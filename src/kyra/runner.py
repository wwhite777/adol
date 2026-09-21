"""Runner: execute items x conditions against a provider and write a run directory.

CLI:
  python -m kyra.runner --items <jsonl> --provider mock --cohort mock \
      --out-root result/raw [--conditions base]

Exit codes: 0 ok (MARKER written) | 2 zero items loaded | 3 validation failed
(no MARKER) | 4 bad arguments / unreadable items file.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from kyra import manifest as mf
from kyra.providers import get_provider
from kyra.schema import Item, load_items

EXIT_OK = 0
EXIT_ZERO_ITEMS = 2
EXIT_VALIDATION_FAILED = 3
EXIT_BAD_INPUT = 4

# Condition -> (system_prompt_id, sampling parameters). 'base' is the only
# condition implemented in v0; Arm B (escalation state machine) is out of scope.
CONDITIONS: Dict[str, Dict[str, object]] = {
    "base": {
        "system_prompt_id": "base_v0",
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 512,
    }
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def make_run_id(cohort: str, items_path: str, now: datetime = None) -> str:
    """run_id = UTC YYYYmmddTHHMMZ + short deterministic-per-invocation suffix."""
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%MZ")
    seed = "%s|%s|%s|%d" % (cohort, items_path, now.isoformat(), os.getpid())
    suffix = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6]
    return "%s-%s" % (stamp, suffix)


def run_item(provider, item: Item, condition: str, run_id: str) -> Tuple[Dict, List[Dict]]:
    """Execute one item under one condition, turn by turn with the context so far.

    Returns (manifest_record, response_records). On provider failure the manifest
    record carries status='error' and the error text; turns already completed are
    still returned. Errors are never converted into content.
    """
    cfg = CONDITIONS[condition]
    provider_name = getattr(provider, "provider_name", "unknown")
    record = {
        "run_id": run_id,
        "item_id": item.item_id,
        "condition": condition,
        "model_id": getattr(provider, "model_id", "unknown"),
        "provider": provider_name,
        "api_version": getattr(provider, "api_version", "unknown"),
        "system_prompt_id": cfg["system_prompt_id"],
        "temperature": cfg["temperature"],
        "top_p": cfg["top_p"],
        "max_tokens": cfg["max_tokens"],
        "started_utc": utc_now_iso(),
        "finished_utc": None,
        "status": "ok",
        "error_text": None,
        "n_turns": item.n_turns,
    }
    messages: List[Dict[str, str]] = []
    responses: List[Dict] = []
    for turn_index, user_text in enumerate(item.turns):
        messages.append({"role": "user", "content": user_text})
        try:
            model_text = provider.generate(list(messages))
        except Exception as exc:  # provider failure -> ERROR label, never a score
            record["status"] = "error"
            record["error_text"] = "%s: %s" % (type(exc).__name__, exc)
            record["finished_utc"] = utc_now_iso()
            return record, responses
        if not isinstance(model_text, str) or not model_text.strip():
            record["status"] = "error"
            record["error_text"] = "provider returned empty response at turn %d" % turn_index
            record["finished_utc"] = utc_now_iso()
            return record, responses
        messages.append({"role": "assistant", "content": model_text})
        responses.append(
            {
                "item_id": item.item_id,
                "condition": condition,
                "turn_index": turn_index,
                "user_text": user_text,
                "model_text": model_text,
            }
        )
    record["finished_utc"] = utc_now_iso()
    return record, responses


def execute_run(
    items: List[Item],
    provider,
    conditions: List[str],
    run_dir: Path,
) -> Tuple[bool, List[str]]:
    """Write manifest/responses for every item x condition, then validate + MARKER."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_dir.name
    manifest_path = run_dir / mf.MANIFEST_NAME
    responses_path = run_dir / mf.RESPONSES_NAME
    for condition in conditions:
        for item in items:
            rec, resps = run_item(provider, item, condition, run_id)
            mf.write_manifest_record(manifest_path, rec)
            for r in resps:
                mf.write_response_record(responses_path, r)
    item_ids = [it.item_id for it in items]
    ok, reasons = mf.validate_run(run_dir, len(items), len(conditions), item_ids=item_ids)
    if ok:
        mf.write_marker(run_dir, len(items), len(conditions), item_ids=item_ids)
    return ok, reasons


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kyra.runner", description="KYRA-Bench runner v0")
    p.add_argument("--items", required=True, help="items JSONL path")
    p.add_argument("--provider", default="mock", help="provider name (v0: mock)")
    p.add_argument("--cohort", default="mock", help="cohort directory name")
    p.add_argument("--out-root", default="result/raw", help="root for result/raw/<cohort>/<run_id>")
    p.add_argument(
        "--conditions",
        nargs="+",
        default=["base"],
        help="conditions to run (v0: base)",
    )
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    for c in args.conditions:
        if c not in CONDITIONS:
            sys.stderr.write(
                "ERROR: unknown condition %r (available: %s)\n"
                % (c, ", ".join(sorted(CONDITIONS)))
            )
            return EXIT_BAD_INPUT
    try:
        provider = get_provider(args.provider)
    except ValueError as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return EXIT_BAD_INPUT
    try:
        items = load_items(args.items)
    except ValueError as exc:
        sys.stderr.write("ERROR: could not load items: %s\n" % exc)
        return EXIT_BAD_INPUT

    if not items:
        sys.stderr.write(
            "ERROR: zero items loaded from %s - refusing to write an empty run "
            "(a 0-item run is an abnormal termination, not a success)\n" % args.items
        )
        return EXIT_ZERO_ITEMS

    run_id = make_run_id(args.cohort, args.items)
    run_dir = Path(args.out_root) / args.cohort / run_id
    if run_dir.exists():
        sys.stderr.write("ERROR: run directory already exists: %s\n" % run_dir)
        return EXIT_BAD_INPUT

    sys.stdout.write(
        "run_id=%s cohort=%s provider=%s model_id=%s items=%d conditions=%s\n"
        % (run_id, args.cohort, args.provider, provider.model_id, len(items),
           ",".join(args.conditions))
    )
    sys.stdout.write("run_dir=%s\n" % run_dir)

    ok, reasons = execute_run(items, provider, list(args.conditions), run_dir)
    if not ok:
        sys.stderr.write("ERROR: run validation FAILED - MARKER not written:\n")
        for r in reasons:
            sys.stderr.write("  - %s\n" % r)
        return EXIT_VALIDATION_FAILED

    sys.stdout.write(
        "OK: validated %d item(s) x %d condition(s); MARKER written at %s\n"
        % (len(items), len(args.conditions), run_dir / mf.MARKER_NAME)
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
