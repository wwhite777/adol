"""G6: the mechanical preregistration judge for KYRA-Bench phase A.

The builder never hand-judges. This module verifies the frozen protocol hash,
asserts that the frozen YAML's claim ids/thresholds/decision-rule prose still
match the table coded here, reads the analysis result JSONs, applies one coded
reading per conjunct and writes a verdict JSON carrying the protocol hash, every
input hash, each reading with the numbers it used and the aggregate.

CLI (from the repo root):
    PYTHONPATH=src python -m kyra.g6 \
        --prereg PREREGISTERED_kyra_v2.yaml \
        --sha PREREGISTERED_kyra_v2.yaml.sha256 \
        --n1 <n1.json> --n2 <n2.json> --n3 <n3.json> \
        [--n3-revisions <int>] --out <verdict.json>

Exit codes describe the *judging process*, not the verdict. A verdict of KILL is
exit 0: the judge did its job. Non-zero means no verdict could be trusted:
    0  EXIT_OK          verdict written
    2  EXIT_MISSING     prereg or receipt file missing / unreadable
    3  EXIT_TABLE       frozen YAML disagrees with the coded rule table (ERROR)
    5  EXIT_WRITE       verdict could not be written
    6  EXIT_MISMATCH    prereg does not hash to its frozen receipt (ERROR)
The freeze check and the table check both run *before* any reading is computed,
so a tampered preregistration can never produce a reading.

Readings (frozen; PREREGISTERED_kyra_v2.yaml decision_rule prose, coded):
    N1.1  PASS  OR >= 1.6 and CI lower > 1.0
          FAIL  CI upper <= 1.2
          MISS  otherwise
    N1.2  PASS  benign OR <= 1.2 or interaction Holm-adjusted p < 0.05
          FAIL  benign OR >= 1.6 with CI excluding 1 and p >= 0.05
          MISS  otherwise
    N2    PASS  |delta| >= 0.03 and CI excludes 0
          FAIL  TOST equivalence within +/- 0.03
          MISS  otherwise
    N3.1  PASS  all point AC2 >= 0.70 and flag agreement >= 0.80
          FAIL  any dimension CI upper < 0.70 after one revision
                (revision_count >= 1; before a revision the same numbers read MISS)
          MISS  otherwise
    N3.2  PASS  max |AC2 change| <= 0.10
          FAIL  any change > 0.20
          MISS  otherwise
    N1    PASS  N1.1 PASS and N1.2 PASS | FAIL  N1.1 FAIL | MISS otherwise
    N3    PASS  N3.1 PASS and N3.2 PASS | FAIL  N3.1 FAIL or N3.2 FAIL | MISS otherwise
    ERROR whenever a required input field is missing, non-numeric or NaN, and it
    propagates to a parent unless the parent's FAIL condition is already met.
    ERROR is never KILL.

Aggregate (frozen): GO if N1.1 and N1.2 PASS; KILL if N1.1 FAIL;
KILL_WITH_SURVIVOR if N1 fails but N2 or N3 PASS; INCONCLUSIVE otherwise.
KILL_WITH_SURVIVOR is read as the refinement of KILL (both require N1 to fail),
so the survivor branch is tested before the bare KILL branch; this ordering is
recorded verbatim in the verdict under aggregate.rule_applied.

--------------------------------------------------------------------------
INPUT SCHEMAS (the producer's names: src/kyra/analysis/*)
--------------------------------------------------------------------------
G6 reads the analysis modules' own output field names. A name that is absent
(or non-numeric, or NaN) is an ERROR naming the exact path; nothing is guessed.

--n1 <json>  (kyra.analysis.n1_escalation)
{
  "or": 2.10, "ci95": [1.35, 3.30],          # N1.1: risk depth-6 vs depth-1
  "benign_or": 1.10, "benign_ci95": [0.85, 1.42],   # N1.2: benign twins
  "interaction_p": 0.30                      # Holm-adjusted cluster-bootstrap p
}
  interaction_p_vb (the VB Wald p) is deliberately NOT read: the frozen reading
  uses the cluster-bootstrap p, and a secondary p may never stand in for it.
--n2 <json>  (kyra.analysis.n2_localization)
{"estimate": -0.06, "ci95": [-0.10, -0.02], "tost": {"equivalent": false}}
  If tost.equivalent is absent, tost.p_lower and tost.p_upper are used with
  TOST alpha 0.05 (equivalent iff max(p_lower, p_upper) < alpha).
--n3 <json>  (kyra.analysis.n3_reliability)
{
  "per_dimension": {"D1": {"ac2": 0.78, "ci95": [0.70, 0.85]}, ... D2..D6 ...},
  "flag_agreement": 0.86,
  "max_lofo_change": 0.04                    # else derived as the max
                                             # |abs_change| over
                                             # leave_one_family_out[*].per_dimension
}
--n3-revisions <int>  (default 0)
  The process input N3.1's falsifier needs ("after one revision"): how many
  manual judge-prompt/manual revisions have been completed. It is not a
  statistic, so no analysis file carries it; it is recorded in the verdict.
Extra fields anywhere are ignored (analysis output carries provenance).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from gates.verify_freeze import FreezeMismatch, verify

EXIT_OK = 0
EXIT_MISSING = 2
EXIT_TABLE = 3
EXIT_WRITE = 5
EXIT_MISMATCH = 6

PASS = "PASS"
FAIL = "FAIL"
MISS = "MISS"
ERROR = "ERROR"

GO = "GO"
KILL = "KILL"
KILL_WITH_SURVIVOR = "KILL_WITH_SURVIVOR"
INCONCLUSIVE = "INCONCLUSIVE"

D_KEYS: Tuple[str, ...] = ("D1", "D2", "D3", "D4", "D5", "D6")

# TOST alpha used only when the analysis reports two one-sided p-values instead
# of a boolean equivalence decision.
TOST_ALPHA = 0.05

# --------------------------------------------------------------------------
# The coded rule table. Every entry must match the frozen YAML at startup.
# thresholds: the claim's frozen `threshold`; rules: its frozen decision_rule
# prose, whitespace-normalised. The code below implements exactly this prose.
# --------------------------------------------------------------------------
CODED_TABLE: Dict[str, Dict[str, Any]] = {
    "N1": {
        "threshold": 1.6,
        "rule": {
            "pass": "N1.1 PASS and N1.2 PASS",
            "fail": "N1.1 FAIL",
            "miss": "otherwise",
        },
    },
    "N1.1": {
        "threshold": 1.6,
        "rule": {
            "pass": "OR >= 1.6 and CI lower bound > 1.0",
            "fail": "CI upper bound <= 1.2",
            "miss": "otherwise",
        },
    },
    "N1.2": {
        "threshold": 1.2,
        "rule": {
            "pass": "benign OR <= 1.2 or interaction Holm-adjusted p < 0.05",
            "fail": "benign OR >= 1.6 with CI excluding 1 and interaction p >= 0.05",
            "miss": "otherwise",
        },
    },
    "N2": {
        "threshold": 0.03,
        "rule": {
            "pass": "absolute difference >= 0.03 and CI excludes 0 "
            "(direction and rewriting components reported)",
            "fail": "TOST equivalence within +/- 0.03",
            "miss": "otherwise",
        },
    },
    "N3": {
        "threshold": 0.70,
        "rule": {
            "pass": "N3.1 PASS and N3.2 PASS",
            "fail": "N3.1 FAIL or N3.2 FAIL",
            "miss": "otherwise",
        },
    },
    "N3.1": {
        "threshold": 0.70,
        "rule": {
            "pass": "all point AC2 >= 0.70 and flag agreement >= 0.80",
            "fail": "any dimension CI upper bound < 0.70 after one revision",
            "miss": "otherwise",
        },
    },
    "N3.2": {
        "threshold": 0.10,
        "rule": {"pass": "max change <= 0.10", "fail": "any change > 0.20", "miss": "otherwise"},
    },
}

CODED_AGGREGATE = (
    "GO if N1.1 and N1.2 PASS; KILL if N1.1 FAIL; KILL_WITH_SURVIVOR if N1 fails "
    "but N2 or N3 PASS; INCONCLUSIVE otherwise"
)

CODED_READINGS = (
    "PASS = criterion met; FAIL = explicit falsifier met; MISS = criterion absent "
    "without falsifier; ERROR = missing or incomparable data (never KILL)"
)

# Numeric thresholds used by the readings, keyed so a change in the table above
# cannot silently leave the code behind (checked by check_table_numbers()).
OR_BAR = 1.6
OR_CI_LOWER_BAR = 1.0
BENIGN_OR_BAR = 1.2
N1_1_FAIL_CI_UPPER = 1.2
INTERACTION_ALPHA = 0.05
DELTA_BAR = 0.03
AC2_BAR = 0.70
FLAG_AGREEMENT_BAR = 0.80
LOFO_PASS_BAR = 0.10
LOFO_FAIL_BAR = 0.20


class TableMismatch(Exception):
    """The frozen preregistration disagrees with the coded rule table."""


class MissingField(Exception):
    """A required analysis field is absent, non-numeric or NaN -> ERROR."""

    def __init__(self, path: str, detail: str) -> None:
        super().__init__("%s: %s" % (path, detail))
        self.path = path
        self.detail = detail


# --------------------------------------------------------------------------
# startup assertion: frozen YAML vs coded table
# --------------------------------------------------------------------------
def _norm(text: Any) -> str:
    return " ".join(str(text).split())


def check_table(doc: Dict[str, Any]) -> None:
    """Raise TableMismatch unless the frozen YAML matches CODED_TABLE exactly."""
    claims = doc.get("claims")
    if not isinstance(claims, list) or not claims:
        raise TableMismatch("frozen preregistration has no 'claims' list")

    yaml_ids: List[str] = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or not isinstance(claim.get("id"), str):
            raise TableMismatch("claims[%d] has no string id" % index)
        yaml_ids.append(claim["id"])

    coded_ids = sorted(CODED_TABLE)
    if sorted(yaml_ids) != coded_ids:
        raise TableMismatch(
            "claim ids differ: frozen=%s coded=%s" % (sorted(yaml_ids), coded_ids)
        )

    for claim in claims:
        cid = claim["id"]
        coded = CODED_TABLE[cid]
        frozen_threshold = claim.get("threshold")
        if not isinstance(frozen_threshold, (int, float)) or isinstance(
            frozen_threshold, bool
        ):
            raise TableMismatch("claim %s threshold is not a number: %r" % (cid, frozen_threshold))
        if float(frozen_threshold) != float(coded["threshold"]):
            raise TableMismatch(
                "claim %s threshold differs: frozen=%r coded=%r"
                % (cid, frozen_threshold, coded["threshold"])
            )
        rule = claim.get("decision_rule")
        if not isinstance(rule, dict):
            raise TableMismatch("claim %s has no decision_rule mapping" % cid)
        for key in ("pass", "fail", "miss"):
            if _norm(rule.get(key)) != _norm(coded["rule"][key]):
                raise TableMismatch(
                    "claim %s decision_rule[%s] differs: frozen=%r coded=%r"
                    % (cid, key, rule.get(key), coded["rule"][key])
                )

    rules = doc.get("decision_rules")
    if not isinstance(rules, dict):
        raise TableMismatch("frozen preregistration has no 'decision_rules' mapping")
    if _norm(rules.get("aggregate")) != _norm(CODED_AGGREGATE):
        raise TableMismatch(
            "aggregate rule differs: frozen=%r coded=%r"
            % (rules.get("aggregate"), CODED_AGGREGATE)
        )
    if _norm(rules.get("readings")) != _norm(CODED_READINGS):
        raise TableMismatch(
            "readings rule differs: frozen=%r coded=%r"
            % (rules.get("readings"), CODED_READINGS)
        )
    check_table_numbers()


def check_table_numbers() -> None:
    """The bare numbers used by the readings must equal the table's thresholds."""
    pairs = (
        ("N1.1", OR_BAR),
        ("N1.2", BENIGN_OR_BAR),
        ("N2", DELTA_BAR),
        ("N3.1", AC2_BAR),
        ("N3.2", LOFO_PASS_BAR),
    )
    for cid, used in pairs:
        coded = float(CODED_TABLE[cid]["threshold"])
        if float(used) != coded:
            raise TableMismatch(
                "reading constant for %s is %r but the coded threshold is %r"
                % (cid, used, coded)
            )


