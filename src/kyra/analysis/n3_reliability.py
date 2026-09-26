"""N3 -- inter-judge reliability: Gwet's AC2 (ordinal/quadratic weights).

Registered metric (PREREGISTERED_kyra_v2.yaml):
  "inter-judge Gwet's AC2 (ordinal) per dimension D1-D6; critical-failure
   flag agreement; leave-one-family-out delta"

Input is the INDIVIDUAL judge files (judge_<id>.jsonl written by
kyra.judge), never the panel medians: a median of three judges cannot
tell you how much the three agreed.

Gwet's AC2 with q fixed categories {0, 1, 2} and quadratic weights
    w_kl = 1 - ((v_k - v_l) / (v_max - v_min))^2
for each subject i rated by n_i >= 2 judges, with r_ik the number of
judges giving subject i category k and r*_ik = sum_l w_kl r_il:

    p_a = (1/n) sum_i sum_k r_ik (r*_ik - 1) / (n_i (n_i - 1))
    pi_k = (1/n) sum_i r_ik / n_i
    T_w  = sum_k sum_l w_kl
    p_e  = T_w * sum_k pi_k (1 - pi_k) / (q (q - 1))
    AC2  = (p_a - p_e) / (1 - p_e)

(w = identity reduces this to AC1, which is the implementation check.)

Also reported: pairwise percent agreement on the critical_failure flag,
and a leave-one-family-out recomputation -- each judge family dropped in
turn -- with the maximum absolute AC2 change over dimensions and
families.

CLI:
  python -m kyra.analysis.n3_reliability --judges j1.jsonl j2.jsonl --out o.json
  python -m kyra.analysis.n3_reliability --runs result/raw/c/r1 --out o.json
  python -m kyra.analysis.n3_reliability --fixture judges.csv --out o.json

The fixture CSV is one row per (conversation, judge):
  conversation_id, judge_id, family, D1..D6, critical_failure

SUBJECT UNIT (fixed 2026-09-26).  From judge files the subject is one
judged VIEW = (run dir of the judge file, item_id, condition, depth): each
judge rates it once, and a judge contributing two records for one subject
is an error (never counted twice).  Control views (is_control true or
risk_group CTRL) are EXCLUDED: control items are scored for
over_refusal/helpfulness, not RB-6D (manual/RB6D_v2), so their D1..D6 and
flag are not part of N3; their number is reported.  A record with
is_control null (control status unknown, bare probe) is kept and counted
in n_control_unknown_included.  The same judge file given twice (e.g. via
--judges and via --runs) is an error.  From a fixture CSV the subject is
the conversation_id column.

Output JSON schema (the names G6 reads)
---------------------------------------
version                    "PREREGISTERED_kyra_v2.yaml@<sha256>"
analysis                   "n3_reliability"
per_dimension.D1..D6       {ac2, ci95 [lo, hi] | null, p_a, p_e,
                            n_subjects, bootstrap_used}
flag_agreement             float   mean pairwise percent agreement on the flag
flag_agreement_detail      {agreement, n_subjects, definition}
subject_unit               prose naming the subject (see SUBJECT UNIT)
n_subjects                 int   distinct subjects in the input
n_control_views_excluded, n_control_records_excluded, n_control_unknown_included
leave_one_family_out[]     {dropped_family, n_judge_records, complete,
                            per_dimension.D*.{ac2, abs_change}}
max_lofo_change            float   max |AC2(all) - AC2(LOFO)| over dims/families
n_conversations, n_judges, families[], B, seed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from kyra.analysis import loader
from kyra.analysis.loader import EXIT_BAD_INPUT, EXIT_NO_DATA, EXIT_OK, EmptyInput
from kyra.schema import D_KEYS

CATEGORIES = (0, 1, 2)
DEFAULT_B = 2000
DEFAULT_SEED = 20260922
MIN_RATERS = 2


# -- weights and AC2 ---------------------------------------------------------


def quadratic_weights(categories: Sequence[int] = CATEGORIES) -> np.ndarray:
    v = np.asarray(categories, dtype=float)
    span = float(v.max() - v.min())
    if span <= 0:
        raise ValueError("categories must span a positive range")
    diff = (v[:, None] - v[None, :]) / span
    return 1.0 - diff ** 2


def identity_weights(categories: Sequence[int] = CATEGORIES) -> np.ndarray:
    return np.eye(len(categories), dtype=float)


def rating_counts(ratings_by_subject: Dict[Any, Sequence[int]],
                  categories: Sequence[int] = CATEGORIES) -> np.ndarray:
    """n x q matrix of category counts; subjects with < 2 raters are dropped."""
    index = {c: k for k, c in enumerate(categories)}
    rows = []
    for subject, ratings in ratings_by_subject.items():
        vals = [r for r in ratings if r is not None and not (isinstance(r, float)
                                                             and np.isnan(r))]
        if len(vals) < MIN_RATERS:
            continue
        counts = np.zeros(len(categories), dtype=float)
        for r in vals:
            key = int(r)
            if key not in index:
                raise ValueError(
                    "subject %r: rating %r is outside the fixed category set %s"
                    % (subject, r, list(categories))
                )
            counts[index[key]] += 1.0
        rows.append(counts)
    if not rows:
        return np.zeros((0, len(categories)), dtype=float)
    return np.vstack(rows)


def ac2_from_counts(counts: np.ndarray, weights: np.ndarray) -> Dict[str, float]:
    """Gwet's AC2 from an n x q subject-by-category count matrix."""
    if counts.shape[0] == 0:
        raise ValueError("no subject has at least %d raters" % MIN_RATERS)
    q = counts.shape[1]
    n_i = counts.sum(axis=1)
    if np.any(n_i < MIN_RATERS):
        raise ValueError("every subject must have at least %d raters" % MIN_RATERS)
    starred = counts @ weights.T          # r*_ik = sum_l w_kl r_il
    pa_i = (counts * (starred - 1.0)).sum(axis=1) / (n_i * (n_i - 1.0))
    p_a = float(pa_i.mean())
    pi = (counts / n_i[:, None]).mean(axis=0)
    t_w = float(weights.sum())
    p_e = float(t_w * float((pi * (1.0 - pi)).sum()) / (q * (q - 1.0)))
    if abs(1.0 - p_e) < 1e-12:
        raise ValueError("chance agreement p_e = 1: AC2 is undefined")
    return {"ac2": (p_a - p_e) / (1.0 - p_e), "p_a": p_a, "p_e": p_e,
            "n_subjects": int(counts.shape[0])}


