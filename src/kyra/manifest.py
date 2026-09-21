"""Manifest writing, run validation and the MARKER rule.

MARKER means: the process exited 0 AND the run outputs validated. It is never
written by the runner before validate_run returns ok=True.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MANIFEST_NAME = "manifest.jsonl"
RESPONSES_NAME = "responses.jsonl"
MARKER_NAME = "MARKER"

MANIFEST_FIELDS = (
    "run_id",
    "item_id",
    "condition",
    "model_id",
    "provider",
    "api_version",
    "system_prompt_id",
    "temperature",
    "top_p",
    "max_tokens",
    "started_utc",
    "finished_utc",
    "status",
    "error_text",
    "n_turns",
)

RESPONSE_FIELDS = ("item_id", "condition", "turn_index", "user_text", "model_text")


def _append_jsonl(path, record: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_manifest_record(path, record: Dict[str, Any]) -> None:
    """Append one manifest record; raises ValueError if fields are missing/extra."""
    missing = [k for k in MANIFEST_FIELDS if k not in record]
    if missing:
        raise ValueError("manifest record missing field(s): %s" % ", ".join(missing))
    unknown = [k for k in record if k not in MANIFEST_FIELDS]
    if unknown:
        raise ValueError("manifest record has unknown field(s): %s" % ", ".join(sorted(unknown)))
    if record["status"] not in ("ok", "error"):
        raise ValueError("manifest status must be 'ok' or 'error', got %r" % (record["status"],))
    _append_jsonl(path, record)


def write_response_record(path, record: Dict[str, Any]) -> None:
    """Append one response record; raises ValueError if fields are missing/extra."""
    missing = [k for k in RESPONSE_FIELDS if k not in record]
    if missing:
        raise ValueError("response record missing field(s): %s" % ", ".join(missing))
    unknown = [k for k in record if k not in RESPONSE_FIELDS]
    if unknown:
        raise ValueError("response record has unknown field(s): %s" % ", ".join(sorted(unknown)))
    _append_jsonl(path, record)


def _read_jsonl(path) -> Tuple[List[Dict[str, Any]], List[str]]:
    p = Path(path)
    records: List[Dict[str, Any]] = []
    reasons: List[str] = []
    if not p.is_file():
        return records, ["missing file: %s" % p.name]
    with p.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                reasons.append("%s:%d invalid JSON (%s)" % (p.name, lineno, exc))
                continue
            if not isinstance(obj, dict):
                reasons.append("%s:%d record is not a JSON object" % (p.name, lineno))
                continue
            records.append(obj)
    return records, reasons


def validate_run(
    run_dir,
    n_items: int,
    n_conditions: int,
    item_ids: Optional[List[str]] = None,
) -> Tuple[bool, List[str]]:
    """Validate a finished run directory.

    Checks (all must hold for ok=True):
      1. manifest.jsonl and responses.jsonl exist and parse.
      2. manifest record count == n_items * n_conditions.
      3. no manifest record has status='error'.
      4. distinct (item_id, condition) units in responses.jsonl
         == n_items * n_conditions  (response record count check).
      5. per unit, turn_index values are exactly 0..n_turns-1 as declared in the
         manifest (catches a dropped turn inside a multi-turn item).
      6. every item_id passed in item_ids appears in both files.
    """
    run_dir = Path(run_dir)
    reasons: List[str] = []
    expected_units = int(n_items) * int(n_conditions)

    manifest, m_err = _read_jsonl(run_dir / MANIFEST_NAME)
    responses, r_err = _read_jsonl(run_dir / RESPONSES_NAME)
    reasons.extend(m_err)
    reasons.extend(r_err)

    if len(manifest) != expected_units:
        reasons.append(
            "manifest record count mismatch: expected %d (= %d items x %d conditions), found %d"
            % (expected_units, n_items, n_conditions, len(manifest))
        )

    errored = [r.get("item_id") for r in manifest if r.get("status") == "error"]
    if errored:
        reasons.append(
            "manifest contains %d record(s) with status=error: %s"
            % (len(errored), ", ".join(str(x) for x in errored))
        )

    units: Dict[Tuple[Any, Any], List[Any]] = {}
    for r in responses:
        key = (r.get("item_id"), r.get("condition"))
        units.setdefault(key, []).append(r.get("turn_index"))

    if len(units) != expected_units:
        reasons.append(
            "response record count mismatch: expected %d response unit(s) "
            "(= %d items x %d conditions), found %d"
            % (expected_units, n_items, n_conditions, len(units))
        )

    for r in manifest:
        key = (r.get("item_id"), r.get("condition"))
        declared = r.get("n_turns")
        got = sorted(x for x in units.get(key, []) if isinstance(x, int))
        if key not in units:
            reasons.append(
                "no response records for item_id=%r condition=%r" % key
            )
            continue
        if isinstance(declared, int) and got != list(range(declared)):
            reasons.append(
                "response record count mismatch for item_id=%r condition=%r: "
                "expected turn_index 0..%d, found %s"
                % (key[0], key[1], declared - 1, got)
            )

    manifest_ids = {r.get("item_id") for r in manifest}
    response_ids = {k[0] for k in units}
    if item_ids is not None:
        for iid in item_ids:
            if iid not in manifest_ids:
                reasons.append("input item_id %r missing from manifest.jsonl" % iid)
            if iid not in response_ids:
                reasons.append("input item_id %r missing from responses.jsonl" % iid)
    extra = response_ids - manifest_ids
    if extra:
        reasons.append(
            "responses.jsonl has item_id(s) absent from manifest.jsonl: %s"
            % ", ".join(sorted(str(x) for x in extra))
        )

    return (len(reasons) == 0), reasons


def write_marker(run_dir, n_items: int, n_conditions: int, item_ids=None) -> bool:
    """Write MARKER only when validate_run passes. Returns True iff written."""
    run_dir = Path(run_dir)
    ok, reasons = validate_run(run_dir, n_items, n_conditions, item_ids=item_ids)
    if not ok:
        return False
    (run_dir / MARKER_NAME).write_text(
        "validated: %d items x %d conditions\n" % (n_items, n_conditions),
        encoding="utf-8",
    )
    return True