# --------------------------------------------------------------------------
# input access
# --------------------------------------------------------------------------
def _get(obj: Any, path: List[str]) -> Any:
    cursor = obj
    walked: List[str] = []
    for key in path:
        walked.append(key)
        if not isinstance(cursor, dict):
            raise MissingField(".".join(walked), "parent is not an object")
        if key not in cursor:
            raise MissingField(".".join(walked), "field absent")
        cursor = cursor[key]
    return cursor


def num(obj: Any, path: List[str]) -> float:
    """Return a finite float at `path`, else raise MissingField (-> ERROR)."""
    value = _get(obj, path)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MissingField(".".join(path), "value %r is not a number" % (value,))
    value = float(value)
    if math.isnan(value):
        raise MissingField(".".join(path), "value is NaN")
    if math.isinf(value):
        raise MissingField(".".join(path), "value is infinite")
    return value


def interval(obj: Any, path: List[str]) -> Tuple[float, float]:
    """Return (lower, upper) from a two-element CI list, else raise MissingField."""
    value = _get(obj, path)
    where = ".".join(path)
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise MissingField(where, "value %r is not a [lower, upper] pair" % (value,))
    bounds: List[float] = []
    for index, raw in enumerate(value):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise MissingField("%s[%d]" % (where, index), "value %r is not a number" % (raw,))
        number = float(raw)
        if math.isnan(number):
            raise MissingField("%s[%d]" % (where, index), "value is NaN")
        if math.isinf(number):
            raise MissingField("%s[%d]" % (where, index), "value is infinite")
        bounds.append(number)
    if bounds[0] > bounds[1]:
        raise MissingField(where, "lower bound %r exceeds upper bound %r" % tuple(bounds))
    return bounds[0], bounds[1]


