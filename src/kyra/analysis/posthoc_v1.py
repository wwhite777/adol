"""POST-HOC SENSITIVITY analyses of the phase-A outputs (not confirmatory).

Requested by the external pre-submission review of the JKIICE manuscript
(2026-09-27). The frozen confirmatory results (result/analysis/phaseA_T1/
20260926T0213Z/) are NOT changed; outcomes had already been read when this
module was written, so every number here is post hoc and labelled so.

Sections (one JSON + one or more CSVs each, under
result/analysis/phaseA_T1/posthoc_<UTC stamp>/):

(a) judge validity, main runs: views with 3 / 2 / <2 valid judges, split
    votes, CF flags (total / complete panels / tie rule), judge ERROR counts
    by type, by arm (N1 risk / benign twin) x depth 1..6, plus summary rows.
(b) N1 sensitivity: the frozen N1 estimator (kyra.analysis.n1_escalation.
    analyse via kyra.analysis.loader.build_tidy, unchanged, default B and
    seed) re-run under alternative CF labelings built from the per-view
    judge records:
      S0 original panel labels (reproduction check against the frozen n1.json)
      S1 complete panels only (views without 3 valid judges dropped)
      S2 ties unresolved (views whose panel CF came from cf_tie dropped)
      S3 ties = non-critical (majority of valid judges; a 1-1 split -> false)
    A dropped view is written as status "INSUFFICIENT" in a rewritten
    panel.jsonl inside a run dir of symlinks (manifest.jsonl, responses.jsonl)
    under the output folder. Crude (marginal 2x2) ORs are reported as well.
(c) N3 sensitivity: judge agreement on RISK views (controls excluded, as in
    the frozen n3) for the 5 main runs and for all 20 runs, with a
    CONVERSATION-cluster bootstrap (cluster = (run_dir, item_id, condition),
    all its depth views move together). Gwet AC2 via kyra.analysis.
    n3_reliability; CF flag mean pairwise agreement, pooled positive / negative
    specific agreement PA = 2a/(2a+b+c), NA = 2d/(2d+b+c), views flagged by
    0/1/2/3 judges.
(d) length and truncation, main runs, N1 population, depths 1/3/6:
    transcript / response character lengths, the J3 (Phi-4) first-attempt
    prompt token count rebuilt with kyra.judge.build_judge_prompt (checked
    against each record's prompt_sha256) and the Phi-4 tokenizer, per-judge
    ERROR rates, and a scan for any stored target finish reason / token count.

Valid judge = a judge_<id>.jsonl record with status "ok" for that view.

CLI:
  PYTHONPATH=src python -m kyra.analysis.posthoc_v1 [--sections abcd]
      [--bootstrap 2000] [--out-root result/analysis/phaseA_T1]

Never writes under result/raw/. Exit codes: 0 ok | 4 bad input.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from kyra import judge as kjudge
from kyra import panel as kpanel
from kyra.analysis import loader
from kyra.analysis import n1_escalation as n1
from kyra.analysis import n3_reliability as n3
from kyra.schema import D_KEYS

LABEL = "POST-HOC SENSITIVITY (not confirmatory)"
README_HEADER = "POST-HOC SENSITIVITY — not confirmatory"
JUDGE_IDS = ("J1", "J2", "J3")
ARMS = ("risk", "benign")
N1_DEPTHS = (1, 3, 6)
SCHEMES = ("S0", "S1", "S2", "S3")
SCHEME_TEXT = {
    "S0": "original panel labels (unchanged panel.jsonl; reproduction check)",
    "S1": "complete panels only: views without 3 valid judges dropped (INSUFFICIENT)",
    "S2": "ties unresolved: views whose panel CF came from cf_tie dropped (INSUFFICIENT)",
    "S3": "ties = non-critical: CF = strict majority of valid judges, a 1-1 split -> false",
}
N3_SEED = 20260922
J3_CONTEXT = 16384
J3_MAX_NEW = 700
J3_THRESHOLD = J3_CONTEXT - J3_MAX_NEW

REPO = Path(__file__).resolve().parents[3]
DEFAULT_ROOT = "result/raw/phaseA_T1"
DEFAULT_ITEMS = "research/items/items_phaseA_v1.jsonl"
DEFAULT_FROZEN = "result/analysis/phaseA_T1/20260926T0213Z"
DEFAULT_FAMILY_MAP = "result/raw/phaseA_T1/family_map_phaseA_T1.json"
DEFAULT_JUDGES_CONFIG = "research/judges_phaseA_v1.json"
DEFAULT_ANCHORS = "research/judge_anchors_v1.json"
DEFAULT_OUT_ROOT = "result/analysis/phaseA_T1"
EXCLUDED_MAIN = "LGAI-EXAONE-EXAONE-4.0-32B-AWQ/main/20260922T1239Z-b936cd"


# -- inputs --------------------------------------------------------------------


def discover_runs(root) -> Tuple[List[str], List[str]]:
    """(main run dirs, all scored run dirs): dirs holding panel.jsonl AND MARKER."""
    r = Path(root)
    scored = sorted(str(d) for d in r.glob("*/*/*")
                    if d.is_dir() and (d / "panel.jsonl").is_file() and (d / "MARKER").is_file())
    main = [d for d in scored if Path(d).parent.name == "main"]
    return main, scored


def check_runs(main: Sequence[str], scored: Sequence[str]) -> None:
    models = {Path(d).parent.parent.name for d in main}
    if len(main) != 5 or len(models) != 5:
        raise ValueError("expected exactly 5 main run dirs over 5 models, got %d over %d"
                         % (len(main), len(models)))
    if len(scored) != 20:
        raise ValueError("expected 20 scored run dirs, got %d" % len(scored))
    if any(d.endswith(EXCLUDED_MAIN) for d in scored):
        raise ValueError("the excluded EXAONE main run is among the inputs")


def load_items_raw(path) -> Dict[str, Dict[str, Any]]:
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                out[rec["item_id"]] = rec
    return out


def arm_of(item: Dict[str, Any]) -> str:
    """risk (LOC/LIT, risk_group != CTRL) | benign (BEN twin) | control (CTRL)."""
    _, suffix = loader.split_item_id(item["item_id"])
    if suffix == "BEN":
        return "benign"
    if item["risk_group"] == "CTRL":
        return "control"
    return "risk"


def n1_population(items: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    """item_id -> arm for the 24 six-turn localized LOC scripts and their BEN twins."""
    risk = {i for i, it in items.items()
            if loader.split_item_id(i)[1] == "LOC" and it["risk_group"] != "CTRL"
            and it.get("localization") == "localized" and len(it["turns"]) == 6}
    bases = {loader.split_item_id(i)[0] for i in risk}
    ben = {i for i in items if loader.split_item_id(i)[1] == "BEN"
           and loader.split_item_id(i)[0] in bases}
    out = {i: "risk" for i in risk}
    out.update({i: "benign" for i in ben})
    return out


def load_views(run_dir) -> Dict[Tuple[str, str, int], Dict[str, Any]]:
    """(item_id, condition, depth) -> {"judges": {jid: record}, "panel": record}."""
    d = Path(run_dir)
    views: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
    for rec in loader._read_jsonl(d / "panel.jsonl"):
        key = (rec["item_id"], rec["condition"], int(rec["depth"]))
        if key in views:
            raise ValueError("%s: duplicate panel view %s" % (d, key))
        views[key] = {"judges": {}, "panel": rec}
    for jid in JUDGE_IDS:
        for rec in kpanel.load_judge_file(d / ("judge_%s.jsonl" % jid)):
            key = (rec["item_id"], rec["condition"], int(rec["depth"]))
            if key not in views:
                raise ValueError("%s: judge %s view %s has no panel record" % (d, jid, key))
            if jid in views[key]["judges"]:
                raise ValueError("%s: judge %s rated %s twice" % (d, jid, key))
            views[key]["judges"][jid] = rec
    return views


# -- per-view summaries ---------------------------------------------------------


def classify_error(error: Optional[str]) -> str:
    text = str(error or "")
    if text.startswith("ProviderError"):
        return "provider"
    if "Unterminated string" in text:
        return "truncated"
    return "other_parse"


def valid_flags(view: Dict[str, Any]) -> List[bool]:
    return [bool(r["record"]["critical_failure"])
            for jid, r in sorted(view["judges"].items()) if r["status"] == "ok"]


def majority_strict(flags: Sequence[bool]) -> bool:
    """S3 rule: CF only on a strict majority of valid judges (a 1-1 split -> False)."""
    n_true = sum(1 for f in flags if f)
    return n_true > len(flags) - n_true


def view_summary(view: Dict[str, Any]) -> Dict[str, Any]:
    flags = valid_flags(view)
    p = view["panel"]
    ok = p["status"] == "ok"
    cf = bool(ok and p["critical_failure"])
    tie = bool(ok and p.get("cf_tie"))
    n_valid = len(flags)
    errors = {jid: (classify_error(r.get("error")) if r["status"] != "ok" else None)
              for jid, r in view["judges"].items()}
    return {
        "n_valid": n_valid,
        "n_flagged": sum(1 for f in flags if f),
        "split2": n_valid == 2 and len(set(flags)) == 2,
        "split3": n_valid == 3 and len(set(flags)) == 2,
        "panel_ok": ok,
        "cf": cf,
        "cf_tie": tie,
        "errors": errors,
        "panel_n_used": len(p.get("judges_used") or []),
    }


def validity_counts(summaries: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    c: Dict[str, Any] = {
        "n_views": 0, "n_valid3": 0, "n_valid2": 0, "n_valid_lt2": 0,
        "split_2valid_1to1": 0, "split_3valid_not_unanimous": 0,
        "cf_flags_total": 0, "cf_from_complete_3valid": 0, "cf_from_tie_rule": 0,
        "cf_from_2valid_unanimous": 0,
    }
    for jid in JUDGE_IDS:
        for kind in ("provider", "truncated", "other_parse", "total"):
            c["%s_err_%s" % (jid, kind)] = 0
    for s in summaries:
        c["n_views"] += 1
        if s["n_valid"] == 3:
            c["n_valid3"] += 1
        elif s["n_valid"] == 2:
            c["n_valid2"] += 1
        else:
            c["n_valid_lt2"] += 1
        c["split_2valid_1to1"] += int(s["split2"])
        c["split_3valid_not_unanimous"] += int(s["split3"])
        if s["cf"]:
            c["cf_flags_total"] += 1
            if s["cf_tie"]:
                c["cf_from_tie_rule"] += 1
            elif s["n_valid"] == 3:
                c["cf_from_complete_3valid"] += 1
            else:
                c["cf_from_2valid_unanimous"] += 1
        for jid, kind in s["errors"].items():
            if kind is not None:
                c["%s_err_%s" % (jid, kind)] += 1
                c["%s_err_total" % jid] += 1
    return c


def consistency(summaries: Iterable[Dict[str, Any]], views: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """Judge-file valid count vs panel judges_used; recomputed flag vs panel flag."""
    n_used_mismatch = 0
    flag_mismatch = 0
    for s, v in zip(summaries, views):
        if s["panel_n_used"] != (s["n_valid"] if s["n_valid"] >= 2 else 0):
            n_used_mismatch += 1
        if s["panel_ok"]:
            flags = valid_flags(v)
            n_true = sum(flags)
            expect = True if n_true * 2 == len(flags) else n_true * 2 > len(flags)
            if expect != bool(v["panel"]["critical_failure"]):
                flag_mismatch += 1
    return {"views_valid_count_ne_panel_judges_used": n_used_mismatch,
            "views_panel_flag_ne_recomputed_majority": flag_mismatch}


# -- (a) --------------------------------------------------------------------------


def section_a(main_runs: Sequence[str], items, pop) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    by_cell: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
    by_summary: Dict[str, List[Dict[str, Any]]] = {
        "ALL_risk_views_LOC+LIT_all_lengths_all_depths": [],
        "ALL_control_views_risk_group_CTRL_BEN+CTRL": [],
        "ALL_BEN_views_all_depths": [],
        "ALL_CTRL_single_turn_views": [],
    }
    all_s, all_v = [], []
    for run in main_runs:
        for key, view in load_views(run).items():
            s = view_summary(view)
            all_s.append(s)
            all_v.append(view)
            item_id = key[0]
            arm = arm_of(items[item_id])
            if item_id in pop:
                by_cell.setdefault((pop[item_id], key[2]), []).append(s)
            if arm == "risk":
                by_summary["ALL_risk_views_LOC+LIT_all_lengths_all_depths"].append(s)
            else:
                by_summary["ALL_control_views_risk_group_CTRL_BEN+CTRL"].append(s)
                if arm == "benign":
                    by_summary["ALL_BEN_views_all_depths"].append(s)
                else:
                    by_summary["ALL_CTRL_single_turn_views"].append(s)
    rows: List[Dict[str, Any]] = []
    for arm in ARMS:
        for depth in range(1, 7):
            row = {"row": "N1_%s" % arm, "arm": arm, "depth": depth,
                   "n1_depth": depth in N1_DEPTHS}
            row.update(validity_counts(by_cell.get((arm, depth), [])))
            rows.append(row)
    for name, ss in by_summary.items():
        row = {"row": name, "arm": "summary", "depth": "all", "n1_depth": False}
        row.update(validity_counts(ss))
        rows.append(row)
    result = {
        "label": LABEL,
        "section": "a_judge_validity",
        "runs": list(main_runs),
        "population": "N1 rows: the 24 six-turn localized LOC risk scripts (arm risk) and "
                      "their item-paired BEN twins (arm benign) x 5 main runs; summary rows "
                      "cover every view of the 5 main runs",
        "definitions": {
            "valid_judge": "judge_<id>.jsonl record with status 'ok' for the view",
            "split_2valid_1to1": "exactly 2 valid judges and they disagree on CF",
            "split_3valid_not_unanimous": "3 valid judges, CF vote 2-1",
            "cf_flags_total": "panel.jsonl critical_failure true (status ok)",
            "cf_from_complete_3valid": "panel CF true, 3 valid judges",
            "cf_from_tie_rule": "panel CF true with cf_tie true (2 valid judges split 1-1)",
            "cf_from_2valid_unanimous": "panel CF true, 2 valid judges both true",
            "err_provider": "error starts with 'ProviderError' (all observed: context length)",
            "err_truncated": "error contains 'Unterminated string' (judge output cut off)",
            "err_other_parse": "any other JudgeParseError",
        },
        "consistency_checks": consistency(all_s, all_v),
        "rows": rows,
    }
    return result, rows


# -- (b) --------------------------------------------------------------------------


def _insufficient(rec: Dict[str, Any], reason: str) -> Dict[str, Any]:
    out = dict(rec)
    for k in ("D", "A", "critical_failure", "cf_codes", "cf_tie", "over_refusal",
              "over_refusal_tie", "helpfulness", "n_turns"):
        out[k] = None
    out["status"] = kpanel.STATUS_INSUFFICIENT
    out["reason"] = reason
    return out


def relabel(view: Dict[str, Any], scheme: str) -> Dict[str, Any]:
    """The panel record of one view under a labeling scheme (S0..S3)."""
    rec = dict(view["panel"])
    if scheme == "S0" or rec["status"] != "ok":
        return rec
    flags = valid_flags(view)
    if scheme == "S1":
        if len(flags) < 3:
            return _insufficient(rec, "posthoc S1: %d valid judge(s), complete panel "
                                      "required" % len(flags))
        return rec
    if scheme == "S2":
        if rec.get("cf_tie"):
            return _insufficient(rec, "posthoc S2: CF came from the tie rule (unresolved)")
        return rec
    if scheme == "S3":
        new_flag = majority_strict(flags)
        if new_flag != bool(rec["critical_failure"]):
            rec["critical_failure"] = new_flag
            rec["cf_codes"] = []
            rec["reason"] = "posthoc S3: 1-1 split relabelled non-critical"
        return rec
    raise ValueError("unknown scheme %r" % scheme)


def write_relabeled_runs(main_runs: Sequence[str], scheme: str, out_dir) -> Tuple[List[str], List[str], Dict[str, int]]:
    """Run dirs of symlinks + a rewritten panel.jsonl; returns (runs, panels, change counts)."""
    runs, panels = [], []
    changes = {"views": 0, "dropped": 0, "cf_true_to_false": 0}
    for run in main_runs:
        src = Path(run)
        dst = Path(out_dir) / scheme / src.parent.parent.name
        dst.mkdir(parents=True, exist_ok=False)
        for name in ("manifest.jsonl", "responses.jsonl"):
            os.symlink(os.path.relpath(src.resolve() / name, dst.resolve()), dst / name)
        views = load_views(run)
        with (dst / "panel.jsonl").open("w", encoding="utf-8") as fh:
            for key, view in views.items():
                new = relabel(view, scheme)
                changes["views"] += 1
                if view["panel"]["status"] == "ok" and new["status"] != "ok":
                    changes["dropped"] += 1
                if (view["panel"]["status"] == "ok" and new["status"] == "ok"
                        and view["panel"]["critical_failure"] and not new["critical_failure"]):
                    changes["cf_true_to_false"] += 1
                fh.write(json.dumps({k: new.get(k) for k in kpanel.PANEL_RECORD_FIELDS},
                                    ensure_ascii=False, sort_keys=True) + "\n")
        runs.append(str(dst))
        panels.append(str(dst / "panel.jsonl"))
    return runs, panels, changes


def crude_or(e1: int, n1_: int, e6: int, n6: int) -> Optional[float]:
    """Marginal 2x2 OR (depth d vs depth 1); None when a cell is zero."""
    a, b, c, d = e6, n6 - e6, e1, n1_ - e1
    if min(a, b, c, d) <= 0:
        return None
    return (a / b) / (c / d)


def depth_counts(df: pd.DataFrame) -> Dict[str, Any]:
    """Events and rows per arm and depth, with the frozen estimator's selection."""
    risk = n1._select(df, "LOC")
    risk = risk[risk["risk_group"].astype(str) != "CTRL"]
    ben = n1._select(df, "BEN")
    out: Dict[str, Any] = {}
    for arm, sub in (("risk", risk), ("benign", ben)):
        long = n1.depth_frame(sub, depths=N1_DEPTHS) if len(sub) else pd.DataFrame()
        cell = {}
        for d in N1_DEPTHS:
            part = long[long["depth"] == d] if len(long) else long
            cell["depth%d" % d] = {"events": int(part["y"].sum()) if len(part) else 0,
                                   "rows": int(len(part))}
        cell["conversations_selected"] = int(len(sub))
        for d in (3, 6):
            cell["crude_or_depth%d_vs_1" % d] = crude_or(
                cell["depth1"]["events"], cell["depth1"]["rows"],
                cell["depth%d" % d]["events"], cell["depth%d" % d]["rows"])
        out[arm] = cell
    return out


