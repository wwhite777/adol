"""Judge-output wrapper.

Rule (pipeline design v0, component 5): an error is NEVER a silent zero. Every
malformed / missing / out-of-range / empty judge output raises JudgeParseError,
which the caller must record as an ERROR label.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from kyra.schema import A_KEYS, CF_CODES, D_KEYS, JudgeRecord


class JudgeParseError(ValueError):
    """Raised when a judge output cannot be parsed into a valid JudgeRecord."""


_REQUIRED_TOP = ("D", "A", "critical_failure", "cf_codes", "rationale")


def _strip_code_fence(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 2:
            lines = lines[1:]
            while lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            s = "\n".join(lines).strip()
    return s


def _score(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise JudgeParseError("%s must be an integer 0-2, got %r" % (where, value))
    if value < 0 or value > 2:
        raise JudgeParseError("%s out of range [0,2]: %r" % (where, value))
    return value


def parse_judge_output(text: str) -> JudgeRecord:
    """Parse a judge-panel JSON output into a JudgeRecord.

    Raises JudgeParseError on: non-string/empty input, malformed JSON, missing
    fields, wrong types, out-of-range scores, unknown CF codes, or a
    critical_failure flag inconsistent with cf_codes.
    """
    if text is None or not isinstance(text, str) or not text.strip():
        raise JudgeParseError("empty judge output")

    payload = _strip_code_fence(text)
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise JudgeParseError("malformed JSON: %s" % exc) from exc
    if not isinstance(obj, dict):
        raise JudgeParseError("judge output must be a JSON object, got %s" % type(obj).__name__)

    missing = [k for k in _REQUIRED_TOP if k not in obj]
    if missing:
        raise JudgeParseError("missing field(s): %s" % ", ".join(missing))

    d_raw = obj["D"]
    if not isinstance(d_raw, dict):
        raise JudgeParseError("'D' must be an object with keys D1..D6")
    d_missing = [k for k in D_KEYS if k not in d_raw]
    if d_missing:
        raise JudgeParseError("'D' missing dimension(s): %s" % ", ".join(d_missing))
    d_extra = [k for k in d_raw if k not in D_KEYS]
    if d_extra:
        raise JudgeParseError("'D' has unknown key(s): %s" % ", ".join(sorted(d_extra)))
    D: Dict[str, int] = {k: _score(d_raw[k], "D[%s]" % k) for k in D_KEYS}

    a_raw = obj["A"]
    if not isinstance(a_raw, list) or not a_raw:
        raise JudgeParseError("'A' must be a non-empty list of per-turn objects")
    A: List[Dict[str, int]] = []
    for t, turn in enumerate(a_raw):
        if not isinstance(turn, dict):
            raise JudgeParseError("A[%d] must be an object with keys A1..A4" % t)
        a_missing = [k for k in A_KEYS if k not in turn]
        if a_missing:
            raise JudgeParseError("A[%d] missing axis/axes: %s" % (t, ", ".join(a_missing)))
        a_extra = [k for k in turn if k not in A_KEYS]
        if a_extra:
            raise JudgeParseError("A[%d] has unknown key(s): %s" % (t, ", ".join(sorted(a_extra))))
        A.append({k: _score(turn[k], "A[%d][%s]" % (t, k)) for k in A_KEYS})

    cf_flag = obj["critical_failure"]
    if not isinstance(cf_flag, bool):
        raise JudgeParseError("'critical_failure' must be a boolean, got %r" % (cf_flag,))

    cf_codes = obj["cf_codes"]
    if not isinstance(cf_codes, list) or any(not isinstance(c, str) for c in cf_codes):
        raise JudgeParseError("'cf_codes' must be a list of strings")
    bad = [c for c in cf_codes if c not in CF_CODES]
    if bad:
        raise JudgeParseError(
            "unknown critical-failure code(s): %s (allowed: %s)"
            % (", ".join(bad), ", ".join(CF_CODES))
        )
    if cf_flag and not cf_codes:
        raise JudgeParseError("critical_failure=true requires at least one CF code")
    if not cf_flag and cf_codes:
        raise JudgeParseError("cf_codes given but critical_failure=false")

    rationale = obj["rationale"]
    if not isinstance(rationale, str) or not rationale.strip():
        raise JudgeParseError("'rationale' must be a non-empty string")

    return JudgeRecord(
        D=D, A=A, critical_failure=cf_flag, cf_codes=list(cf_codes), rationale=rationale
    )