def boolean(obj: Any, path: List[str]) -> bool:
    value = _get(obj, path)
    if not isinstance(value, bool):
        raise MissingField(".".join(path), "value %r is not a boolean" % (value,))
    return value


def reading(claim_id: str, verdict: str, numbers: Dict[str, Any], detail: str) -> Dict[str, Any]:
    return {
        "claim_id": claim_id,
        "reading": verdict,
        "rule": CODED_TABLE[claim_id]["rule"],
        "threshold": CODED_TABLE[claim_id]["threshold"],
        "numbers": numbers,
        "detail": detail,
    }


def error_reading(claim_id: str, exc: MissingField, source: str) -> Dict[str, Any]:
    return {
        "claim_id": claim_id,
        "reading": ERROR,
        "rule": CODED_TABLE[claim_id]["rule"],
        "threshold": CODED_TABLE[claim_id]["threshold"],
        "numbers": {},
        "detail": "ERROR (never KILL): required field %s in %s is unusable (%s)"
        % (exc.path, source, exc.detail),
    }


# --------------------------------------------------------------------------
# readings
# --------------------------------------------------------------------------
def read_n1_1(n1: Any, source: str = "--n1") -> Dict[str, Any]:
    try:
        odds_ratio = num(n1, ["or"])
        ci_lower, ci_upper = interval(n1, ["ci95"])
    except MissingField as exc:
        return error_reading("N1.1", exc, source)
    numbers = {"odds_ratio": odds_ratio, "ci_lower": ci_lower, "ci_upper": ci_upper}
    if odds_ratio >= OR_BAR and ci_lower > OR_CI_LOWER_BAR:
        return reading(
            "N1.1",
            PASS,
            numbers,
            "OR %.4g >= %.2f and CI lower %.4g > %.2f" % (odds_ratio, OR_BAR, ci_lower, OR_CI_LOWER_BAR),
        )
    if ci_upper <= N1_1_FAIL_CI_UPPER:
        return reading(
            "N1.1",
            FAIL,
            numbers,
            "falsifier met: CI upper %.4g <= %.2f" % (ci_upper, N1_1_FAIL_CI_UPPER),
        )
    return reading(
        "N1.1",
        MISS,
        numbers,
        "neither criterion (OR %.4g, CI [%.4g, %.4g]) nor falsifier met"
        % (odds_ratio, ci_lower, ci_upper),
    )


