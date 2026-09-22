"""Fail-closed freeze gate for a preregistration YAML (KYRA-Bench).

Usage (from the repo root):
    PYTHONPATH=src python -m gates.freeze --prereg <path.yaml> \
        --contract <path.md> [--out-sha <path.sha256>]

Steps, each fail-closed with a named reason and a distinct exit code:
    (a) parse   : yaml.safe_load                         -> exit 2  PARSE_ERROR
    (b) schema  : required keys / claim shape            -> exit 3  SCHEMA_ERROR
    (c) contract: claim ids, forbidden wording, version  -> exit 4  CONTRACT_DISAGREEMENT
    (d) write   : sha256 receipt + re-read confirmation  -> exit 5  WRITE_FAILURE

The .sha256 receipt is written by this process only, and only after (a)-(c)
have passed and the re-read of the preregistration file reproduces the hash.
No following shell line ever produces the receipt.

Design rule (global rules v3.2 §14 / project CLAUDE.md): the hash must be
produced by the verifying process itself, before the first confirmatory run.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

EXIT_OK = 0
EXIT_PARSE = 2
EXIT_SCHEMA = 3
EXIT_CONTRACT = 4
EXIT_WRITE = 5

REQUIRED_TOP_LEVEL_KEYS: Tuple[str, ...] = (
    "topic",
    "version",
    "frozen_by",
    "claims",
    "baselines",
    "splits",
    "statistics",
    "decision_rules",
    "interim_look_rule",
    "kill_rules",
    "forbidden_wording",
    "fallback",
    "definitions",
)

CLAIM_ID_RE = re.compile(r"^N\d+(\.\d+)?$")
CLAIM_TYPES = ("primary", "supporting")
DECISION_RULE_KEYS = ("pass", "fail", "miss")
MAX_TOP_LEVEL_SUPPORTING = 3


class GateError(Exception):
    """A fail-closed gate refusal: carries a named reason and an exit code."""

    def __init__(self, reason: str, detail: str, code: int) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail
        self.code = code


# --------------------------------------------------------------------------
# (a) parse
# --------------------------------------------------------------------------
def parse_prereg(prereg_path: Path) -> Dict[str, Any]:
    """Read and yaml.safe_load the preregistration; any failure is PARSE_ERROR."""
    try:
        raw = prereg_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateError("PARSE_ERROR", f"cannot read {prereg_path}: {exc}", EXIT_PARSE)
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        oneline = " ".join(str(exc).split())
        raise GateError("PARSE_ERROR", f"{prereg_path} is not valid YAML: {oneline}", EXIT_PARSE)
    if not isinstance(doc, dict):
        raise GateError(
            "PARSE_ERROR",
            f"{prereg_path} must parse to a mapping, got {type(doc).__name__}",
            EXIT_PARSE,
        )
    return doc


# --------------------------------------------------------------------------
# (b) schema
# --------------------------------------------------------------------------
def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_claim(claim: Any, index: int) -> None:
    where = f"claims[{index}]"
    if not isinstance(claim, dict):
        raise GateError("SCHEMA_ERROR", f"{where} is not a mapping", EXIT_SCHEMA)
    claim_id = claim.get("id")
    if not isinstance(claim_id, str) or not CLAIM_ID_RE.match(claim_id):
        raise GateError(
            "SCHEMA_ERROR",
            f"{where} has id {claim_id!r}, expected to match ^N\\d+(\\.\\d+)?$",
            EXIT_SCHEMA,
        )
    where = f"claim {claim_id}"
    for key in ("text", "metric"):
        value = claim.get(key)
        if not isinstance(value, str) or not value.strip():
            raise GateError(
                "SCHEMA_ERROR", f"{where} has missing or empty {key}", EXIT_SCHEMA
            )
    claim_type = claim.get("type")
    if claim_type not in CLAIM_TYPES:
        raise GateError(
            "SCHEMA_ERROR",
            f"{where} has type {claim_type!r}, expected one of {CLAIM_TYPES}",
            EXIT_SCHEMA,
        )
    if "threshold" not in claim:
        raise GateError("SCHEMA_ERROR", f"{where} has no threshold", EXIT_SCHEMA)
    if not _is_number(claim["threshold"]):
        raise GateError(
            "SCHEMA_ERROR",
            f"{where} threshold {claim['threshold']!r} is "
            f"{type(claim['threshold']).__name__}, expected a number",
            EXIT_SCHEMA,
        )
    falsifier = claim.get("falsifier")
    if not isinstance(falsifier, str) or not falsifier.strip():
        raise GateError(
            "SCHEMA_ERROR", f"{where} has missing or empty falsifier", EXIT_SCHEMA
        )
    rule = claim.get("decision_rule")
    if not isinstance(rule, dict):
        raise GateError(
            "SCHEMA_ERROR", f"{where} has no decision_rule mapping", EXIT_SCHEMA
        )
    missing = [k for k in DECISION_RULE_KEYS if k not in rule]
    if missing:
        raise GateError(
            "SCHEMA_ERROR",
            f"{where} decision_rule is missing key(s): {', '.join(missing)}",
            EXIT_SCHEMA,
        )


def check_schema(doc: Dict[str, Any]) -> List[str]:
    """Validate the preregistration structure; return the top-level claim ids."""
    missing = [k for k in REQUIRED_TOP_LEVEL_KEYS if k not in doc]
    if missing:
        raise GateError(
            "SCHEMA_ERROR",
            f"missing required top-level key(s): {', '.join(missing)}",
            EXIT_SCHEMA,
        )

    claims = doc["claims"]
    if not isinstance(claims, list) or not claims:
        raise GateError("SCHEMA_ERROR", "claims must be a non-empty list", EXIT_SCHEMA)
    for index, claim in enumerate(claims):
        _check_claim(claim, index)

    ids = [c["id"] for c in claims]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise GateError(
            "SCHEMA_ERROR", f"duplicate claim id(s): {', '.join(duplicates)}", EXIT_SCHEMA
        )

    top_level = [c for c in claims if "." not in c["id"]]
    primaries = [c["id"] for c in top_level if c["type"] == "primary"]
    if len(primaries) != 1:
        raise GateError(
            "SCHEMA_ERROR",
            f"expected exactly one top-level primary claim, found {len(primaries)}"
            + (f" ({', '.join(primaries)})" if primaries else ""),
            EXIT_SCHEMA,
        )
    supporting = [c["id"] for c in top_level if c["type"] == "supporting"]
    if len(supporting) > MAX_TOP_LEVEL_SUPPORTING:
        raise GateError(
            "SCHEMA_ERROR",
            f"at most {MAX_TOP_LEVEL_SUPPORTING} top-level supporting claims, "
            f"found {len(supporting)} ({', '.join(supporting)})",
            EXIT_SCHEMA,
        )

    baselines = doc["baselines"]
    if not isinstance(baselines, list) or not baselines:
        raise GateError("SCHEMA_ERROR", "baselines must be a non-empty list", EXIT_SCHEMA)
    for index, baseline in enumerate(baselines):
        if not isinstance(baseline, str) or not baseline.strip():
            raise GateError(
                "SCHEMA_ERROR",
                f"baselines[{index}] must be a non-empty string, got {baseline!r}",
                EXIT_SCHEMA,
            )

    forbidden = doc["forbidden_wording"]
    if not isinstance(forbidden, list) or not forbidden:
        raise GateError(
            "SCHEMA_ERROR", "forbidden_wording must be a non-empty list", EXIT_SCHEMA
        )
    for index, phrase in enumerate(forbidden):
        if not isinstance(phrase, str) or not phrase.strip():
            raise GateError(
                "SCHEMA_ERROR",
                f"forbidden_wording[{index}] must be a non-empty string, got {phrase!r}",
                EXIT_SCHEMA,
            )

    return [c["id"] for c in top_level]


# --------------------------------------------------------------------------
# (c) contract agreement
# --------------------------------------------------------------------------
def _id_token_re(claim_id: str) -> "re.Pattern[str]":
    # "N1" must not be satisfied by "N1.1": no alphanumeric, underscore or dot
    # may sit on either side of the token.
    return re.compile(
        r"(?<![A-Za-z0-9_.])" + re.escape(claim_id) + r"(?![A-Za-z0-9_.])"
    )


def check_contract(doc: Dict[str, Any], top_level_ids: List[str], contract_path: Path) -> None:
    """Every top-level claim id, every forbidden phrase and the version must agree."""
    try:
        contract = contract_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateError(
            "CONTRACT_DISAGREEMENT", f"cannot read {contract_path}: {exc}", EXIT_CONTRACT
        )

    missing_ids = [cid for cid in top_level_ids if not _id_token_re(cid).search(contract)]
    if missing_ids:
        raise GateError(
            "CONTRACT_DISAGREEMENT",
            f"{contract_path.name} does not mention claim id(s): {', '.join(missing_ids)}",
            EXIT_CONTRACT,
        )

    lowered = contract.lower()
    missing_phrases = [p for p in doc["forbidden_wording"] if p.lower() not in lowered]
    if missing_phrases:
        shown = "; ".join(repr(p) for p in missing_phrases)
        raise GateError(
            "CONTRACT_DISAGREEMENT",
            f"{contract_path.name} is missing forbidden wording: {shown}",
            EXIT_CONTRACT,
        )

    version = str(doc["version"])
    if f"Version: {version}" not in contract:
        raise GateError(
            "CONTRACT_DISAGREEMENT",
            f"{contract_path.name} does not contain 'Version: {version}' "
            "(prereg version and contract version disagree)",
            EXIT_CONTRACT,
        )


# --------------------------------------------------------------------------
# (d) receipt
# --------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_receipt(prereg_path: Path, out_sha: Path) -> str:
    """Hash the prereg, write the receipt, then re-read and confirm. Fail closed."""
    try:
        digest = sha256_file(prereg_path)
    except OSError as exc:
        raise GateError("WRITE_FAILURE", f"cannot hash {prereg_path}: {exc}", EXIT_WRITE)

    line = f"{digest}  {prereg_path.name}\n"
    try:
        out_sha.parent.mkdir(parents=True, exist_ok=True)
        out_sha.write_text(line, encoding="utf-8")
    except OSError as exc:
        raise GateError("WRITE_FAILURE", f"cannot write {out_sha}: {exc}", EXIT_WRITE)

    # Re-read both files and confirm the receipt states the file's current hash.
    try:
        recheck = sha256_file(prereg_path)
        written = out_sha.read_text(encoding="utf-8")
    except OSError as exc:
        _remove_quietly(out_sha)
        raise GateError("WRITE_FAILURE", f"cannot re-read after write: {exc}", EXIT_WRITE)

    if recheck != digest:
        _remove_quietly(out_sha)
        raise GateError(
            "WRITE_FAILURE",
            f"{prereg_path.name} changed during freeze ({digest} -> {recheck})",
            EXIT_WRITE,
        )
    if written != line:
        _remove_quietly(out_sha)
        raise GateError(
            "WRITE_FAILURE",
            f"receipt {out_sha.name} did not read back as written",
            EXIT_WRITE,
        )
    return digest


def _remove_quietly(path: Path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def freeze(prereg_path: Path, contract_path: Path, out_sha: Path) -> str:
    doc = parse_prereg(prereg_path)
    top_level_ids = check_schema(doc)
    check_contract(doc, top_level_ids, contract_path)
    return write_receipt(prereg_path, out_sha)


def default_out_sha(prereg_path: Path) -> Path:
    return Path(str(prereg_path) + ".sha256")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gates.freeze",
        description="Fail-closed freeze gate: hash a preregistration only if it "
        "parses, matches the schema and agrees with the claim contract.",
    )
    parser.add_argument("--prereg", required=True, help="preregistration YAML path")
    parser.add_argument("--contract", required=True, help="claim contract Markdown path")
    parser.add_argument(
        "--out-sha", default=None, help="receipt path (default: <prereg>.sha256)"
    )
    args = parser.parse_args(argv)

    prereg_path = Path(args.prereg)
    contract_path = Path(args.contract)
    out_sha = Path(args.out_sha) if args.out_sha else default_out_sha(prereg_path)

    try:
        digest = freeze(prereg_path, contract_path, out_sha)
    except GateError as exc:
        print(f"ERROR {exc.reason}: {exc.detail}", file=sys.stderr)
        print(f"REFUSED to freeze {prereg_path.name}; no receipt written.", file=sys.stderr)
        return exc.code

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"FROZEN {prereg_path.name} sha256={digest} at {stamp}")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