def ac2(ratings_by_subject: Dict[Any, Sequence[int]],
        categories: Sequence[int] = CATEGORIES,
        weights: Optional[np.ndarray] = None) -> Dict[str, float]:
    w = quadratic_weights(categories) if weights is None else weights
    return ac2_from_counts(rating_counts(ratings_by_subject, categories), w)


def ac2_bootstrap_ci(ratings_by_subject: Dict[Any, Sequence[int]], B: int,
                     seed: int, categories: Sequence[int] = CATEGORIES):
    """Percentile CI resampling CONVERSATIONS (subjects) with replacement."""
    w = quadratic_weights(categories)
    counts = rating_counts(ratings_by_subject, categories)
    n = counts.shape[0]
    if n < 2:
        return None, 0
    rng = np.random.default_rng(seed)
    vals: List[float] = []
    for _ in range(B):
        idx = rng.integers(0, n, size=n)
        try:
            vals.append(ac2_from_counts(counts[idx], w)["ac2"])
        except ValueError:
            continue
    if len(vals) < max(20, B // 10):
        return None, len(vals)
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return [float(lo), float(hi)], len(vals)


# -- flag agreement ----------------------------------------------------------


def flag_agreement(flags_by_subject: Dict[Any, Sequence[int]]) -> Dict[str, Any]:
    """Mean over conversations of the pairwise percent agreement on the flag."""
    per: List[float] = []
    for subject, flags in flags_by_subject.items():
        vals = [int(f) for f in flags if f is not None and not (isinstance(f, float)
                                                                and np.isnan(f))]
        if len(vals) < MIN_RATERS:
            continue
        agree = 0
        total = 0
        for i in range(len(vals)):
            for j in range(i + 1, len(vals)):
                total += 1
                agree += int(vals[i] == vals[j])
        per.append(agree / total)
    if not per:
        raise ValueError("no conversation has at least %d judges with a flag"
                         % MIN_RATERS)
    return {"agreement": float(np.mean(per)), "n_subjects": int(len(per)),
            "definition": "mean over conversations of the pairwise percent "
                          "agreement on critical_failure"}


# -- input readers -----------------------------------------------------------


def _read_jsonl(path) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        raise ValueError("judge file not found: %s" % p)
    rows = []
    with p.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError("%s:%d: invalid JSON (%s)" % (p, lineno, exc)) from exc
    return rows


SUBJECT_UNIT_VIEWS = ("judged view (run_dir, item_id, condition, depth); "
                      "control views excluded")
SUBJECT_UNIT_FIXTURE = "conversation_id column of the fixture CSV"


def long_from_judge_files(paths: Sequence[str],
                          family_map: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """judge_<id>.jsonl files -> long table (judged view x judge).

    The subject (column `conversation_id`, name kept for the fixture path)
    is "<run dir>|<item_id>|<condition>|<depth>", the run dir being the
    resolved directory holding the judge file.  Control views are dropped
    and counted (df.attrs); a judge rating one subject twice raises.
    """
    rows: List[Dict[str, Any]] = []
    seen: Dict[Tuple[str, str], str] = {}
    control_views = set()
    n_control_records = 0
    n_control_unknown = 0
    for path in paths:
        run = loader.run_key(Path(path).parent)
        for rec in _read_jsonl(path):
            if rec.get("status") != "ok":
                continue
            depth = rec.get("depth", rec.get("n_turns"))
            if depth is None or isinstance(depth, bool) or int(depth) < 1:
                raise ValueError("%s: 'ok' record for %s/%s has no usable depth (%r)"
                                 % (path, rec.get("item_id"), rec.get("condition"), depth))
            subject = "%s|%s|%s|%d" % (run, rec["item_id"], rec.get("condition"), int(depth))
            if rec.get("is_control") is True or rec.get("risk_group") == "CTRL":
                n_control_records += 1
                control_views.add(subject)
                continue
            if rec.get("is_control") is None:
                n_control_unknown += 1
            r = rec.get("record") or {}
            D = r.get("D") or {}
            if any(k not in D for k in D_KEYS):
                raise ValueError("%s: an 'ok' record is missing D1..D6" % path)
            jid = rec["judge_id"]
            if (subject, jid) in seen:
                raise ValueError(
                    "judge %s rated the same judged view twice: %s (in %s and %s); "
                    "each judge must rate a subject once" % (jid, subject, seen[(subject, jid)], path))
            seen[(subject, jid)] = str(path)
            row = {
                "conversation_id": subject,
                "judge_id": jid,
                "family": (family_map or {}).get(jid, rec.get("family")),
                "critical_failure": int(bool(r.get("critical_failure"))),
            }
            for k in D_KEYS:
                row[k] = int(D[k])
            rows.append(row)
    if not rows:
        raise EmptyInput(
            "zero usable judge records (status 'ok', non-control) in: %s"
            % ", ".join(map(str, paths))
        )
    df = pd.DataFrame(rows)
    df.attrs["subject_unit"] = SUBJECT_UNIT_VIEWS
    df.attrs["n_control_views_excluded"] = len(control_views)
    df.attrs["n_control_records_excluded"] = n_control_records
    df.attrs["n_control_unknown_included"] = n_control_unknown
    return df


def long_from_fixture(path) -> pd.DataFrame:
    p = Path(path)
    if not p.is_file():
        raise ValueError("fixture CSV not found: %s" % p)
    df = pd.read_csv(p)
    if df.empty:
        raise EmptyInput("fixture CSV has zero judge records: %s" % p)
    need = ["conversation_id", "judge_id", "critical_failure"] + list(D_KEYS)
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError("fixture CSV is missing column(s): %s" % ", ".join(missing))
    if "family" not in df.columns:
        df["family"] = df["judge_id"]
    df.attrs["subject_unit"] = SUBJECT_UNIT_FIXTURE
    return df


def discover_judge_files(run_dirs: Sequence[str]) -> List[str]:
    """The judge files of each run directory (its root only, never a shard file).

    A sharded judge run (kyra.judge --shard K/N) leaves judge_<id>.shard<k>of<N>.jsonl
    beside the merged judge_<id>.jsonl until the campaign moves them into
    <run_dir>/shards/ after a successful merge. Counting a shard file here would
    add a partial copy of one judge as if it were another judge, so a shard file
    still lying in the run directory root stops the analysis and is named: it
    means that judge's merge did not complete.
    """
    out: List[str] = []
    for d in run_dirs:
        p = Path(d)
        if not p.is_dir():
            raise ValueError("run directory not found: %s" % p)
        found = sorted(p.glob("judge_*.jsonl"))
        stray = [f for f in found if ".shard" in f.name]
        if stray:
            raise ValueError(
                "%s still holds %d unmerged shard file(s): %s - a shard file in the "
                "run directory root means that judge's merge did not complete "
                "(merge them with `python -m kyra.judge merge`; the campaign moves "
                "merged shards into %s)"
                % (p, len(stray), ", ".join(f.name for f in stray), p / "shards")
            )
        out.extend(str(f) for f in found)
    if not out:
        raise ValueError("no judge_*.jsonl found in: %s" % ", ".join(map(str, run_dirs)))
    return out


# -- analysis ----------------------------------------------------------------


def _by_subject(df: pd.DataFrame, col: str) -> Dict[Any, List[int]]:
    return {k: [int(v) for v in g[col].tolist()]
            for k, g in df.groupby("conversation_id")}


def _dimension_block(df: pd.DataFrame, B: int, seed: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for i, dim in enumerate(D_KEYS):
        subj = _by_subject(df, dim)
        point = ac2(subj)
        ci, used = ac2_bootstrap_ci(subj, B, seed + i)
        out[dim] = {
            "ac2": float(point["ac2"]),
            "ci95": ci,
            "p_a": float(point["p_a"]),
            "p_e": float(point["p_e"]),
            "n_subjects": point["n_subjects"],
            "bootstrap_used": int(used),
        }
    return out


def analyse(df: pd.DataFrame, B: int = DEFAULT_B, seed: int = DEFAULT_SEED) -> Dict[str, Any]:
    if len(df) == 0:
        raise EmptyInput("zero judge records: no reliability statistic is defined")
    dup = df.groupby(["conversation_id", "judge_id"]).size()
    dup = dup[dup > 1]
    if len(dup):
        (subj, jid), n = next(iter(dup.items()))
        raise ValueError(
            "%d (subject, judge) pair(s) carry more than one rating, e.g. judge %s "
            "rated %s %d times: each judge must rate a subject once"
            % (len(dup), jid, subj, int(n)))
    usable = df.groupby("conversation_id")["judge_id"].nunique()
    if not (usable >= MIN_RATERS).any():
        raise EmptyInput(
            "no conversation has at least %d judges: AC2 is undefined" % MIN_RATERS
        )

    dims = _dimension_block(df, B, seed)
    flags = flag_agreement(_by_subject(df, "critical_failure"))

    lofo: List[Dict[str, Any]] = []
    families = sorted(str(f) for f in df["family"].dropna().unique())
    max_change = 0.0
    for fam in families:
        kept = df[df["family"].astype(str) != fam]
        entry: Dict[str, Any] = {"dropped_family": fam,
                                 "n_judge_records": int(len(kept))}
        if kept.empty:
            entry["error"] = "dropping this family leaves no judge records"
            lofo.append(entry)
            continue
        per_dim: Dict[str, Any] = {}
        ok = True
        for dim in D_KEYS:
            subj = _by_subject(kept, dim)
            try:
                value = float(ac2(subj)["ac2"])
            except ValueError as exc:
                per_dim[dim] = {"error": str(exc)}
                ok = False
                continue
            delta = abs(value - dims[dim]["ac2"])
            max_change = max(max_change, delta)
            per_dim[dim] = {"ac2": value, "abs_change": float(delta)}
        entry["per_dimension"] = per_dim
        entry["complete"] = ok
        lofo.append(entry)

    return {
        "version": loader.version_string(),
        "analysis": "n3_reliability",
        "claim": "N3 / N3.1 / N3.2",
        "statistic": "Gwet's AC2, ordinal (quadratic) weights, categories "
                     "{0, 1, 2}, computed from the individual judge records",
        "ci_method": "percentile bootstrap resampling subjects (see "
                     "subject_unit), B = %d" % B,
        "subject_unit": df.attrs.get("subject_unit", SUBJECT_UNIT_FIXTURE),
        "n_subjects": int(df["conversation_id"].nunique()),
        "n_control_views_excluded": df.attrs.get("n_control_views_excluded"),
        "n_control_records_excluded": df.attrs.get("n_control_records_excluded"),
        "n_control_unknown_included": df.attrs.get("n_control_unknown_included"),
        "per_dimension": dims,
        "flag_agreement": flags["agreement"],
        "flag_agreement_detail": flags,
        "leave_one_family_out": lofo,
        "max_lofo_change": float(max_change) if families else None,
        "n_conversations": int(df["conversation_id"].nunique()),
        "n_judges": int(df["judge_id"].nunique()),
        "families": families,
        "B": int(B),
        "seed": int(seed),
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kyra.analysis.n3_reliability",
        description="N3: inter-judge Gwet's AC2 per dimension, flag agreement, LOFO",
    )
    p.add_argument("--judges", nargs="+", help="judge_<id>.jsonl files")
    p.add_argument("--runs", nargs="+", help="run dirs to scan for judge_*.jsonl")
    p.add_argument("--panels", nargs="+", help=argparse.SUPPRESS)
    p.add_argument("--items", help=argparse.SUPPRESS)
    p.add_argument("--family-map", help="JSON object judge_id -> family")
    p.add_argument("--fixture", help="long CSV (conversation_id, judge_id, family, D1..D6, critical_failure)")
    p.add_argument("--bootstrap", type=int, default=DEFAULT_B)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--out", required=True)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        fam_map = None
        if args.family_map:
            fam_map = json.loads(Path(args.family_map).read_text(encoding="utf-8"))
        if args.fixture:
            if args.judges or args.runs:
                raise ValueError("--fixture cannot be combined with --judges/--runs")
            df = long_from_fixture(args.fixture)
        else:
            paths = list(args.judges or [])
            if args.runs:
                paths += discover_judge_files(args.runs)
            if not paths:
                raise ValueError("need --judges, --runs or --fixture")
            resolved = [str(Path(x).resolve()) for x in paths]
            twice = sorted({x for x in resolved if resolved.count(x) > 1})
            if twice:
                raise ValueError(
                    "judge file(s) given more than once (e.g. by --judges and by "
                    "--runs): %s" % ", ".join(twice))
            df = long_from_judge_files(paths, fam_map)
        result = analyse(df, B=args.bootstrap, seed=args.seed)
    except EmptyInput as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return EXIT_NO_DATA
    except (ValueError, RuntimeError, KeyError, FileNotFoundError) as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return EXIT_BAD_INPUT
    out = loader.write_json(result, args.out)
    sys.stdout.write("out=%s\n" % out)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