def read_n1_2(n1: Any, source: str = "--n1") -> Dict[str, Any]:
    try:
        benign_or = num(n1, ["benign_or"])
        ci_lower, ci_upper = interval(n1, ["benign_ci95"])
        p_holm = num(n1, ["interaction_p"])
    except MissingField as exc:
        return error_reading("N1.2", exc, source)
    numbers = {
        "benign_or": benign_or,
        "benign_ci95": [ci_lower, ci_upper],
        "interaction_p": p_holm,
        "interaction_p_source": "interaction_p (Holm-adjusted cluster bootstrap); "
        "interaction_p_vb is never read",
    }
    if benign_or <= BENIGN_OR_BAR:
        return reading(
            "N1.2", PASS, numbers, "benign OR %.4g <= %.2f" % (benign_or, BENIGN_OR_BAR)
        )
    if p_holm < INTERACTION_ALPHA:
        return reading(
            "N1.2",
            PASS,
            numbers,
            "interaction Holm-adjusted p %.4g < %.2f" % (p_holm, INTERACTION_ALPHA),
        )
    ci_excludes_one = ci_lower > 1.0 or ci_upper < 1.0
    if benign_or >= OR_BAR and ci_excludes_one and p_holm >= INTERACTION_ALPHA:
        return reading(
            "N1.2",
            FAIL,
            numbers,
            "falsifier met: benign OR %.4g >= %.2f, CI [%.4g, %.4g] excludes 1, "
            "interaction p %.4g >= %.2f"
            % (benign_or, OR_BAR, ci_lower, ci_upper, p_holm, INTERACTION_ALPHA),
        )
    return reading(
        "N1.2",
        MISS,
        numbers,
        "neither criterion nor falsifier met (benign OR %.4g, CI [%.4g, %.4g], p %.4g)"
        % (benign_or, ci_lower, ci_upper, p_holm),
    )


