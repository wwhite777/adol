"""Turn-level transition tables (prereg statistics.also_reported).

"turn-level transition tables (SAFE/FAIL per turn, first-failure turn,
 immediate and eventual recovery counts, censoring)"

Per model and risk group this reports, with every denominator stated:
  * SAFE / FAIL counts per turn (denominator = conversations that reached
    that turn);
  * the first-failure turn distribution, including "none";
  * immediate recovery (restored at t+1) and eventual recovery (restored
    at any later turn) counts, each with its own denominator -- final-turn
    failures are NOT in either denominator, they are censored;
  * censoring counts (failure on the final turn, recovery unobserved);
  * an empirical discrete-time hazard per turn: events at turn t divided
    by the conversations still at risk at the start of turn t.

"turn" in the output means the JUDGED PREFIX DEPTH: with every turn
judged the two coincide; with prefix views at {1, 3, 6} only those
depths appear, and "at risk at t" means "safe in every judged view
before t".

Counting only.  No model is fitted here: the cloglog hazard model of
CRRI_SPEC_v1.md is one representation of exactly these counts and is not
part of this card.

Output JSON schema (the names G6 reads)
---------------------------------------
version                       "PREREGISTERED_kyra_v2.yaml@<sha256>"
analysis                      "transitions"
n_conversations               int
by_model_and_risk_group[]     model_id, risk_group, n_conversations,
                              judged_depths[], max_turns,
                              per_turn[]  {turn, denominator_reached_turn,
                                           safe, fail},
                              hazard[]    {turn, at_risk, events, hazard},
                              first_failure_turn {"<d>": n, ..., "none": n},
                              recovery.immediate {n, denominator},
                              recovery.eventual  {n, denominator},
                              censored_final_turn, critical_any, crri_mean
overall                       the same block over every conversation
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from kyra.analysis import loader
from kyra.analysis.loader import EmptyInput, clean_float


def _group_summary(g: pd.DataFrame) -> Dict[str, Any]:
    recs = g.to_dict("records")
    safes = {}       # conversation -> {depth: is_safe}
    all_depths = set()
    for r in recs:
        s = loader.safe_series(r)
        if s is None:
            continue
        depths, safe = s
        safes[r["item_id"] + "|" + str(r["model_id"])] = dict(zip(depths, safe))
        all_depths.update(depths)

    depth_list = sorted(all_depths)
    per_turn: List[Dict[str, Any]] = []
    hazard: List[Dict[str, Any]] = []
    for t in depth_list:
        reached = [s for s in safes.values() if t in s]
        n_safe = sum(1 for s in reached if s[t])
        n_fail = len(reached) - n_safe
        per_turn.append({
            "turn": t,
            "denominator_reached_turn": len(reached),
            "safe": n_safe,
            "fail": n_fail,
        })
        earlier = [d for d in depth_list if d < t]
        at_risk = [s for s in reached if all(s.get(d, True) for d in earlier)]
        events = sum(1 for s in at_risk if not s[t])
        hazard.append({
            "turn": t,
            "at_risk": len(at_risk),
            "events": events,
            "hazard": (events / len(at_risk)) if at_risk else None,
        })

    fet = g["failure_event_turn"]
    dist: Dict[str, int] = {}
    for t in depth_list:
        dist[str(t)] = int((fet == t).sum())
    dist["none"] = int(fet.isna().sum())

    imm = g["immediate_recovery"]
    eve = g["eventual_recovery"]
    cen = g["censored_final_turn"]
    return {
        "n_conversations": int(len(g)),
        "n_with_per_turn_series": int(len(safes)),
        "max_turns": int(depth_list[-1]) if depth_list else 0,
        "judged_depths": depth_list,
        "per_turn": per_turn,
        "hazard": hazard,
        "first_failure_turn": dist,
        "recovery": {
            "immediate": {
                "n": int((imm == 1).sum()),
                "denominator": int(imm.notna().sum()),
                "definition": "restored at t+1 after the first failure at t",
            },
            "eventual": {
                "n": int((eve == 1).sum()),
                "denominator": int(eve.notna().sum()),
                "definition": "restored at any turn after the first failure",
            },
        },
        "censored_final_turn": int((cen == 1).sum()),
        "censoring_note": "a first failure on the final turn has unobserved "
                          "recovery; it is excluded from both recovery "
                          "denominators. Any-turn failure stays true after "
                          "recovery.",
        "critical_any": int(g["critical_any"].sum()),
        "crri_mean": clean_float(g["crri"].mean()),
    }


def analyse(df: pd.DataFrame) -> Dict[str, Any]:
    if len(df) == 0:
        raise EmptyInput("zero conversations: nothing to count")
    loader.require_one_run_per_model(df, "transitions")
    if not df["per_turn_available"].any():
        raise ValueError(
            "no conversation carries a per-turn series (crit_turns), so "
            "turn-level SAFE/FAIL, first-failure turn, recovery and hazard "
            "counts cannot be produced. kyra.panel v0 records one "
            "conversation-level flag; supply per-turn panel records or a "
            "fixture CSV with crit_turns/d2_turns/d6_turns."
        )
    groups = []
    for (model, risk), g in df.groupby(["model_id", "risk_group"], dropna=False):
        summary = _group_summary(g)
        summary["model_id"] = model
        summary["risk_group"] = None if pd.isna(risk) else risk
        groups.append(summary)
    groups.sort(key=lambda d: (str(d["model_id"]), str(d["risk_group"])))
    return {
        "version": loader.version_string(),
        "analysis": "transitions",
        "unit": "conversation (item x model x condition), turns 1..n_turns",
        "failure_event": "first turn with D2 = 0 or D6 = 0 or a critical failure",
        "n_conversations": int(len(df)),
        "by_model_and_risk_group": groups,
        "overall": _group_summary(df),
    }


def main(argv=None) -> int:
    return loader.run_cli(
        lambda df, args: analyse(df), argv, "kyra.analysis.transitions",
        "Turn-level SAFE/FAIL, first-failure, recovery, censoring and hazard counts",
    )


if __name__ == "__main__":
    sys.exit(main())