def _brief(block: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if block is None:
        return {"error": "not computed"}
    if "error" in block:
        return {"error": block["error"]}
    keys = ("or", "ci95", "p_bootstrap", "p_holm", "n_events", "n_rows", "n_scenarios",
            "bootstrap_used", "bootstrap_failures")
    return {k: block.get(k) for k in keys if k in block}


def section_b(main_runs, items_path, family_map_path, out_dir, B: int, seed: int,
              frozen_n1_path, schemes=SCHEMES) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    fam = json.loads(Path(family_map_path).read_text(encoding="utf-8"))
    res: Dict[str, Any] = {
        "label": LABEL, "section": "b_n1_sensitivity", "runs": list(main_runs),
        "estimator": "kyra.analysis.n1_escalation.analyse, unchanged (loader.build_tidy "
                     "-> analyse, as the CLI does), B = %d, seed = %d" % (B, seed),
        "note_dropped_views": "a view dropped as INSUFFICIENT removes that depth's row; "
                              "when the depth-6 view is dropped the conversation's deepest "
                              "view is < 6, so the frozen selection (n_turns >= 6) drops "
                              "the whole conversation, including its depth-1 row",
        "crude_or_definition": "(e_d/(n_d-e_d)) / (e_1/(n_1-e_1)) over pooled rows; "
                               "null when a cell is zero",
        "schemes": {},
    }
    rows = []
    for scheme in schemes:
        runs, panels, changes = write_relabeled_runs(main_runs, scheme, out_dir)
        df = loader.build_tidy(items_path, runs, panels, family_map=fam)
        counts = depth_counts(df)
        entry: Dict[str, Any] = {"definition": SCHEME_TEXT[scheme], "panel_changes": changes,
                                 "counts": counts, "run_dirs": runs}
        try:
            full = n1.analyse(df, B=B, seed=seed)
            entry["risk"] = _brief(full.get("risk"))
            entry["benign"] = _brief(full.get("benign"))
            entry["interaction"] = _brief(full.get("interaction"))
            entry["risk_depth3_vs_1"] = _brief(full.get("risk_depth3_vs_1"))
            entry["full_result"] = full
        except Exception as exc:  # the estimator's own failure is a result here
            entry["error"] = "%s: %s" % (type(exc).__name__, exc)
        res["schemes"][scheme] = entry
        row = {"scheme": scheme, "definition": SCHEME_TEXT[scheme]}
        for arm in ("risk", "benign"):
            for d in N1_DEPTHS:
                row["%s_d%d_events" % (arm, d)] = counts[arm]["depth%d" % d]["events"]
                row["%s_d%d_rows" % (arm, d)] = counts[arm]["depth%d" % d]["rows"]
            row["%s_crude_or_6v1" % arm] = counts[arm]["crude_or_depth6_vs_1"]
            blk = entry.get(arm, {"error": entry.get("error")})
            row["%s_or" % arm] = blk.get("or")
            ci = blk.get("ci95") or [None, None]
            row["%s_ci_lo" % arm], row["%s_ci_hi" % arm] = ci[0], ci[1]
            row["%s_error" % arm] = blk.get("error")
        it = entry.get("interaction", {"error": entry.get("error")})
        row["interaction_or"] = it.get("or")
        ci = it.get("ci95") or [None, None]
        row["interaction_ci_lo"], row["interaction_ci_hi"] = ci[0], ci[1]
        row["interaction_p_holm"] = it.get("p_holm")
        row["interaction_error"] = it.get("error")
        rows.append(row)
    if "S0" in res["schemes"] and "full_result" in res["schemes"]["S0"] and frozen_n1_path:
        frozen = json.loads(Path(frozen_n1_path).read_text(encoding="utf-8"))
        s0 = res["schemes"]["S0"]["full_result"]
        keys = ("or", "ci95", "benign_or", "benign_ci95", "interaction_p", "n")
        res["s0_vs_frozen_n1"] = {
            "frozen_path": str(frozen_n1_path),
            "note": "statsmodels BinomialBayesMixedGLM.fit_vb draws its start values "
                    "from fresh OS entropy (rng=None in the frozen _fit_vb), so a re-run "
                    "of the unchanged estimator is not bit-identical to the frozen "
                    "n1.json; this block quantifies the difference",
            "frozen": {k: frozen.get(k) for k in keys},
            "s0": {k: s0.get(k) for k in keys},
            "bit_equal": {k: s0.get(k) == frozen.get(k) for k in keys},
            "max_rel_diff": {k: _max_rel_diff(s0.get(k), frozen.get(k)) for k in keys},
        }
    return res, rows


def _max_rel_diff(a, b) -> Optional[float]:
    """max |a-b|/|b| over a scalar or a list pair; None when not comparable."""
    xs = a if isinstance(a, list) else [a]
    ys = b if isinstance(b, list) else [b]
    if len(xs) != len(ys) or any(v is None for v in xs + ys):
        return None
    return max(abs(float(x) - float(y)) / abs(float(y)) if float(y) != 0 else abs(float(x))
               for x, y in zip(xs, ys))


# -- (c) --------------------------------------------------------------------------


def cluster_of(subject: str) -> str:
    """'<run>|<item>|<cond>|<depth>' -> '<run>|<item>|<cond>' (one conversation)."""
    return subject.rsplit("|", 1)[0]


def pair_counts(flags: Sequence[int]) -> Tuple[int, int, int]:
    """(a both 1, b+c discordant, d both 0) over all judge pairs of one view."""
    a = bc = d = 0
    for i in range(len(flags)):
        for j in range(i + 1, len(flags)):
            if flags[i] and flags[j]:
                a += 1
            elif flags[i] or flags[j]:
                bc += 1
            else:
                d += 1
    return a, bc, d


def specific_agreement(a: float, bc: float, d: float) -> Tuple[Optional[float], Optional[float]]:
    pa = 2 * a / (2 * a + bc) if (2 * a + bc) > 0 else None
    na = 2 * d / (2 * d + bc) if (2 * d + bc) > 0 else None
    return pa, na


def _ci(vals: List[float]) -> Optional[List[float]]:
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    if not vals:
        return None
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return [float(lo), float(hi)]


def cluster_bootstrap_agreement(df: pd.DataFrame, B: int, seed: int) -> Dict[str, Any]:
    """AC2 per dimension + CF agreement with a conversation-cluster bootstrap.

    One rng draws the resampled clusters for every replicate; the same draw is
    applied to all six dimensions and to the CF statistics.
    """
    subjects = sorted(df["conversation_id"].unique())
    clusters = sorted({cluster_of(s) for s in subjects})
    cidx = {c: k for k, c in enumerate(clusters)}
    by_subj = {k: g for k, g in df.groupby("conversation_id")}
    K = len(clusters)
    w = n3.quadratic_weights()

    # per-dimension count matrices, rows grouped by cluster
    dim_rows: Dict[str, List[np.ndarray]] = {}
    for dim in D_KEYS:
        mats: List[List[np.ndarray]] = [[] for _ in range(K)]
        for s in subjects:
            m = n3.rating_counts({s: [int(v) for v in by_subj[s][dim]]})
            if m.shape[0]:
                mats[cidx[cluster_of(s)]].append(m)
        dim_rows[dim] = [np.vstack(ms) if ms else np.zeros((0, 3)) for ms in mats]

    # CF statistics per cluster
    agree_sum = np.zeros(K)
    n_subj = np.zeros(K)
    pa_a = np.zeros(K)
    pa_bc = np.zeros(K)
    pa_d = np.zeros(K)
    flagged: Dict[str, int] = {}
    for s in subjects:
        flags = [int(v) for v in by_subj[s]["critical_failure"]]
        if len(flags) < n3.MIN_RATERS:
            continue
        k = cidx[cluster_of(s)]
        a, bc, d = pair_counts(flags)
        agree_sum[k] += (a + d) / (a + bc + d)
        n_subj[k] += 1
        pa_a[k] += a
        pa_bc[k] += bc
        pa_d[k] += d
        key = "valid%d_flagged%d" % (len(flags), sum(flags))
        flagged[key] = flagged.get(key, 0) + 1

    point_dims = {}
    for dim in D_KEYS:
        pt = n3.ac2(n3._by_subject(df, dim))
        point_dims[dim] = {"ac2": float(pt["ac2"]), "p_a": float(pt["p_a"]),
                           "p_e": float(pt["p_e"]), "n_subjects": pt["n_subjects"]}
    agree_pt = n3.flag_agreement(n3._by_subject(df, "critical_failure"))
    pa_pt, na_pt = specific_agreement(pa_a.sum(), pa_bc.sum(), pa_d.sum())

    rng = np.random.default_rng(seed)
    boot_dims: Dict[str, List[float]] = {dim: [] for dim in D_KEYS}
    boot_agree, boot_pa, boot_na = [], [], []
    for _ in range(B):
        pick = rng.integers(0, K, size=K)
        for dim in D_KEYS:
            blocks = dim_rows[dim]
            parts = [blocks[i] for i in pick if blocks[i].shape[0]]
            if not parts:
                continue
            try:
                boot_dims[dim].append(n3.ac2_from_counts(np.vstack(parts), w)["ac2"])
            except ValueError:
                continue
        ns = n_subj[pick].sum()
        if ns > 0:
            boot_agree.append(float(agree_sum[pick].sum() / ns))
        pa_b, na_b = specific_agreement(pa_a[pick].sum(), pa_bc[pick].sum(), pa_d[pick].sum())
        boot_pa.append(pa_b)
        boot_na.append(na_b)

    for dim in D_KEYS:
        point_dims[dim]["ci95_cluster"] = _ci(boot_dims[dim])
        point_dims[dim]["bootstrap_used"] = len(boot_dims[dim])
    total_flagged: Dict[str, int] = {}
    for key, v in flagged.items():
        nf = key.split("flagged")[1]
        total_flagged["flagged_by_%s" % nf] = total_flagged.get("flagged_by_%s" % nf, 0) + v
    return {
        "n_views": int(len(subjects)),
        "n_clusters": int(K),
        "per_dimension": point_dims,
        "cf_flag": {
            "mean_pairwise_agreement": float(agree_pt["agreement"]),
            "mean_pairwise_agreement_ci95_cluster": _ci(boot_agree),
            "n_views_with_2plus_judges": int(agree_pt["n_subjects"]),
            "pairs_pooled": {"a_both_true": int(pa_a.sum()), "b_plus_c_discordant": int(pa_bc.sum()),
                             "d_both_false": int(pa_d.sum())},
            "positive_specific_agreement_PA": pa_pt,
            "PA_ci95_cluster": _ci(boot_pa),
            "negative_specific_agreement_NA": na_pt,
            "NA_ci95_cluster": _ci(boot_na),
            "views_by_n_judges_flagging": total_flagged,
            "views_by_valid_and_flagging": dict(sorted(flagged.items())),
        },
        "B": int(B),
        "seed": int(seed),
    }


def section_c(main_runs, all_runs, family_map_path, B: int, seed: int,
              frozen_n3_path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    fam = json.loads(Path(family_map_path).read_text(encoding="utf-8"))
    res: Dict[str, Any] = {
        "label": LABEL, "section": "c_n3_cluster_bootstrap",
        "subject_unit": n3.SUBJECT_UNIT_VIEWS,
        "cluster_unit": "conversation = (run_dir, item_id, condition); all its depth views "
                        "are resampled together",
        "statistic": "Gwet AC2, quadratic weights, categories {0,1,2} "
                     "(kyra.analysis.n3_reliability.ac2 / ac2_from_counts)",
        "pa_na_definition": "pooled over all judge pairs of all views with >= 2 valid "
                            "judges: PA = 2a/(2a+b+c), NA = 2d/(2d+b+c)",
        "sets": {},
    }
    rows = []
    for name, runs in (("main_5_runs", main_runs), ("all_20_runs", all_runs)):
        paths = [str(Path(r) / ("judge_%s.jsonl" % j)) for r in runs for j in JUDGE_IDS]
        df = n3.long_from_judge_files(paths, fam)
        block = cluster_bootstrap_agreement(df, B, seed)
        block["runs"] = list(runs)
        block["n_control_views_excluded"] = df.attrs.get("n_control_views_excluded")
        res["sets"][name] = block
        for dim in D_KEYS:
            p = block["per_dimension"][dim]
            ci = p["ci95_cluster"] or [None, None]
            rows.append({"set": name, "statistic": "AC2_%s" % dim, "value": p["ac2"],
                         "ci_lo": ci[0], "ci_hi": ci[1], "n_views": p["n_subjects"],
                         "n_clusters": block["n_clusters"]})
        cf = block["cf_flag"]
        for stat, val, ci in (("CF_mean_pairwise_agreement", cf["mean_pairwise_agreement"],
                               cf["mean_pairwise_agreement_ci95_cluster"]),
                              ("CF_PA", cf["positive_specific_agreement_PA"], cf["PA_ci95_cluster"]),
                              ("CF_NA", cf["negative_specific_agreement_NA"], cf["NA_ci95_cluster"])):
            ci = ci or [None, None]
            rows.append({"set": name, "statistic": stat, "value": val, "ci_lo": ci[0],
                         "ci_hi": ci[1], "n_views": cf["n_views_with_2plus_judges"],
                         "n_clusters": block["n_clusters"]})
    if frozen_n3_path and Path(frozen_n3_path).is_file():
        frozen = json.loads(Path(frozen_n3_path).read_text(encoding="utf-8"))
        allb = res["sets"]["all_20_runs"]
        res["all_20_point_equals_frozen_n3"] = {
            "frozen_path": str(frozen_n3_path),
            "ac2": {d: allb["per_dimension"][d]["ac2"] == frozen["per_dimension"][d]["ac2"]
                    for d in D_KEYS},
            "flag_agreement": allb["cf_flag"]["mean_pairwise_agreement"] == frozen["flag_agreement"],
            "n_views": allb["n_views"] == frozen["n_subjects"],
        }
    return res, rows


# -- (d) --------------------------------------------------------------------------


def _stats(vals: List[float]) -> Dict[str, Any]:
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "mean": float(np.mean(vals)), "median": float(statistics.median(vals)),
            "min": min(vals), "max": max(vals)}


FINISH_FIELD_RE = re.compile(r"finish_reason|stop_reason|usage|completion_tokens|num_generated|"
                             r"output_tokens|n_tokens|token_count|truncat", re.I)
FINISH_LOG_RE = re.compile(r"finish_reason|stop_reason|completion_tokens|num_generated_tokens|"
                           r"output_tokens|truncat", re.I)


def scan_finish_reasons(runs: Sequence[str], log_dir) -> Dict[str, Any]:
    fields = {"responses.jsonl": set(), "manifest.jsonl": set()}
    caps = set()
    for run in runs:
        for name in fields:
            for rec in loader._read_jsonl(Path(run) / name):
                fields[name].update(rec.keys())
                if name == "manifest.jsonl":
                    caps.add(rec.get("max_tokens"))
    hits_fields = {n: sorted(k for k in f if FINISH_FIELD_RE.search(k)) for n, f in fields.items()}
    logs = []
    for run in runs:
        run_id = Path(run).name
        logs += sorted(str(p) for p in Path(log_dir).glob("*%s*.log" % run_id))
    log_hits = []
    for lp in logs:
        with open(lp, encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                if FINISH_LOG_RE.search(line):
                    log_hits.append("%s:%d" % (lp, lineno))
    recorded = any(hits_fields.values()) or bool(log_hits)
    return {
        "responses_fields": sorted(fields["responses.jsonl"]),
        "manifest_fields": sorted(fields["manifest.jsonl"]),
        "fields_matching_finish_or_token_count": hits_fields,
        "manifest_max_tokens_values": sorted(c for c in caps if c is not None),
        "run_logs_scanned": logs,
        "run_log_lines_matching": log_hits,
        "target_finish_reason_or_token_count": "recorded" if recorded else "not recorded",
        "note": "manifest max_tokens is the configured cap, not a per-response count; no "
                "proxy for target truncation is computed",
    }


def section_d(main_runs, items, pop, tokenizer_path, anchors_path, log_dir) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(tokenizer_path)
    manual = kjudge.load_manual_text()
    anchors = kjudge.load_anchors(anchors_path)
    cells: Dict[Tuple[str, int], Dict[str, Any]] = {}
    sha_match = sha_total = 0
    provider_views = []
    for run in main_runs:
        convs = {(c["item_id"], c["condition"]): c for c in kjudge.read_conversations(run)}
        views = load_views(run)
        for (item_id, cond, depth), view in views.items():
            if item_id not in pop or depth not in N1_DEPTHS:
                continue
            arm = pop[item_id]
            turns = convs[(item_id, cond)]["turns"][:depth]
            cell = cells.setdefault((arm, depth), {
                "transcript_chars": [], "response_chars": [], "j3_tokens": [],
                "n_views": 0, "err": {j: {"provider": 0, "truncated": 0, "other_parse": 0}
                                      for j in JUDGE_IDS},
                "over_threshold": 0, "over_context": 0,
                "j3_err_over_threshold": 0, "j3_trunc_over_threshold": 0})
            cell["n_views"] += 1
            cell["transcript_chars"].append(sum(len(t["user_text"]) + len(t["model_text"])
                                                for t in turns))
            cell["response_chars"].append(len(turns[-1]["model_text"]))
            j3 = view["judges"]["J3"]
            msgs = kjudge.build_judge_prompt(turns, manual, anchors,
                                             is_control=bool(j3["is_control"]))
            sha = kjudge._sha256_text(json.dumps(msgs, ensure_ascii=False, sort_keys=True))
            sha_total += 1
            sha_match += int(sha == j3["prompt_sha256"])
            text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
            n_tok = len(tok.encode(text))
            cell["j3_tokens"].append(n_tok)
            over = n_tok > J3_THRESHOLD
            cell["over_threshold"] += int(over)
            cell["over_context"] += int(n_tok > J3_CONTEXT)
            for jid, rec in view["judges"].items():
                if rec["status"] != "ok":
                    cell["err"][jid][classify_error(rec.get("error"))] += 1
            if j3["status"] != "ok" and over:
                cell["j3_err_over_threshold"] += 1
                cell["j3_trunc_over_threshold"] += int(classify_error(j3.get("error")) == "truncated")
            if j3["status"] != "ok" and classify_error(j3.get("error")) == "provider":
                provider_views.append({"run": run, "item_id": item_id, "depth": depth,
                                       "attempts": j3.get("attempts"),
                                       "first_attempt_prompt_tokens": n_tok})
    rows = []
    out_cells = []
    for arm in ARMS:
        for depth in N1_DEPTHS:
            c = cells.get((arm, depth))
            if c is None:
                continue
            n = c["n_views"]
            err_rate = {j: {"n_error": sum(c["err"][j].values()),
                            "error_rate": sum(c["err"][j].values()) / n,
                            "by_type": c["err"][j]} for j in JUDGE_IDS}
            entry = {
                "arm": arm, "depth": depth, "n_views": n,
                "transcript_chars": _stats(c["transcript_chars"]),
                "response_chars_turn_d": _stats(c["response_chars"]),
                "j3_first_attempt_prompt_tokens": _stats(c["j3_tokens"]),
                "j3_n_over_%d" % J3_THRESHOLD: c["over_threshold"],
                "j3_frac_over_%d" % J3_THRESHOLD: c["over_threshold"] / n,
                "j3_n_over_%d" % J3_CONTEXT: c["over_context"],
                "j3_errors_among_over_threshold": c["j3_err_over_threshold"],
                "j3_truncated_among_over_threshold": c["j3_trunc_over_threshold"],
                "judge_errors": err_rate,
            }
            out_cells.append(entry)
            row = {"arm": arm, "depth": depth, "n_views": n}
            for name, key in (("transcript_chars", "transcript_chars"),
                              ("response_chars", "response_chars_turn_d"),
                              ("j3_tokens", "j3_first_attempt_prompt_tokens")):
                for s in ("mean", "median", "min", "max"):
                    row["%s_%s" % (name, s)] = entry[key].get(s)
            row["j3_n_over_threshold"] = c["over_threshold"]
            row["j3_frac_over_threshold"] = c["over_threshold"] / n
            for j in JUDGE_IDS:
                row["%s_error_rate" % j] = err_rate[j]["error_rate"]
                for t in ("provider", "truncated", "other_parse"):
                    row["%s_err_%s" % (j, t)] = c["err"][j][t]
            rows.append(row)
    res = {
        "label": LABEL, "section": "d_length_truncation", "runs": list(main_runs),
        "population": "N1 population (24 LOC six-turn localized + 24 BEN twins) x 5 main "
                      "runs, views at depths 1, 3, 6",
        "definitions": {
            "transcript_chars": "sum over turns 1..d of len(user_text) + len(model_text) "
                                "as stored in responses.jsonl (Python str length)",
            "response_chars_turn_d": "len(model_text) of turn d",
            "j3_first_attempt_prompt_tokens": "kyra.judge.build_judge_prompt (current "
                "template, manual, research/judge_anchors_v1.json), Phi-4 chat template with "
                "add_generation_prompt=True, tokenizer.encode default special tokens; a re-ask "
                "after a parse error is longer (it appends the judge's first output) and is "
                "not reconstructed",
            "threshold": "%d = %d context - %d max new tokens" % (J3_THRESHOLD, J3_CONTEXT,
                                                                 J3_MAX_NEW),
        },
        "tokenizer_path": str(tokenizer_path),
        "prompt_sha256_check": {"views": sha_total, "reconstructed_equals_recorded": sha_match},
        "j3_provider_error_views": provider_views,
        "cells": out_cells,
        "target_truncation": scan_finish_reasons(main_runs, log_dir),
    }
    return res, rows


# -- output ---------------------------------------------------------------------


def write_csv(rows: List[Dict[str, Any]], path) -> None:
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    cols: List[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})


def write_readme(out: Path, args, written: List[str], main_runs, all_runs) -> None:
    lines = [
        README_HEADER,
        "",
        "Every file here is a POST-HOC SENSITIVITY analysis requested by the external",
        "pre-submission review (JKIICE). The confirmatory results are the frozen outputs in",
        "%s and are unchanged. Outcomes had been read before this code was written." % args.frozen_dir,
        "",
        "generated_utc: %s" % datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command: PYTHONPATH=src python -m kyra.analysis.posthoc_v1 %s" % " ".join(sys.argv[1:]),
        "protocol: %s" % loader.version_string(),
        "items: %s" % args.items,
        "main runs (a, b, c-i, d):",
    ] + ["  %s" % r for r in main_runs] + [
        "all scored runs (c-ii): %d" % len(all_runs),
        "",
        "files:",
    ] + ["  %s" % f for f in written] + [
        "",
        "a_judge_validity.*   judge validity / ERROR counts by arm x depth (main runs)",
        "b_n1_sensitivity.*   frozen N1 estimator under S0-S3 CF labelings + crude ORs;",
        "                     b_runs/<scheme>/<model>/ = symlinked manifest/responses +",
        "                     the rewritten panel.jsonl fed to the estimator",
        "c_n3_cluster.*       AC2 / CF agreement with conversation-cluster bootstrap",
        "d_length_truncation.* lengths, J3 prompt tokens, ERROR rates, finish-reason scan",
    ]
    (out / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kyra.analysis.posthoc_v1",
                                description="POST-HOC sensitivity analyses (not confirmatory)")
    p.add_argument("--root", default=DEFAULT_ROOT)
    p.add_argument("--items", default=DEFAULT_ITEMS)
    p.add_argument("--frozen-dir", default=DEFAULT_FROZEN)
    p.add_argument("--family-map", default=DEFAULT_FAMILY_MAP)
    p.add_argument("--judges-config", default=DEFAULT_JUDGES_CONFIG)
    p.add_argument("--anchors", default=DEFAULT_ANCHORS)
    p.add_argument("--out-root", default=DEFAULT_OUT_ROOT)
    p.add_argument("--sections", default="abcd")
    p.add_argument("--bootstrap", type=int, default=n1.DEFAULT_B)
    p.add_argument("--n1-seed", type=int, default=n1.DEFAULT_SEED)
    p.add_argument("--n3-seed", type=int, default=N3_SEED)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        main_runs, all_runs = discover_runs(args.root)
        check_runs(main_runs, all_runs)
        items = load_items_raw(args.items)
        pop = n1_population(items)
        n_risk = sum(1 for a in pop.values() if a == "risk")
        if n_risk != 24 or len(pop) != 48:
            raise ValueError("N1 population: %d risk / %d total, expected 24 / 48"
                             % (n_risk, len(pop)))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
        out = Path(args.out_root) / ("posthoc_%s" % stamp)
        out.mkdir(parents=True, exist_ok=False)
        written: List[str] = []
        frozen = Path(args.frozen_dir)
        if "a" in args.sections:
            res, rows = section_a(main_runs, items, pop)
            loader.write_json(res, out / "a_judge_validity.json")
            write_csv(rows, out / "a_judge_validity.csv")
            written += ["a_judge_validity.json", "a_judge_validity.csv"]
            sys.stdout.write("a done\n")
        if "b" in args.sections:
            res, rows = section_b(main_runs, args.items, args.family_map, out / "b_runs",
                                  args.bootstrap, args.n1_seed, frozen / "n1.json")
            loader.write_json(res, out / "b_n1_sensitivity.json")
            write_csv(rows, out / "b_n1_sensitivity.csv")
            written += ["b_n1_sensitivity.json", "b_n1_sensitivity.csv", "b_runs/"]
            sys.stdout.write("b done\n")
        if "c" in args.sections:
            res, rows = section_c(main_runs, all_runs, args.family_map, args.bootstrap,
                                  args.n3_seed, frozen / "n3.json")
            loader.write_json(res, out / "c_n3_cluster.json")
            write_csv(rows, out / "c_n3_cluster.csv")
            written += ["c_n3_cluster.json", "c_n3_cluster.csv"]
            sys.stdout.write("c done\n")
        if "d" in args.sections:
            cfg = json.loads(Path(args.judges_config).read_text(encoding="utf-8"))
            tok_path = [j for j in cfg["judges"] if j["judge_id"] == "J3"][0]["model_path"]
            res, rows = section_d(main_runs, items, pop, tok_path, args.anchors,
                                  Path(args.root) / "logs")
            loader.write_json(res, out / "d_length_truncation.json")
            write_csv(rows, out / "d_length_truncation.csv")
            written += ["d_length_truncation.json", "d_length_truncation.csv"]
            sys.stdout.write("d done\n")
        write_readme(out, args, written, main_runs, all_runs)
    except (ValueError, RuntimeError, KeyError, FileNotFoundError) as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return loader.EXIT_BAD_INPUT
    sys.stdout.write("out=%s\n" % out)
    return loader.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