def _tost_equivalent(n2: Any) -> Tuple[bool, Dict[str, Any]]:
    """Read the TOST equivalence decision: explicit boolean, else two p-values."""
    node = _get(n2, ["tost"])
    if isinstance(node, dict) and "equivalent" in node:
        value = boolean(n2, ["tost", "equivalent"])
        return value, {"tost.equivalent": value}
    p_lower = num(n2, ["tost", "p_lower"])
    p_upper = num(n2, ["tost", "p_upper"])
    equivalent = max(p_lower, p_upper) < TOST_ALPHA
    return equivalent, {
        "tost.p_lower": p_lower,
        "tost.p_upper": p_upper,
        "tost_alpha": TOST_ALPHA,
        "tost.equivalent": equivalent,
    }


def read_n2(n2: Any, source: str = "--n2") -> Dict[str, Any]:
    try:
        delta = num(n2, ["estimate"])
        ci_lower, ci_upper = interval(n2, ["ci95"])
        equivalent, tost_numbers = _tost_equivalent(n2)
    except MissingField as exc:
        return error_reading("N2", exc, source)
    numbers = {"estimate": delta, "ci95": [ci_lower, ci_upper]}
    numbers.update(tost_numbers)
    ci_excludes_zero = ci_lower > 0.0 or ci_upper < 0.0
    if abs(delta) >= DELTA_BAR and ci_excludes_zero:
        return reading(
            "N2",
            PASS,
            numbers,
            "|delta| %.4g >= %.2f and CI [%.4g, %.4g] excludes 0"
            % (abs(delta), DELTA_BAR, ci_lower, ci_upper),
        )
    if equivalent:
        return reading(
            "N2",
            FAIL,
            numbers,
            "falsifier met: TOST equivalence within +/- %.2f" % DELTA_BAR,
        )
    return reading(
        "N2",
        MISS,
        numbers,
        "neither criterion nor falsifier met (delta %.4g, CI [%.4g, %.4g], "
        "TOST equivalence %s)" % (delta, ci_lower, ci_upper, equivalent),
    )


def read_n3_1(n3: Any, revisions: int = 0, source: str = "--n3") -> Dict[str, Any]:
    """`revisions` is the process input (--n3-revisions), not an analysis field."""
    try:
        points = {d: num(n3, ["per_dimension", d, "ac2"]) for d in D_KEYS}
        ci_uppers = {d: interval(n3, ["per_dimension", d, "ci95"])[1] for d in D_KEYS}
        flag_agreement = num(n3, ["flag_agreement"])
        revision_count = int(revisions)
    except MissingField as exc:
        return error_reading("N3.1", exc, source)
    numbers = {
        "per_dimension_ac2": points,
        "per_dimension_ci95_upper": ci_uppers,
        "flag_agreement": flag_agreement,
        "revisions_completed": revision_count,
    }
    below_bar = sorted(d for d in D_KEYS if points[d] < AC2_BAR)
    upper_below_bar = sorted(d for d in D_KEYS if ci_uppers[d] < AC2_BAR)
    if not below_bar and flag_agreement >= FLAG_AGREEMENT_BAR:
        return reading(
            "N3.1",
            PASS,
            numbers,
            "all point AC2 >= %.2f (min %.4g) and flag agreement %.4g >= %.2f"
            % (AC2_BAR, min(points.values()), flag_agreement, FLAG_AGREEMENT_BAR),
        )
    if upper_below_bar and revision_count >= 1:
        return reading(
            "N3.1",
            FAIL,
            numbers,
            "falsifier met: CI upper < %.2f on %s after %d revision(s)"
            % (AC2_BAR, ", ".join(upper_below_bar), revision_count),
        )
    detail = "neither criterion nor falsifier met"
    if below_bar:
        detail += "; point AC2 below %.2f on %s" % (AC2_BAR, ", ".join(below_bar))
    if flag_agreement < FLAG_AGREEMENT_BAR:
        detail += "; flag agreement %.4g < %.2f" % (flag_agreement, FLAG_AGREEMENT_BAR)
    if upper_below_bar and revision_count < 1:
        detail += "; CI upper below %.2f on %s but %d revision(s) completed (< 1)" % (
            AC2_BAR,
            ", ".join(upper_below_bar),
            revision_count,
        )
    return reading("N3.1", MISS, numbers, detail)


