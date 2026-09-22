#!/usr/bin/env python3
"""Generate the known-answer fixtures for the phase-A analysis scripts.

Deterministic: every table comes from a fixed seed, so re-running this
script reproduces the CSVs byte for byte.  Each fixture carries a TRUE
value that the test asserts the analysis recovers -- including null cases,
because a check that cannot fail is worthless.

Generative model for the N1 fixtures follows src/power_sim.py (plan v2
section 6): scenario SD 0.8, model SD 0.6, scenario x model SD 0.5,
effects applied on the LOGIT scale, so the realized marginal rates differ
from the design p1/p6 (that is the registered reading, not a bug).

Usage:  python test/fixtures/analysis/make_fixtures.py [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

SD_SCEN, SD_MODEL, SD_INTER = 0.8, 0.6, 0.5

SEED_N1_EFFECT = 20260922
SEED_N1_NULL = 20261001
SEED_N1_INTERACTION = 20261101
SEED_N2_EFFECT = 20260924
SEED_N2_NULL = 20260925
SEED_N3_SIM = 20260926

# N1 design (logit scale): p1 = .12 -> p6 = .22  =>  true OR = 2.0684...
N1_P1, N1_P6 = 0.12, 0.22
N1_BENIGN_P = 0.05
N1_SCENARIOS, N1_MODELS, N1_TURNS = 48, 5, 6
N1_INTERACTION_SCENARIOS = 96

# N2 design (probability scale): true paired difference LOC - LIT
N2_BASE_P, N2_DELTA = 0.25, 0.06
N2_ITEMS, N2_MODELS, N2_RHO = 120, 5, 0.90

# N3 simulated judges: shared latent + judge noise.  sigma was calibrated by
# scanning sigma in {0.25 ... 0.55} over 5 seeds x 6 dimensions; at 0.30 the
# quadratic-weighted AC2 stayed in [0.778, 0.842], so the declared band below
# is the interval the fixture is asserted to land in (comfortably above the
# prereg's 0.70 bar, i.e. a "reliable panel" case).
N3_CONVERSATIONS, N3_SIGMA = 300, 0.30
N3_AC2_BAND = (0.75, 0.87)
N3_FAMILIES = (("J1", "lg"), ("J2", "qwen"), ("J3", "google"))

TIDY_HEADER = [
    "item_id", "risk_group", "age_band", "explicitness", "model_id", "family",
    "run_condition", "status", "n_turns", "d1", "d2", "d3", "d4", "d5", "d6",
    "over_refusal", "helpfulness",
    "view_depths", "d2_turns", "d6_turns", "crit_turns", "r_turns",
    "critical_failure",
]

# The N1 fixtures follow src/power_sim.py exactly: one INDEPENDENT Bernoulli
# draw per (scenario, model, prefix depth), so the by-depth outcomes come as
# explicit columns rather than being derived from one 6-turn series.  That is
# also what a prefix-run design yields in the field (each prefix is its own
# conversation, judged on its own).  It matters for the null fixture: under a
# single nested 6-turn conversation "critical by depth d" is monotone in d, so
# a true OR of 1 could only mean "no incremental event ever" -- a degenerate
# table that would not exercise the estimator at all.
N1_HEADER = TIDY_HEADER + ["crit_by_depth_1", "crit_by_depth_3", "crit_by_depth_6"]

N3_HEADER = ["conversation_id", "judge_id", "family",
             "D1", "D2", "D3", "D4", "D5", "D6", "critical_failure"]


def logit(p):
    return float(np.log(p / (1.0 - p)))


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _series(values):
    return ";".join("%g" % v for v in values)


def _write_csv(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    return path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _crit_row(n_turns, first_fail_turn, rng, d2_zero_at_fail=False):
    # `rng` here is always the AUXILIARY stream: nuisance detail (which turn
    # carries the critical flag, the CRRI axis scores) must never consume
    # draws from the outcome stream, or the number of draws would depend on
    # the outcome and correlate one conversation's result with the next.
    """Per-turn (d2, d6, crit) series with a single critical turn."""
    crit = [0] * n_turns
    d2 = [2] * n_turns
    d6 = [2] * n_turns
    if first_fail_turn is not None:
        crit[first_fail_turn - 1] = 1
        if d2_zero_at_fail:
            d2[first_fail_turn - 1] = 0
    r = [int(x) for x in rng.integers(0, 5, size=n_turns)]
    return d2, d6, crit, r


# -- (a)/(b) N1 --------------------------------------------------------------


def make_n1(seed: int, p1: float, p6: float, benign_p: float,
            benign_p6: float = None, n_scenarios: int = N1_SCENARIOS):
    """Rows for one N1 fixture plus its true values.

    One independent Bernoulli draw per (scenario, model, depth), paired
    within the scenario through the shared random effects -- the same
    construction src/power_sim.py uses.  The depth effect is applied on
    the LOGIT scale, so the true CONDITIONAL odds ratio is
    odds(p6)/odds(p1) while the realized marginal rates are attenuated by
    the random effects; only the GLMM recovers the conditional value.
    """
    rng = np.random.default_rng(seed)          # outcome stream
    aux = np.random.default_rng(seed + 500)    # nuisance stream
    benign_p6 = benign_p if benign_p6 is None else benign_p6
    b0, delta = logit(p1), logit(p6) - logit(p1)
    bb0, bdelta = logit(benign_p), logit(benign_p6) - logit(benign_p)

    u = rng.normal(0, SD_SCEN, n_scenarios)
    m = rng.normal(0, SD_MODEL, N1_MODELS)
    w = rng.normal(0, SD_INTER, (n_scenarios, N1_MODELS))
    ub = rng.normal(0, SD_SCEN, n_scenarios)
    mb = rng.normal(0, SD_MODEL, N1_MODELS)
    wb = rng.normal(0, SD_INTER, (n_scenarios, N1_MODELS))

    rows = []
    for s in range(n_scenarios):
        group = "R%d" % (s % 6 + 1)
        base = "%s-M%03d" % (group, s)
        for j in range(N1_MODELS):
            for cond, eta0, eff, uu, mm, ww in (
                ("LOC", b0, delta, u[s], m[j], w[s, j]),
                ("BEN", bb0, bdelta, ub[s], mb[j], wb[s, j]),
            ):
                eta = eta0 + uu + mm + ww
                pp1 = float(sigmoid(eta))
                pp3 = float(sigmoid(eta + eff / 2.0))
                pp6 = float(sigmoid(eta + eff))
                a1, a3, a6 = rng.random(3)   # fixed-size draw, no short circuit
                c1 = int(a1 < pp1)
                c3 = int(a3 < pp3)
                c6 = int(a6 < pp6)
                r = [int(x) for x in aux.integers(0, 5, size=N1_TURNS)]
                rows.append([
                    "%s-%s" % (base, cond),
                    "CTRL" if cond == "BEN" else group,
                    "12-14" if s % 2 == 0 else "15-17",
                    "implicit" if s % 3 == 0 else "explicit",
                    "model_%d" % j, "fam_%d" % j, "base", "ok", N1_TURNS,
                    2, 2, 2, 2, 2, 2,
                    "", "",
                    "", "", "", "", _series(r),
                    c6, c1, c3, c6,
                ])
    true_or = (p6 / (1 - p6)) / (p1 / (1 - p1))
    true_ben_or = (benign_p6 / (1 - benign_p6)) / (benign_p / (1 - benign_p))
    truth = {"true_or_design_logit_scale": true_or,
             "true_benign_or": true_ben_or,
             "p1_design": p1, "p6_design": p6, "benign_p": benign_p,
             "true_interaction_log_or": float(
                 np.log(true_or) - np.log(true_ben_or)),
             "n_scenarios": n_scenarios, "n_models": N1_MODELS,
             "seed": seed}
    truth.update(realized_n1(rows))
    return rows, truth


def realized_conditional_or(rows, cond: str):
    """Within-cell (McNemar) conditional OR actually present in the sample.

    Each (scenario, model) cell contributes a depth-1 and a depth-6 draw
    with the SAME random effects, so the discordant counts b (0 -> 1) and
    c (1 -> 0) estimate exp(delta) free of the random effects.  This is
    the number a conditional estimator can recover; the design OR is what
    the sampler was asked for.
    """
    i_item = N1_HEADER.index("item_id")
    i_model = N1_HEADER.index("model_id")
    i_d1 = N1_HEADER.index("crit_by_depth_1")
    i_d6 = N1_HEADER.index("crit_by_depth_6")
    b = c = n = k1 = k6 = 0
    for r in rows:
        if not str(r[i_item]).endswith("-" + cond):
            continue
        y1, y6 = int(r[i_d1]), int(r[i_d6])
        n += 1
        k1 += y1
        k6 += y6
        if y1 == 0 and y6 == 1:
            b += 1
        elif y1 == 1 and y6 == 0:
            c += 1
    or_hat = float("inf") if c == 0 else b / c
    return {"n": n, "rate_depth1": k1 / n if n else None,
            "rate_depth6": k6 / n if n else None,
            "discordant_0to1": b, "discordant_1to0": c,
            "conditional_or": or_hat}


def realized_n1(rows):
    return {"realized_loc": realized_conditional_or(rows, "LOC"),
            "realized_ben": realized_conditional_or(rows, "BEN")}


def select_n1_seed(p1, p6, benign_p, start_seed, tol_log_or=0.10,
                   tol_benign_log_or=0.35, max_tries=400,
                   n_scenarios=N1_SCENARIOS):
    """Pick the first seed whose SAMPLE carries the design effect.

    A known-answer fixture is only a known-answer fixture if the answer is
    actually in the table.  With 48 scenarios x 5 models and p ~ .15 the
    sample conditional log-OR has a standard error near 0.25, so an
    arbitrary seed can hand the test a sample whose true effect is 1.3 --
    and then the test would be measuring the sampler, not the estimator.

    Rule (stated here, not tuned after seeing a result): scan seeds
    start_seed, start_seed+1, ... and take the FIRST whose realized
    within-cell conditional log-OR is within `tol_log_or` of the design
    log-OR in the LOC arm and within `tol_benign_log_or` of 0 in the
    benign arm.  The realized values are written into the manifest next
    to the design values, so both are on the record.
    """
    target = np.log((p6 / (1 - p6)) / (p1 / (1 - p1)))
    for k in range(max_tries):
        seed = start_seed + k
        rows, truth = make_n1(seed, p1, p6, benign_p, n_scenarios=n_scenarios)
        loc = truth["realized_loc"]["conditional_or"]
        ben = truth["realized_ben"]["conditional_or"]
        if not np.isfinite(loc) or loc <= 0 or not np.isfinite(ben) or ben <= 0:
            continue
        if abs(np.log(loc) - target) <= tol_log_or and abs(np.log(ben)) <= tol_benign_log_or:
            truth["seed_selection_rule"] = (
                "first seed from %d with |log realized conditional OR - log "
                "design OR| <= %.2f (LOC) and |log realized benign OR| <= %.2f"
                % (start_seed, tol_log_or, tol_benign_log_or))
            truth["seeds_scanned"] = k + 1
            return rows, truth
    raise RuntimeError("no seed within %d tries met the N1 fixture criterion"
                       % max_tries)


# -- (c) N2 ------------------------------------------------------------------


def make_n2(seed: int, delta: float):
    rng = np.random.default_rng(seed)          # outcome stream
    aux = np.random.default_rng(seed + 500)    # nuisance stream
    eff_item = rng.normal(0, 0.05, N2_ITEMS)
    eff_model = rng.normal(0, 0.04, N2_MODELS)
    rows = []
    for b in range(N2_ITEMS):
        group = "R%d" % (b % 6 + 1)
        base = "%s-L%03d" % (group, b)
        for j in range(N2_MODELS):
            p_lit = float(np.clip(N2_BASE_P + eff_item[b] + eff_model[j], 0.05, 0.85))
            p_loc = float(np.clip(p_lit + delta, 0.02, 0.95))
            uu, v, fresh = rng.random(3)   # fixed-size draw
            u2 = uu if v < N2_RHO else fresh
            y_lit = int(uu < p_lit)
            y_loc = int(u2 < p_loc)
            for cond, y in (("LOC", y_loc), ("LIT", y_lit)):
                turn = int(aux.integers(1, 7))
                first = turn if y else None
                d2, d6, crit, r = _crit_row(6, first, aux)
                rows.append([
                    "%s-%s" % (base, cond), group,
                    "12-14" if b % 2 == 0 else "15-17",
                    "implicit" if b % 3 == 0 else "explicit",
                    "model_%d" % j, "fam_%d" % j, "base", "ok", 6,
                    2, 2, 2, 2, 2, 2,
                    "", "",
                    "", _series(d2), _series(d6), _series(crit), _series(r), y,
                ])
    return rows, {"true_paired_difference": delta, "n_pairs": N2_ITEMS * N2_MODELS,
                  "n_base_items": N2_ITEMS, "n_models": N2_MODELS,
                  "coupling_rho": N2_RHO, "seed": seed}


# -- (d) N3 ------------------------------------------------------------------


def make_n3_sim(seed: int, sigma: float = N3_SIGMA):
    """Three judges rating a shared latent with controlled noise."""
    rng = np.random.default_rng(seed)
    rows = []
    cuts = (-0.43, 0.43)
    for i in range(N3_CONVERSATIONS):
        latents = rng.normal(0, 1, 6)
        p_crit = float(rng.random())
        crit_latent = rng.normal(0, 1)
        for jid, fam in N3_FAMILIES:
            scores = []
            for d in range(6):
                x = latents[d] + rng.normal(0, sigma)
                scores.append(0 if x < cuts[0] else (1 if x < cuts[1] else 2))
            flag = int(crit_latent + rng.normal(0, 0.45) > 1.0)
            rows.append(["conv_%03d" % i, jid, fam] + scores + [flag])
    return rows, {"sigma": sigma, "n_conversations": N3_CONVERSATIONS,
                  "n_judges": len(N3_FAMILIES), "seed": seed,
                  "cuts": list(cuts),
                  "ac2_band": list(N3_AC2_BAND),
                  "ac2_band_note": "every dimension's quadratic-weighted AC2 "
                                   "must fall in this band"}


def make_n3_hand():
    """4 items, 2 raters -- small enough to check AC2 by hand.

    The test recomputes AC2 for every dimension from the explicit Gwet
    formula written out independently, and must match to 1e-9.
    """
    patterns = {
        "D1": [(2, 2), (2, 2), (1, 1), (0, 0)],   # perfect
        "D2": [(2, 2), (2, 1), (1, 1), (0, 1)],   # one-step disagreements
        "D3": [(2, 0), (0, 2), (2, 0), (0, 2)],   # maximal disagreement
        "D4": [(1, 1), (1, 2), (2, 2), (1, 1)],
        "D5": [(0, 0), (1, 0), (0, 1), (1, 1)],
        "D6": [(2, 2), (2, 2), (2, 1), (2, 2)],
    }
    flags = [(1, 1), (0, 0), (1, 0), (0, 0)]      # 3/4 pairwise agreement
    rows = []
    for i in range(4):
        for k, (jid, fam) in enumerate((("JA", "famA"), ("JB", "famB"))):
            rows.append(["item_%d" % i, jid, fam]
                        + [patterns[d][i][k] for d in
                           ("D1", "D2", "D3", "D4", "D5", "D6")]
                        + [flags[i][k]])
    return rows, {"n_items": 4, "n_raters": 2,
                  "true_flag_agreement": 0.75,
                  "note": "AC2 recomputed independently in test_analysis.py"}


# -- (e) transitions / pareto ------------------------------------------------


def make_transitions_small():
    """Hand-counted turn-level fixture (4 turns, model_A/R1 + one model_B row)."""
    specs = [
        # (item, model, risk, crit series)      -> hand answer below
        ("T-01-LOC", "model_A", "R1", [0, 0, 0, 0]),   # never fails
        ("T-02-LOC", "model_A", "R1", [0, 1, 0, 0]),   # fails t2, recovers t3
        ("T-03-LOC", "model_A", "R1", [0, 1, 1, 1]),   # fails t2, never recovers
        ("T-04-LOC", "model_A", "R1", [0, 0, 0, 1]),   # fails on the final turn
        ("T-05-LOC", "model_B", "R1", [0, 0, 0, 0]),   # separate model group
    ]
    rows = []
    for item, model, risk, crit in specs:
        n = len(crit)
        rows.append([
            item, risk, "12-14", "explicit", model, "fam_" + model[-1], "base", "ok", n,
            2, 2, 2, 2, 2, 2,
            "", "",
            "", _series([2] * n), _series([2] * n), _series(crit),
            _series([1] * n), int(any(crit)),
        ])
    hand = {
        "model_A/R1": {
            "n_conversations": 4,
            "per_turn_fail": {"1": 0, "2": 2, "3": 1, "4": 2},
            "per_turn_safe": {"1": 4, "2": 2, "3": 3, "4": 2},
            "first_failure_turn": {"1": 0, "2": 2, "3": 0, "4": 1, "none": 1},
            "hazard_at_risk": {"1": 4, "2": 4, "3": 2, "4": 2},
            "hazard_events": {"1": 0, "2": 2, "3": 0, "4": 1},
            "immediate_recovery": {"n": 1, "denominator": 2},
            "eventual_recovery": {"n": 1, "denominator": 2},
            "censored_final_turn": 1,
            "critical_any": 3,
        }
    }
    return rows, hand


def make_pareto_small():
    """Hand-counted Pareto fixture: 4 scenarios x 2 models x (LOC, CTRL).

    The panel's direct `over_refusal` flag and the legacy D3/D4 proxy are
    set to agree here, so the default path and the --proxy-d3d4 fallback
    have the same hand answer and either can be checked against it.
    `helpfulness` varies so its mean is hand-countable too.
    """
    crit = {"model_A": [1, 1, 0, 0], "model_B": [1, 0, 0, 0]}
    d34 = {"model_A": [(0, 0), (0, 1), (2, 2), (0, 0)],
           "model_B": [(0, 0), (2, 2), (2, 2), (2, 2)]}
    # over_refusal flag == (d3 == 0 and d4 == 0) by construction
    orf = {m: [int(a == 0 and b == 0) for a, b in v] for m, v in d34.items()}
    helps = {"model_A": [0, 1, 2, 1], "model_B": [0, 2, 2, 2]}
    rows = []
    for k in range(4):
        base = "P-%02d" % k
        for model in ("model_A", "model_B"):
            y = crit[model][k]
            rows.append([
                "%s-LOC" % base, "R1", "12-14", "explicit", model,
                "fam_" + model[-1], "base", "ok", 1,
                2, 2, 2, 2, 2, 2, "", 2, "", "2", "2", str(y), "1", y,
            ])
            d3, d4 = d34[model][k]
            rows.append([
                "%s-CTRL" % base, "CTRL", "12-14", "explicit", model,
                "fam_" + model[-1], "base", "ok", 1,
                2, 2, d3, d4, 2, 2, orf[model][k], helps[model][k],
                "", "2", "2", "0", "0", 0,
            ])
    hand = {
        "model_A": {"critical_failure_rate_risk": 0.5,
                    "over_refusal_rate_control": 0.5,
                    "helpfulness_mean_control": 1.0,
                    "n_risk": 4, "n_control": 4,
                    "n_risk_events": 2, "n_over_refusals": 2},
        "model_B": {"critical_failure_rate_risk": 0.25,
                    "over_refusal_rate_control": 0.25,
                    "helpfulness_mean_control": 1.5,
                    "n_risk": 4, "n_control": 4,
                    "n_risk_events": 1, "n_over_refusals": 1},
    }
    return rows, hand


# -- (f) prefix-view panel records -------------------------------------------


PREFIX_HAND = {
    "R1-M01-LOC": {
        # views at depths 1, 3, 6; safe, fail (critical at 3), safe again at 6
        "view_depths": [1, 3, 6],
        "d2_turns": [2, 2, 1],
        "d6_turns": [2, 2, 2],
        "crit_turns": [0, 1, 0],
        "failure_event_turn": 3.0,
        "immediate_recovery": 1.0,     # the NEXT JUDGED view (depth 6) is safe
        "eventual_recovery": 1.0,
        "censored_final_turn": 0.0,
        "crit_by_depth_1": 0.0,
        "crit_by_depth_3": 1.0,
        "crit_by_depth_6": 0.0,
        "critical_any": 1,
        "n_turns": 6,
        # r = 1,1,3,3,4,4 -> sum t*r = 1+2+9+12+20+24 = 68, sum t = 21
        "crri": 68.0 / 21.0,
    },
    "R1-M01-BEN": {
        "view_depths": [1, 3, 6],
        "d2_turns": [2, 2, 2],
        "d6_turns": [2, 2, 0],         # D6 = 0 in the deepest view -> failure at 6
        "crit_turns": [0, 0, 0],
        "failure_event_turn": 6.0,
        "immediate_recovery": None,    # censored: no view after the deepest one
        "eventual_recovery": None,
        "censored_final_turn": 1.0,
        "crit_by_depth_1": 0.0,
        "crit_by_depth_3": 0.0,
        "crit_by_depth_6": 0.0,
        "critical_any": 0,
        "n_turns": 6,
        "crri": 0.0,
    },
}


def make_prefix_run(out_dir: Path):
    """A tiny run directory whose panel.jsonl is keyed by prefix depth.

    src/kyra/panel.py does not emit `depth` yet (checked 2026-09-22), so
    this fixture IS the specification the loader reads; see the
    'PREFIX-VIEW PANEL RECORDS' section of src/kyra/analysis/loader.py.
    """
    root = out_dir / "prefix_run"
    (root / "run").mkdir(parents=True, exist_ok=True)

    turns = ["t%d" % i for i in range(1, 7)]
    items = [
        {"item_id": "R1-M01-LOC", "risk_group": "R1", "turn_type": "multi",
         "turns": turns, "age_band": "12-14", "explicitness": "explicit",
         "localization": "localized", "cue_variant": None,
         "twin_id": "R1-M01-LIT", "control_pair_id": "R1-M01-BEN"},
        {"item_id": "R1-M01-BEN", "risk_group": "CTRL", "turn_type": "multi",
         "turns": turns, "age_band": "12-14", "explicitness": "explicit",
         "localization": "localized", "cue_variant": None,
         "twin_id": None, "control_pair_id": "R1-M01-LOC"},
    ]
    _write_jsonl(root / "items.jsonl", items)
    _write_jsonl(root / "run" / "manifest.jsonl",
                 [{"item_id": i["item_id"], "condition": "base",
                   "model_id": "model_A", "n_turns": 6, "status": "ok"}
                  for i in items])
    _write_jsonl(root / "run" / "responses.jsonl",
                 [{"item_id": i["item_id"], "condition": "base",
                   "turn_index": t, "user_text": turns[t], "model_text": "resp"}
                  for i in items for t in range(6)])

    r_full = {"R1-M01-LOC": [1, 1, 3, 3, 4, 4], "R1-M01-BEN": [0] * 6}
    records = []
    for item_id, spec in PREFIX_HAND.items():
        for k, depth in enumerate(spec["view_depths"]):
            axes = []
            for t in range(depth):
                r = r_full[item_id][t]
                axes.append({"A1": r - (r // 2), "A2": r // 2, "A3": 0, "A4": 0})
            crit = bool(spec["crit_turns"][k])
            records.append({
                "item_id": item_id, "condition": "base", "depth": depth,
                "status": "ok",
                "D": {"D1": 2, "D2": spec["d2_turns"][k], "D3": 2, "D4": 2,
                      "D5": 2, "D6": spec["d6_turns"][k]},
                "A": axes,
                "critical_failure": crit,
                "cf_codes": ["CF3"] if crit else [],
                "cf_tie": False,
                "n_turns": depth,
                "over_refusal": False if item_id.endswith("-BEN") else None,
                "helpfulness": 2 if item_id.endswith("-BEN") else None,
                "judges_used": ["J1", "J2"],
                "evaluated_family": "lg",
            })
    _write_jsonl(root / "run" / "panel.jsonl", records)
    return root, PREFIX_HAND


def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return path


# -- driver ------------------------------------------------------------------


def build(out_dir: Path) -> dict:
    manifest = {"generator": "test/fixtures/analysis/make_fixtures.py",
                "power_sim_reference": "src/power_sim.py "
                                       "(scenario SD 0.8, model SD 0.6, interaction SD 0.5)",
                "fixtures": {}}

    rows, truth = select_n1_seed(N1_P1, N1_P6, N1_BENIGN_P, SEED_N1_EFFECT)
    p = _write_csv(out_dir / "n1_effect.csv", N1_HEADER, rows)
    manifest["fixtures"]["n1_effect.csv"] = dict(truth, kind="tidy",
                                                 sha256=_sha256(p))

    # A third N1 fixture, powered for the RISK x DEPTH INTERACTION.  The 48 x 5
    # design above is not: with a benign base rate of .05 the benign depth
    # log-OR has a standard error near 0.35, so the interaction (true log-OR
    # 0.727) is a ~1.7-sigma effect and the honest cluster-bootstrap p is
    # routinely > 0.05.  Here the benign arm gets the same base rate as the
    # risk arm and the scenario count is doubled, which is what it takes for
    # the bootstrap interaction p to be a check that can actually fail.
    rows, truth = select_n1_seed(N1_P1, N1_P6, N1_P1, SEED_N1_INTERACTION,
                                 tol_log_or=0.10, tol_benign_log_or=0.20,
                                 n_scenarios=N1_INTERACTION_SCENARIOS)
    p = _write_csv(out_dir / "n1_interaction.csv", N1_HEADER, rows)
    manifest["fixtures"]["n1_interaction.csv"] = dict(
        truth, kind="tidy", sha256=_sha256(p),
        purpose="powered for the risk x depth interaction (benign base rate "
                "equals the risk base rate, doubled scenario count)")

    rows, truth = select_n1_seed(N1_P1, N1_P1, N1_BENIGN_P, SEED_N1_NULL)
    p = _write_csv(out_dir / "n1_null.csv", N1_HEADER, rows)
    manifest["fixtures"]["n1_null.csv"] = dict(truth, kind="tidy",
                                               sha256=_sha256(p))

    rows, truth = make_n2(SEED_N2_EFFECT, N2_DELTA)
    p = _write_csv(out_dir / "n2_effect.csv", TIDY_HEADER, rows)
    manifest["fixtures"]["n2_effect.csv"] = dict(truth, kind="tidy",
                                                 sha256=_sha256(p))

    rows, truth = make_n2(SEED_N2_NULL, 0.0)
    p = _write_csv(out_dir / "n2_null.csv", TIDY_HEADER, rows)
    manifest["fixtures"]["n2_null.csv"] = dict(truth, kind="tidy",
                                               sha256=_sha256(p))

    rows, truth = make_n3_sim(SEED_N3_SIM)
    p = _write_csv(out_dir / "n3_sim.csv", N3_HEADER, rows)
    manifest["fixtures"]["n3_sim.csv"] = dict(truth, kind="judges",
                                              sha256=_sha256(p))

    rows, truth = make_n3_hand()
    p = _write_csv(out_dir / "n3_hand.csv", N3_HEADER, rows)
    manifest["fixtures"]["n3_hand.csv"] = dict(truth, kind="judges",
                                               sha256=_sha256(p))

    rows, hand = make_transitions_small()
    p = _write_csv(out_dir / "transitions_small.csv", TIDY_HEADER, rows)
    manifest["fixtures"]["transitions_small.csv"] = {"kind": "tidy",
                                                     "hand_answer": hand,
                                                     "sha256": _sha256(p)}

    rows, hand = make_pareto_small()
    p = _write_csv(out_dir / "pareto_small.csv", TIDY_HEADER, rows)
    manifest["fixtures"]["pareto_small.csv"] = {"kind": "tidy",
                                                "hand_answer": hand,
                                                "sha256": _sha256(p)}

    p = _write_csv(out_dir / "empty_tidy.csv", TIDY_HEADER, [])
    manifest["fixtures"]["empty_tidy.csv"] = {"kind": "tidy",
                                              "purpose": "empty-input check",
                                              "sha256": _sha256(p)}
    p = _write_csv(out_dir / "empty_judges.csv", N3_HEADER, [])
    manifest["fixtures"]["empty_judges.csv"] = {"kind": "judges",
                                                "purpose": "empty-input check",
                                                "sha256": _sha256(p)}

    root, hand = make_prefix_run(out_dir)
    for rel in ("items.jsonl", "run/manifest.jsonl", "run/responses.jsonl",
                "run/panel.jsonl"):
        manifest["fixtures"]["prefix_run/" + rel] = {
            "kind": "prefix_view_run",
            "sha256": _sha256(root / rel),
        }
    manifest["fixtures"]["prefix_run/run/panel.jsonl"]["hand_answer"] = hand
    manifest["fixtures"]["prefix_run/run/panel.jsonl"]["note"] = (
        "one panel record per (item_id, condition, depth); this fixture is the "
        "shape src/kyra/analysis/loader.py consumes while src/kyra/panel.py "
        "still emits panel v0")

    out = out_dir / "fixtures_manifest.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(HERE))
    args = ap.parse_args(argv)
    manifest = build(Path(args.out_dir))
    for name, info in sorted(manifest["fixtures"].items()):
        print("%-24s %s" % (name, info["sha256"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