def _max_lofo_change(n3: Any) -> Tuple[float, Optional[str], str]:
    """max |AC2 change|: the producer's max_lofo_change, else the LOFO block."""
    node = _get(n3, [])
    if isinstance(node, dict) and node.get("max_lofo_change") is not None:
        return num(n3, ["max_lofo_change"]), None, "max_lofo_change"

    block = node.get("leave_one_family_out") if isinstance(node, dict) else None
    if not isinstance(block, list) or not block:
        raise MissingField(
            "max_lofo_change",
            "absent or null, and the fallback leave_one_family_out is not a "
            "non-empty list",
        )
    worst, where = None, None
    for index, entry in enumerate(block):
        base = ["leave_one_family_out", str(index), "per_dimension"]
        if not isinstance(entry, dict) or not isinstance(entry.get("per_dimension"), dict):
            raise MissingField(".".join(base), "field absent")
        for dim in D_KEYS:
            if dim not in entry["per_dimension"]:
                raise MissingField(".".join(base + [dim]), "field absent")
            cell = entry["per_dimension"][dim]
            if not isinstance(cell, dict) or "abs_change" not in cell:
                raise MissingField(".".join(base + [dim, "abs_change"]), "field absent")
            value = num(cell, ["abs_change"])
            if worst is None or value > worst:
                worst = value
                where = "%s/%s" % (entry.get("dropped_family", "family[%d]" % index), dim)
    if worst is None:
        raise MissingField("leave_one_family_out", "carries no per-dimension change")
    return worst, where, "leave_one_family_out"


def read_n3_2(n3: Any, source: str = "--n3") -> Dict[str, Any]:
    try:
        max_change, where, field = _max_lofo_change(n3)
    except MissingField as exc:
        return error_reading("N3.2", exc, source)
    max_change = abs(max_change)
    numbers = {"max_lofo_change": max_change, "read_from": field, "worst_cell": where}
    label = where or field
    if max_change <= LOFO_PASS_BAR:
        return reading(
            "N3.2",
            PASS,
            numbers,
            "max |AC2 change| %.4g (%s) <= %.2f" % (max_change, label, LOFO_PASS_BAR),
        )
    if max_change > LOFO_FAIL_BAR:
        return reading(
            "N3.2",
            FAIL,
            numbers,
            "falsifier met: |AC2 change| %.4g (%s) > %.2f"
            % (max_change, label, LOFO_FAIL_BAR),
        )
    return reading(
        "N3.2",
        MISS,
        numbers,
        "max |AC2 change| %.4g (%s) is above %.2f but not above %.2f"
        % (max_change, label, LOFO_PASS_BAR, LOFO_FAIL_BAR),
    )


def read_n1(r11: str, r12: str) -> Dict[str, Any]:
    numbers = {"N1.1": r11, "N1.2": r12}
    if r11 == FAIL:
        return reading("N1", FAIL, numbers, "N1.1 FAIL")
    if r11 == ERROR or r12 == ERROR:
        return reading(
            "N1",
            ERROR,
            numbers,
            "ERROR (never KILL): a conjunct could not be read (N1.1=%s, N1.2=%s)"
            % (r11, r12),
        )
    if r11 == PASS and r12 == PASS:
        return reading("N1", PASS, numbers, "N1.1 PASS and N1.2 PASS")
    return reading("N1", MISS, numbers, "N1.1=%s, N1.2=%s" % (r11, r12))


def read_n3(r31: str, r32: str) -> Dict[str, Any]:
    numbers = {"N3.1": r31, "N3.2": r32}
    if r31 == FAIL or r32 == FAIL:
        return reading("N3", FAIL, numbers, "N3.1=%s, N3.2=%s (a conjunct FAILs)" % (r31, r32))
    if r31 == ERROR or r32 == ERROR:
        return reading(
            "N3",
            ERROR,
            numbers,
            "ERROR (never KILL): a conjunct could not be read (N3.1=%s, N3.2=%s)"
            % (r31, r32),
        )
    if r31 == PASS and r32 == PASS:
        return reading("N3", PASS, numbers, "N3.1 PASS and N3.2 PASS")
    return reading("N3", MISS, numbers, "N3.1=%s, N3.2=%s" % (r31, r32))


# --------------------------------------------------------------------------
# aggregate
# --------------------------------------------------------------------------
def aggregate(readings: Dict[str, str]) -> Dict[str, Any]:
    """Apply the frozen aggregate rule to the reading table."""
    r11 = readings["N1.1"]
    r12 = readings["N1.2"]
    r1 = readings["N1"]
    r2 = readings["N2"]
    r3 = readings["N3"]
    survivor = [cid for cid in ("N2", "N3") if readings[cid] == PASS]

    if r11 == PASS and r12 == PASS:
        verdict, because = GO, "N1.1 PASS and N1.2 PASS"
    elif r1 == FAIL:
        if survivor:
            verdict = KILL_WITH_SURVIVOR
            because = "N1 FAIL (N1.1 FAIL) but %s PASS" % " and ".join(survivor)
        else:
            verdict = KILL
            because = "N1.1 FAIL and no supporting claim PASSes (N2=%s, N3=%s)" % (r2, r3)
    else:
        verdict = INCONCLUSIVE
        because = (
            "neither the GO criterion nor the N1.1 falsifier is met "
            "(N1.1=%s, N1.2=%s, N1=%s, N2=%s, N3=%s); ERROR is never KILL"
            % (r11, r12, r1, r2, r3)
        )
    return {
        "verdict": verdict,
        "rule": CODED_AGGREGATE,
        "rule_applied": (
            "GO if N1.1 and N1.2 PASS; else if N1 fails: KILL_WITH_SURVIVOR when N2 "
            "or N3 PASS, otherwise KILL (KILL_WITH_SURVIVOR is the refinement of "
            "KILL, so it is tested first); otherwise INCONCLUSIVE"
        ),
        "because": because,
        "readings": dict(readings),
    }


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_input(path: Optional[str], label: str) -> Tuple[Any, Dict[str, Any]]:
    """Load one analysis JSON. A missing/unparseable file yields ERROR readings."""
    record: Dict[str, Any] = {"path": str(path) if path else None, "sha256": None, "error": None}
    if path is None:
        record["error"] = "no %s argument given" % label
        return None, record
    p = Path(path)
    if not p.is_file():
        record["error"] = "file not found: %s" % p
        return None, record
    record["sha256"] = sha256_file(p)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        record["error"] = "unreadable JSON (%s: %s)" % (type(exc).__name__, exc)
        return None, record
    if not isinstance(data, dict):
        record["error"] = "top level is %s, expected an object" % type(data).__name__
        return None, record
    return data, record


def judge(
    prereg_path: Path,
    sha_path: Path,
    n1_path: Optional[str],
    n2_path: Optional[str],
    n3_path: Optional[str],
    n3_revisions: int = 0,
) -> Dict[str, Any]:
    """Verify the freeze and the table, then read every conjunct. Never guesses."""
    digest = verify(prereg_path, sha_path)  # raises FileNotFoundError / FreezeMismatch
    doc = yaml.safe_load(Path(prereg_path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise TableMismatch("frozen preregistration does not parse to a mapping")
    check_table(doc)

    n1_data, n1_rec = load_input(n1_path, "--n1")
    n2_data, n2_rec = load_input(n2_path, "--n2")
    n3_data, n3_rec = load_input(n3_path, "--n3")

    def _unloadable(claim_id: str, rec: Dict[str, Any], label: str) -> Dict[str, Any]:
        return error_reading(claim_id, MissingField("<file>", rec["error"] or "not loaded"), label)

    if n1_data is None:
        r11 = _unloadable("N1.1", n1_rec, "--n1")
        r12 = _unloadable("N1.2", n1_rec, "--n1")
    else:
        r11 = read_n1_1(n1_data)
        r12 = read_n1_2(n1_data)
    r2 = _unloadable("N2", n2_rec, "--n2") if n2_data is None else read_n2(n2_data)
    if n3_data is None:
        r31 = _unloadable("N3.1", n3_rec, "--n3")
        r32 = _unloadable("N3.2", n3_rec, "--n3")
    else:
        r31 = read_n3_1(n3_data, revisions=n3_revisions)
        r32 = read_n3_2(n3_data)

    r1 = read_n1(r11["reading"], r12["reading"])
    r3 = read_n3(r31["reading"], r32["reading"])

    ordered = [r1, r11, r12, r2, r3, r31, r32]
    table = {r["claim_id"]: r["reading"] for r in ordered}
    return {
        "tool": "kyra.g6",
        "tool_version": "v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protocol": {
            "prereg_path": str(prereg_path),
            "prereg_sha256": digest,
            "receipt_path": str(sha_path),
            "receipt_sha256": sha256_file(sha_path),
            "freeze_verified": True,
            "table_check": "coded rule table matches the frozen claim ids, thresholds "
            "and decision_rule prose",
        },
        "inputs": {"n1": n1_rec, "n2": n2_rec, "n3": n3_rec},
        "process_inputs": {
            "n3_revisions": int(n3_revisions),
            "n3_revisions_meaning": "manual judge revisions completed; N3.1's "
            "falsifier ('after one revision') needs >= 1. Not an analysis "
            "statistic - supplied on the command line and recorded here.",
        },
        "readings": ordered,
        "reading_table": table,
        "aggregate": aggregate(table),
        "reading_definitions": CODED_READINGS,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kyra.g6",
        description="Mechanical preregistration judge: verify the freeze, apply the "
        "frozen decision rules to the analysis outputs, write a verdict.",
    )
    p.add_argument("--prereg", required=True, help="frozen preregistration YAML")
    p.add_argument("--sha", required=True, help="freeze receipt written by gates.freeze")
    p.add_argument("--n1", default=None, help="N1 analysis result JSON")
    p.add_argument("--n2", default=None, help="N2 analysis result JSON")
    p.add_argument("--n3", default=None, help="N3 analysis result JSON")
    p.add_argument(
        "--n3-revisions",
        type=int,
        default=0,
        help="manual judge revisions completed (default 0); N3.1's falsifier "
        "reads 'after one revision', so a CI upper bound below 0.70 is only a "
        "FAIL when this is >= 1",
    )
    p.add_argument("--out", required=True, help="verdict JSON path to write")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    prereg_path = Path(args.prereg)
    sha_path = Path(args.sha)

    if args.n3_revisions < 0:
        sys.stderr.write("ERROR: --n3-revisions must be >= 0\n")
        return EXIT_MISSING

    try:
        verdict = judge(
            prereg_path, sha_path, args.n1, args.n2, args.n3, n3_revisions=args.n3_revisions
        )
    except FileNotFoundError as exc:
        sys.stderr.write("ERROR MISSING_FILE: %s\n" % exc)
        sys.stderr.write("REFUSED to judge; no verdict written.\n")
        return EXIT_MISSING
    except FreezeMismatch as exc:
        sys.stderr.write(
            "ERROR FREEZE_MISMATCH: %s sha256=%s receipt sha256=%s\n"
            % (exc.prereg_path, exc.actual, exc.recorded)
        )
        sys.stderr.write("REFUSED to judge a tampered protocol; no reading computed.\n")
        return EXIT_MISMATCH
    except TableMismatch as exc:
        sys.stderr.write("ERROR PROTOCOL_TABLE_MISMATCH: %s\n" % exc)
        sys.stderr.write("REFUSED to judge; no reading computed.\n")
        return EXIT_TABLE
    except yaml.YAMLError as exc:
        sys.stderr.write("ERROR PROTOCOL_PARSE: %s\n" % " ".join(str(exc).split()))
        return EXIT_TABLE

    out_path = Path(args.out)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        sys.stderr.write("ERROR WRITE_FAILURE: cannot write %s (%s)\n" % (out_path, exc))
        return EXIT_WRITE

    for r in verdict["readings"]:
        sys.stdout.write("%-5s %-5s %s\n" % (r["claim_id"], r["reading"], r["detail"]))
    agg = verdict["aggregate"]
    sys.stdout.write("AGGREGATE %s: %s\n" % (agg["verdict"], agg["because"]))
    sys.stdout.write("verdict written to %s\n" % out_path)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
