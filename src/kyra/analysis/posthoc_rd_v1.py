"""POST-HOC risk-difference contrasts and sparse-cell sensitivity (not confirmatory).

Requested by the external review of 2026-10-01 (review/JMIRMH_review_2026-10-01.md,
section 3.2 R1): the odds-ratio intervals of the benign arm and of the risk x
depth interaction rest on cells with 0-1 events, so the VB + scenario-bootstrap
percentile intervals mostly report the prior. The frozen confirmatory results
(result/analysis/phaseA_T1/20260926T0213Z/) are NOT changed; outcomes had been
read before this code was written, so every number here is post hoc.

Labelings (CF flag definitions already in manuscript v6, Table 7):
  S0  original panel labels (fixed rules)
  S1  complete panels only           } built with kyra.analysis.posthoc_v1.relabel
  S2  ties unresolved                } from the 5 adol main runs, exactly as in
  S3  ties = non-critical            } posthoc_20260927T2328Z
  R1  output budget repair           } kyrameas repair check 20260928T0239Z:
  R2  budget + JSON-schema decoding  } R1/runs, R2/runs (panel.jsonl per main run)
Both families go through kyra.analysis.loader.build_tidy and the frozen N1
selection (n1_escalation._select / depth_frame), so the rows are the rows the
paper's estimator saw.

Before anything new is computed, the k/n counts of every labeling are compared
with the reference outputs (S0-S3: posthoc_20260927T2328Z/b_n1_sensitivity.json;
R1/R2: the kyrameas n1.json totals and summary.json depth-6 flags). Any mismatch
-> reproduction_check.json is written and the process exits 2.

Sections:
(a) CF proportions k/n at depth 1 and 6 per arm, RD_risk = p6 - p1 (risk),
    RD_benign (benign twins), DiD = RD_risk - RD_benign; scenario-cluster
    bootstrap percentile 95% intervals (B = 2000). One resample = the 24 base
    items drawn with replacement, each carrying ALL its rows (risk script and
    benign twin, all models, both depths) -- the paper's interaction bootstrap.
    The rng stream is the paper's interaction stream: default_rng(seed + 3) with
    seed = 20260922, drawing rng.choice(n_scenarios, n_scenarios) over the sorted
    scenario list, as n1_escalation._cluster_resample does.
(b) Benign arm, crude 2 x 2 (depth-6 rows vs depth-1 rows, rows treated as
    independent -- NOT cluster-adjusted): exact conditional OR
    (scipy.stats.contingency.odds_ratio, kind="conditional"), Firth
    (Jeffreys-penalized) logistic regression y ~ depth6 with Wald and profile
    penalized-likelihood intervals (numpy/scipy implementation below), and the
    Woolf interval with the Haldane-Anscombe +0.5 correction (plus the
    uncorrected Woolf interval when no cell is zero).
(c) The scenario random-intercept SD of the frozen VB mixed model
    (BinomialBayesMixedGLM, y ~ depth6, scenario intercept), risk and benign.
    The frozen n1.json does not store it, so the frozen model is refitted. The
    frozen _fit_vb calls fit_vb with rng=None (start values from OS entropy);
    here the same call is made with K seeded start generators so the result is
    reproducible, and the spread over starts is reported.

CLI:
  PYTHONPATH=src python -m kyra.analysis.posthoc_rd_v1 [--bootstrap 2000]
      [--out-root result/analysis/phaseA_T1] [--vb-starts 20]

Exit codes: 0 ok | 2 reproduction mismatch | 4 bad input. Never writes under result/raw/.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from kyra.analysis import loader
from kyra.analysis import n1_escalation as n1
from kyra.analysis import posthoc_v1 as ph

LABEL = "POST-HOC (not confirmatory): risk-difference contrasts and sparse-cell sensitivity"
EXIT_OK = 0
EXIT_MISMATCH = 2
EXIT_BAD_INPUT = 4

DEFAULT_B = n1.DEFAULT_B
DEFAULT_SEED = n1.DEFAULT_SEED
RD_SEED_OFFSET = 3            # the paper's interaction-bootstrap stream (n1: seed + 3)
DEFAULT_VB_STARTS = 20
DEPTHS = (1, 6)
ARMS = ("risk", "benign")
LABELINGS = ("S0", "S1", "S2", "S3", "R1", "R2")
LABELING_TEXT = dict(ph.SCHEME_TEXT)
LABELING_TEXT.update({
    "R1": "output budget repair (kyrameas repair check 20260928T0239Z, R1: failed judge "
          "outputs re-judged with a larger max_new_tokens; manuscript v6 Table 7)",
    "R2": "budget + JSON-schema decoding (kyrameas repair check 20260928T0239Z, R2: R1 + "
          "vLLM structured outputs; manuscript v6 Table 7)",
})

DEFAULT_REF_POSTHOC = "result/analysis/phaseA_T1/posthoc_20260927T2328Z"
DEFAULT_REPAIR_DIR = "/home/wjeong/kyrameas/result/repair_check/20260928T0239Z"
Z975 = 1.959963984540054
CHI2_1_95 = 3.841458820694124


# -- small helpers --------------------------------------------------------------


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sanitize(obj):
    """JSON-safe copy: numpy scalars -> python; non-finite floats -> 'inf' / '-inf' / 'nan'."""
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        v = float(obj)
        if math.isnan(v):
            return "nan"
        if math.isinf(v):
            return "inf" if v > 0 else "-inf"
        return v
    return obj


def percentile_ci(vals: Sequence[float]) -> Optional[List[float]]:
    arr = np.asarray([v for v in vals if np.isfinite(v)], dtype=float)
    if arr.size == 0:
        return None
    lo, hi = np.percentile(arr, [2.5, 97.5])
    return [float(lo), float(hi)]


# -- data -------------------------------------------------------------------------


def long_frames(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """(risk long, benign long) at depths 1 and 6 with the frozen N1 selection."""
    risk = n1._select(df, "LOC")
    risk = risk[risk["risk_group"].astype(str) != "CTRL"]
    ben = n1._select(df, "BEN")
    lr = n1.depth_frame(risk, depths=DEPTHS)
    lb = n1.depth_frame(ben, depths=DEPTHS) if len(ben) else pd.DataFrame(columns=lr.columns)
    return lr, lb


def pooled_frame(long_risk: pd.DataFrame, long_ben: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([long_risk.assign(arm="risk"), long_ben.assign(arm="benign")],
                     ignore_index=True)


def scenario_counts(pooled: pd.DataFrame):
    """(sorted scenarios, K[s, arm, depth], N[s, arm, depth]) with arm 0 risk / 1 benign."""
    scen = sorted(pooled["scenario"].unique())
    idx = {s: i for i, s in enumerate(scen)}
    K = np.zeros((len(scen), 2, 2), dtype=float)
    N = np.zeros((len(scen), 2, 2), dtype=float)
    for rec in pooled[["scenario", "arm", "depth", "y"]].itertuples(index=False):
        a = 0 if rec.arm == "risk" else 1
        d = 0 if int(rec.depth) == DEPTHS[0] else 1
        K[idx[rec.scenario], a, d] += int(rec.y)
        N[idx[rec.scenario], a, d] += 1
    return scen, K, N


def rd_stats(k: np.ndarray, n: np.ndarray) -> Dict[str, float]:
    """RD_risk, RD_benign, DiD from summed 2 x 2 (arm x depth) counts; NaN if a cell is empty."""
    with np.errstate(invalid="ignore", divide="ignore"):
        p = np.where(n > 0, k / np.where(n > 0, n, 1), np.nan)
    rd_r = p[0, 1] - p[0, 0]
    rd_b = p[1, 1] - p[1, 0]
    return {"rd_risk": float(rd_r), "rd_benign": float(rd_b), "did": float(rd_r - rd_b)}


def rd_bootstrap(pooled: pd.DataFrame, B: int, seed: int) -> Dict[str, Any]:
    """Point RD/DiD + scenario-cluster bootstrap percentile intervals."""
    scen, K, N = scenario_counts(pooled)
    k_all, n_all = K.sum(0), N.sum(0)
    point = rd_stats(k_all, n_all)
    rng = np.random.default_rng(seed)
    S = len(scen)
    boots = {key: [] for key in point}
    undefined = {key: 0 for key in point}
    ben_d1_zero = 0
    for _ in range(B):
        picks = rng.choice(S, size=S, replace=True)
        kb, nb = K[picks].sum(0), N[picks].sum(0)
        if kb[1, 0] == 0:
            ben_d1_zero += 1
        st = rd_stats(kb, nb)
        for key, v in st.items():
            if np.isfinite(v):
                boots[key].append(v)
            else:
                undefined[key] += 1
    cells = {}
    for a, arm in enumerate(ARMS):
        for d, depth in enumerate(DEPTHS):
            k, n = int(k_all[a, d]), int(n_all[a, d])
            cells["%s_d%d" % (arm, depth)] = {"k": k, "n": n,
                                              "p": (k / n) if n else float("nan")}
    out: Dict[str, Any] = {"cells": cells, "n_scenarios": S, "B": int(B), "seed": int(seed)}
    for key in point:
        out[key] = {"estimate": point[key], "ci95_cluster_bootstrap": percentile_ci(boots[key]),
                    "bootstrap_used": len(boots[key]), "bootstrap_undefined": undefined[key]}
    out["bootstrap_replicates_with_0_benign_depth1_events"] = int(ben_d1_zero)
    return out


# -- 2 x 2 odds ratios ----------------------------------------------------------------


def table_2x2(cells: Dict[str, Dict[str, int]], arm: str) -> Tuple[int, int, int, int]:
    """(a, b, c, d) = (depth-6 events, depth-6 non-events, depth-1 events, depth-1 non-events)."""
    k6, n6 = cells["%s_d6" % arm]["k"], cells["%s_d6" % arm]["n"]
    k1, n1_ = cells["%s_d1" % arm]["k"], cells["%s_d1" % arm]["n"]
    return k6, n6 - k6, k1, n1_ - k1


def exact_conditional_or(a: int, b: int, c: int, d: int) -> Dict[str, Any]:
    from scipy.stats.contingency import odds_ratio

    res = odds_ratio(np.array([[a, b], [c, d]]), kind="conditional")
    ci = res.confidence_interval(confidence_level=0.95, alternative="two-sided")
    return {"method": "exact conditional (Fisher noncentral hypergeometric) MLE and "
                      "95% CI, scipy.stats.contingency.odds_ratio(kind='conditional')",
            "or": float(res.statistic), "ci95": [float(ci.low), float(ci.high)]}


def woolf_or(a: int, b: int, c: int, d: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if min(a, b, c, d) > 0:
        lo = math.log(a * d / (b * c))
        se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
        out["uncorrected"] = {"or": math.exp(lo), "se_log_or": se,
                              "ci95": [math.exp(lo - Z975 * se), math.exp(lo + Z975 * se)]}
    else:
        out["uncorrected"] = {"or": None, "note": "a cell is zero: crude OR undefined"}
    ah, bh, ch, dh = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    lo = math.log(ah * dh / (bh * ch))
    se = math.sqrt(1 / ah + 1 / bh + 1 / ch + 1 / dh)
    out["haldane"] = {"method": "Woolf (log-OR Wald) interval, Haldane-Anscombe +0.5 added "
                                "to every cell (always applied)",
                      "or": math.exp(lo), "se_log_or": se,
                      "ci95": [math.exp(lo - Z975 * se), math.exp(lo + Z975 * se)]}
    return out


def _firth_pll(beta: np.ndarray, X: np.ndarray, y: np.ndarray, n: np.ndarray) -> float:
    """Jeffreys-penalized binomial log-likelihood l(b) + 0.5 log|X'WX|."""
    eta = X @ beta
    ll = float(np.sum(y * eta - n * np.logaddexp(0.0, eta)))
    p = 1.0 / (1.0 + np.exp(-eta))
    w = n * p * (1.0 - p)
    sign, logdet = np.linalg.slogdet(X.T @ (X * w[:, None]))
    if sign <= 0:
        return -np.inf
    return ll + 0.5 * logdet


def firth_fit(X, y, n, max_iter: int = 200, tol: float = 1e-10,
              offset_fixed: Optional[Tuple[int, float]] = None,
              start: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    """Firth logistic regression on grouped binomial data (Newton on the modified score).

    X: (m, p) covariate patterns; y: events; n: trials per pattern.
    Modified score U*_r = sum_i x_ir (y_i - n_i p_i + h_i (1/2 - p_i)), h = diag of
    W^1/2 X (X'WX)^-1 X' W^1/2, W = n p (1 - p); step-halving on the penalized
    log-likelihood. offset_fixed = (j, value) holds coefficient j fixed (profile);
    start = starting coefficients (default 0). A numerically singular information
    matrix (all weights underflowed) ends the fit with pll = -inf, which a profile
    search reads as "far outside the interval".
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n = np.asarray(n, dtype=float)
    p_dim = X.shape[1]
    free = list(range(p_dim))
    beta = np.zeros(p_dim) if start is None else np.array(start, dtype=float)
    if offset_fixed is not None:
        j, val = offset_fixed
        beta[j] = val
        free.remove(j)
    cur = _firth_pll(beta, X, y, n)
    converged = False
    for it in range(max_iter):
        eta = X @ beta
        p = 1.0 / (1.0 + np.exp(-eta))
        w = n * p * (1.0 - p)
        info = X.T @ (X * w[:, None])
        try:
            inv = np.linalg.inv(info)
            xw = X * np.sqrt(w)[:, None]
            h = np.einsum("ij,jk,ik->i", xw, inv, xw)
            U = X.T @ (y - n * p + h * (0.5 - p))
            step = np.zeros(p_dim)
            step[free] = np.linalg.solve(info[np.ix_(free, free)], U[free])
        except np.linalg.LinAlgError:
            return {"beta": beta, "cov": None, "pll": -np.inf, "converged": False,
                    "iterations": it + 1, "singular": True}
        t = 1.0
        while True:
            cand = beta + t * step
            val = _firth_pll(cand, X, y, n)
            if val >= cur - 1e-12 or t < 1e-8:
                break
            t /= 2.0
        beta, cur = cand, val
        if np.max(np.abs(t * step)) < tol:
            converged = True
            break
    eta = X @ beta
    p = 1.0 / (1.0 + np.exp(-eta))
    w = n * p * (1.0 - p)
    try:
        cov = np.linalg.inv(X.T @ (X * w[:, None]))
    except np.linalg.LinAlgError:
        return {"beta": beta, "cov": None, "pll": -np.inf, "converged": False,
                "iterations": it + 1, "singular": True}
    return {"beta": beta, "cov": cov, "pll": cur, "converged": converged,
            "iterations": it + 1, "singular": False}


def firth_or_2x2(a: int, b: int, c: int, d: int) -> Dict[str, Any]:
    """Firth logistic y ~ 1 + depth6 on the 2 x 2; Wald and profile penalized-likelihood CIs."""
    from scipy.optimize import brentq

    X = np.array([[1.0, 1.0], [1.0, 0.0]])
    y = np.array([a, c], dtype=float)
    n = np.array([a + b, c + d], dtype=float)
    fit = firth_fit(X, y, n)
    b1 = float(fit["beta"][1])
    se = float(math.sqrt(fit["cov"][1, 1]))
    pmax = fit["pll"]

    b0_start = math.log((c + 0.5) / (d + 0.5))   # depth-1 row, Haldane-corrected logit

    def dev(v: float) -> float:
        prof = firth_fit(X, y, n, offset_fixed=(1, v), start=[b0_start, v])
        if not np.isfinite(prof["pll"]):
            return math.inf
        return 2.0 * (pmax - prof["pll"]) - CHI2_1_95

    def bound(direction: int) -> Optional[float]:
        step = max(1.0, 2.0 * se)
        lo_pt = b1
        for _ in range(60):
            hi_pt = lo_pt + direction * step
            if dev(hi_pt) > 0:
                return float(brentq(dev, min(lo_pt, hi_pt), max(lo_pt, hi_pt), xtol=1e-10))
            lo_pt = hi_pt
            step *= 1.5
        return None

    lo, hi = bound(-1), bound(+1)
    return {"method": "Firth (Jeffreys-prior penalized likelihood) logistic regression "
                      "y ~ 1 + depth6 on the crude 2 x 2, Newton on the modified score; "
                      "profile penalized-likelihood 95% CI (Heinze-Schemper) and Wald CI",
            "or": math.exp(b1), "log_or": b1, "se_log_or": se,
            "ci95_profile_penalized_likelihood": [math.exp(lo) if lo is not None else None,
                                                  math.exp(hi) if hi is not None else None],
            "ci95_wald": [math.exp(b1 - Z975 * se), math.exp(b1 + Z975 * se)],
            "converged": bool(fit["converged"]), "iterations": int(fit["iterations"])}


def benign_or_block(cells: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    a, b, c, d = table_2x2(cells, "benign")
    return {"table": {"depth6_events": a, "depth6_nonevents": b, "depth1_events": c,
                      "depth1_nonevents": d, "k6/n6": "%d/%d" % (a, a + b),
                      "k1/n1": "%d/%d" % (c, c + d)},
            "unit_note": "rows = (conversation, depth) views pooled over 5 models and 24 "
                         "scenarios, treated as independent (crude, NOT cluster-adjusted); "
                         "depth-1 and depth-6 rows of one conversation are both counted",
            "exact_conditional": exact_conditional_or(a, b, c, d),
            "firth": firth_or_2x2(a, b, c, d),
            "woolf": woolf_or(a, b, c, d)}


# -- (c) VB random-intercept SD -------------------------------------------------------


def vb_scenario_sd(long: pd.DataFrame, starts: int, seed: int) -> Dict[str, Any]:
    """Refit the frozen VB GLMM (y ~ depth6, scenario intercept) from K seeded starts."""
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

    data = long.copy()
    data["depth6"] = (data["depth"] == data["depth"].max()).astype(int)
    fits = []
    prior = None
    for k in range(starts):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = BinomialBayesMixedGLM.from_formula(
                "y ~ depth6", {"scen": "0 + C(scenario)"}, data)
            res = model.fit_vb(verbose=False, rng=np.random.default_rng(seed + k))
        prior = {"vcp_p_prior_sd_of_log_sd": float(model.vcp_p),
                 "fe_p_prior_sd_of_fixed_effects": float(model.fe_p)}
        names = list(res.model.exog_names)
        fe = dict(zip(names, map(float, res.fe_mean)))
        vm, vs = float(res.vcp_mean[0]), float(res.vcp_sd[0])
        fits.append({"start_seed": seed + k, "log_or_depth6": fe["depth6"],
                     "vcp_mean_log_sd": vm, "vcp_sd": vs, "sd": math.exp(vm),
                     "sd_vb_95": [math.exp(vm - Z975 * vs), math.exp(vm + Z975 * vs)]})
    sds = np.array([f["sd"] for f in fits])
    lors = np.array([f["log_or_depth6"] for f in fits])
    return {"model": "statsmodels BinomialBayesMixedGLM.fit_vb, y ~ depth6, random "
                     "intercept 0 + C(scenario) (scenario = base_item), frozen formula",
            "prior": prior,
            "n_rows": int(len(data)), "n_scenarios": int(data["scenario"].nunique()),
            "n_starts": int(starts),
            "sd_median": float(np.median(sds)), "sd_min": float(sds.min()),
            "sd_max": float(sds.max()),
            "sigma2_u_median": float(np.median(sds) ** 2),
            "log_or_median": float(np.median(lors)), "log_or_min": float(lors.min()),
            "log_or_max": float(lors.max()),
            "fits": fits}


# -- reproduction check ---------------------------------------------------------------


def counts_for(df: pd.DataFrame) -> Dict[str, Any]:
    return ph.depth_counts(df)


def compare_counts(mine: Dict[str, Any], ref: Dict[str, Any]) -> List[str]:
    """Differences between two posthoc_v1.depth_counts blocks (k/n, conversations)."""
    diffs = []
    for arm in ARMS:
        for key in ("depth1", "depth3", "depth6"):
            for f in ("events", "rows"):
                m, r = mine[arm][key][f], ref[arm][key][f]
                if m != r:
                    diffs.append("%s.%s.%s: %s != ref %s" % (arm, key, f, m, r))
        m, r = mine[arm]["conversations_selected"], ref[arm]["conversations_selected"]
        if m != r:
            diffs.append("%s.conversations_selected: %s != ref %s" % (arm, m, r))
    return diffs


def compare_repair(mine: Dict[str, Any], n1ref: Dict[str, Any],
                   d6ref: Optional[Dict[str, Any]]) -> List[str]:
    """R1/R2: events/rows at depths 1+6 vs the kyrameas n1.json; depth-6 flags vs summary."""
    diffs = []
    for arm in ARMS:
        ev = mine[arm]["depth1"]["events"] + mine[arm]["depth6"]["events"]
        rows = mine[arm]["depth1"]["rows"] + mine[arm]["depth6"]["rows"]
        if ev != n1ref[arm]["n_events"]:
            diffs.append("%s n_events %d != ref %s" % (arm, ev, n1ref[arm]["n_events"]))
        if rows != n1ref[arm]["n_rows"]:
            diffs.append("%s n_rows %d != ref %s" % (arm, rows, n1ref[arm]["n_rows"]))
    if mine["risk"]["conversations_selected"] != n1ref["counts"]["loc_conversations"]:
        diffs.append("risk conversations != ref")
    if mine["benign"]["conversations_selected"] != n1ref["counts"]["ben_conversations"]:
        diffs.append("benign conversations != ref")
    if d6ref is not None:
        for arm, key in (("benign", "benign_d6_cf_flags"), ("risk", "risk_d6_cf_flags")):
            if mine[arm]["depth6"]["events"] != d6ref[key]:
                diffs.append("%s depth6 events %d != summary %s"
                             % (arm, mine[arm]["depth6"]["events"], d6ref[key]))
    return diffs


# -- inputs ---------------------------------------------------------------------------


def repair_runs(repair_dir, variant: str) -> List[str]:
    runs = sorted(str(p) for p in Path(repair_dir, variant, "runs").glob("*/main/*")
                  if (p / "panel.jsonl").is_file())
    if len(runs) != 5:
        raise ValueError("%s: expected 5 main run dirs under %s/runs, found %d"
                         % (repair_dir, variant, len(runs)))
    return runs


def build_labeling(name: str, args, main_runs, out: Path, fam) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if name in ph.SCHEMES:
        runs, panels, changes = ph.write_relabeled_runs(main_runs, name, out / "runs")
        info = {"source": "adol main runs relabelled by posthoc_v1.relabel", "run_dirs": runs,
                "panel_changes": changes}
    else:
        runs = repair_runs(args.repair_dir, name)
        panels = [str(Path(r) / "panel.jsonl") for r in runs]
        info = {"source": "kyrameas repair check %s/%s/runs" % (args.repair_dir, name),
                "run_dirs": runs}
    info["panel_sha256"] = {p: sha256_file(p) for p in panels}
    df = loader.build_tidy(args.items, runs, panels, family_map=fam)
    return df, info


# -- output ---------------------------------------------------------------------------


def write_csv(rows: List[Dict[str, Any]], path) -> None:
    cols: List[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else sanitize(r.get(k))) for k in cols})


def _ci(v):
    return v if v is not None else [None, None]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kyra.analysis.posthoc_rd_v1", description=LABEL)
    p.add_argument("--root", default=ph.DEFAULT_ROOT)
    p.add_argument("--items", default=ph.DEFAULT_ITEMS)
    p.add_argument("--family-map", default=ph.DEFAULT_FAMILY_MAP)
    p.add_argument("--frozen-dir", default=ph.DEFAULT_FROZEN)
    p.add_argument("--ref-posthoc", default=DEFAULT_REF_POSTHOC)
    p.add_argument("--repair-dir", default=DEFAULT_REPAIR_DIR)
    p.add_argument("--out-root", default=ph.DEFAULT_OUT_ROOT)
    p.add_argument("--bootstrap", type=int, default=DEFAULT_B)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--vb-starts", type=int, default=DEFAULT_VB_STARTS)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logl: List[str] = []

    def log(msg: str) -> None:
        logl.append(msg)
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()

    try:
        main_runs, all_runs = ph.discover_runs(args.root)
        ph.check_runs(main_runs, all_runs)
        fam = json.loads(Path(args.family_map).read_text(encoding="utf-8"))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
        out = Path(args.out_root) / ("posthoc_rd_%s" % stamp)
        out.mkdir(parents=True, exist_ok=False)
        log("%s\nout=%s" % (LABEL, out))

        ref_b = json.loads((Path(args.ref_posthoc) / "b_n1_sensitivity.json").read_text("utf-8"))
        summ = json.loads((Path(args.repair_dir) / "summary.json").read_text("utf-8"))

        # 1. build every labeling and check its counts BEFORE computing anything new
        frames: Dict[str, pd.DataFrame] = {}
        infos: Dict[str, Dict[str, Any]] = {}
        repro: Dict[str, Any] = {}
        ok_all = True
        for name in LABELINGS:
            df, info = build_labeling(name, args, main_runs, out, fam)
            frames[name], infos[name] = df, info
            mine = counts_for(df)
            if name in ph.SCHEMES:
                ref = ref_b["schemes"][name]["counts"]
                diffs = compare_counts(mine, ref)
                refsrc = str(Path(args.ref_posthoc) / "b_n1_sensitivity.json")
                old_dir = Path(args.ref_posthoc) / "b_runs" / name
                same = {}
                for p, h in info["panel_sha256"].items():
                    oldp = old_dir / Path(p).parent.name / "panel.jsonl"
                    same[Path(p).parent.name] = oldp.is_file() and sha256_file(oldp) == h
                info["panel_identical_to_posthoc_20260927T2328Z"] = same
            else:
                n1ref = json.loads((Path(args.repair_dir) / name / "n1.json").read_text("utf-8"))
                diffs = compare_repair(mine, n1ref, summ["arms"][name].get("benign_depth6"))
                refsrc = "%s/%s/n1.json + summary.json" % (args.repair_dir, name)
            repro[name] = {"reference": refsrc, "counts": mine, "match": not diffs,
                           "differences": diffs}
            ok_all = ok_all and not diffs
            log("repro %s: %s %s" % (name, "MATCH" if not diffs else "MISMATCH", diffs or ""))
        loader.write_json(sanitize({"label": LABEL, "all_match": ok_all, "labelings": repro}),
                          out / "reproduction_check.json")
        if not ok_all:
            log("reproduction check FAILED: nothing new computed")
            (out / "posthoc_rd.log").write_text("\n".join(logl) + "\n", encoding="utf-8")
            return EXIT_MISMATCH

        # 2. new computations
        rd_seed = args.seed + RD_SEED_OFFSET
        sec_a, sec_b, sec_c = {}, {}, {}
        rows_a, rows_b, rows_c = [], [], []
        frozen_n1 = json.loads((Path(args.frozen_dir) / "n1.json").read_text("utf-8"))
        for name in LABELINGS:
            lr, lb = long_frames(frames[name])
            pooled = pooled_frame(lr, lb)
            a = rd_bootstrap(pooled, args.bootstrap, rd_seed)
            sec_a[name] = a
            c = a["cells"]
            row = {"labeling": name, "definition": LABELING_TEXT[name]}
            for key in ("risk_d1", "risk_d6", "benign_d1", "benign_d6"):
                row[key + "_k"], row[key + "_n"], row[key + "_p"] = c[key]["k"], c[key]["n"], c[key]["p"]
            for key in ("rd_risk", "rd_benign", "did"):
                ci = _ci(a[key]["ci95_cluster_bootstrap"])
                row[key], row[key + "_lo"], row[key + "_hi"] = a[key]["estimate"], ci[0], ci[1]
                row[key + "_undefined_reps"] = a[key]["bootstrap_undefined"]
            row["reps_0_benign_d1_events"] = a["bootstrap_replicates_with_0_benign_depth1_events"]
            rows_a.append(row)
            log("(a) %s risk %d/%d -> %d/%d  benign %d/%d -> %d/%d  RD_risk %.4f %s  RD_benign %.4f %s  DiD %.4f %s"
                % (name, c["risk_d1"]["k"], c["risk_d1"]["n"], c["risk_d6"]["k"], c["risk_d6"]["n"],
                   c["benign_d1"]["k"], c["benign_d1"]["n"], c["benign_d6"]["k"], c["benign_d6"]["n"],
                   a["rd_risk"]["estimate"], a["rd_risk"]["ci95_cluster_bootstrap"],
                   a["rd_benign"]["estimate"], a["rd_benign"]["ci95_cluster_bootstrap"],
                   a["did"]["estimate"], a["did"]["ci95_cluster_bootstrap"]))

            bb = benign_or_block(c)
            sec_b[name] = bb
            ex, fi, wo = bb["exact_conditional"], bb["firth"], bb["woolf"]
            rows_b.append({
                "labeling": name, "benign_k6": bb["table"]["depth6_events"],
                "benign_n6": bb["table"]["depth6_events"] + bb["table"]["depth6_nonevents"],
                "benign_k1": bb["table"]["depth1_events"],
                "benign_n1": bb["table"]["depth1_events"] + bb["table"]["depth1_nonevents"],
                "exact_or": ex["or"], "exact_lo": ex["ci95"][0], "exact_hi": ex["ci95"][1],
                "firth_or": fi["or"],
                "firth_pl_lo": fi["ci95_profile_penalized_likelihood"][0],
                "firth_pl_hi": fi["ci95_profile_penalized_likelihood"][1],
                "firth_wald_lo": fi["ci95_wald"][0], "firth_wald_hi": fi["ci95_wald"][1],
                "woolf_haldane_or": wo["haldane"]["or"], "woolf_haldane_lo": wo["haldane"]["ci95"][0],
                "woolf_haldane_hi": wo["haldane"]["ci95"][1],
                "woolf_uncorrected_or": wo["uncorrected"].get("or"),
                "woolf_uncorrected_lo": (wo["uncorrected"].get("ci95") or [None, None])[0],
                "woolf_uncorrected_hi": (wo["uncorrected"].get("ci95") or [None, None])[1],
            })
            log("(b) %s benign exact %.4g %s  Firth %.4g PL %s  Woolf-Haldane %.4g %s"
                % (name, ex["or"], ex["ci95"], fi["or"], fi["ci95_profile_penalized_likelihood"],
                   wo["haldane"]["or"], wo["haldane"]["ci95"]))

            sec_c[name] = {}
            for arm, lng in (("risk", lr), ("benign", lb)):
                v = vb_scenario_sd(lng, args.vb_starts, args.seed)
                if name == "S0":
                    v["frozen_n1_log_or"] = frozen_n1[arm]["log_or"]
                    v["frozen_n1_note"] = "the frozen fit (rng=None) stored only the fixed effect"
                sec_c[name][arm] = v
                rows_c.append({"labeling": name, "arm": arm, "n_rows": v["n_rows"],
                               "n_events": int(lng["y"].sum()),
                               "n_scenarios": v["n_scenarios"], "n_starts": v["n_starts"],
                               "sd_median": v["sd_median"], "sd_min": v["sd_min"],
                               "sd_max": v["sd_max"], "sigma2_u_median": v["sigma2_u_median"],
                               "log_or_median": v["log_or_median"],
                               "vcp_p": v["prior"]["vcp_p_prior_sd_of_log_sd"],
                               "fe_p": v["prior"]["fe_p_prior_sd_of_fixed_effects"]})
                log("(c) %s %s VB scenario SD median %.4f [min %.4f, max %.4f] over %d starts; log OR median %.4f"
                    % (name, arm, v["sd_median"], v["sd_min"], v["sd_max"], v["n_starts"],
                       v["log_or_median"]))

        code = Path(__file__).resolve()
        hashes = {
            "code": {str(code): sha256_file(code),
                     str(Path(ph.__file__).resolve()): sha256_file(ph.__file__),
                     str(Path(n1.__file__).resolve()): sha256_file(n1.__file__),
                     str(Path(loader.__file__).resolve()): sha256_file(loader.__file__)},
            "inputs": {args.items: sha256_file(args.items),
                       args.family_map: sha256_file(args.family_map),
                       str(Path(args.frozen_dir) / "n1.json"): sha256_file(Path(args.frozen_dir) / "n1.json"),
                       str(Path(args.ref_posthoc) / "b_n1_sensitivity.json"):
                           sha256_file(Path(args.ref_posthoc) / "b_n1_sensitivity.json"),
                       str(Path(args.repair_dir) / "summary.json"):
                           sha256_file(Path(args.repair_dir) / "summary.json")},
        }
        for v in ("R1", "R2"):
            pth = Path(args.repair_dir) / v / "n1.json"
            hashes["inputs"][str(pth)] = sha256_file(pth)
        for run in main_runs:
            for nm in ("panel.jsonl", "judge_J1.jsonl", "judge_J2.jsonl", "judge_J3.jsonl",
                       "manifest.jsonl", "responses.jsonl"):
                hashes["inputs"][str(Path(run) / nm)] = sha256_file(Path(run) / nm)
        for name in LABELINGS:
            for p, h in infos[name]["panel_sha256"].items():
                hashes["inputs"][p] = h

        result = {
            "label": LABEL,
            "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "command": "PYTHONPATH=src python -m kyra.analysis.posthoc_rd_v1 %s" % " ".join(sys.argv[1:]),
            "protocol": loader.version_string(),
            "frozen_results_unchanged": args.frozen_dir,
            "labelings": {k: LABELING_TEXT[k] for k in LABELINGS},
            "labeling_sources": infos,
            "reproduction_check": {"all_match": ok_all, "file": "reproduction_check.json"},
            "population": "N1 rows: 24 six-turn localized LOC risk scripts and their BEN twins x 5 "
                          "main runs, depths 1 and 6, frozen n1_escalation selection (n_turns >= 6)",
            "a_rd_did": {
                "method": "RD = k6/n6 - k1/n1 per arm over pooled (conversation, depth) rows; "
                          "DiD = RD_risk - RD_benign; percentile 95%% CI from a scenario-cluster "
                          "bootstrap (B = %d; one replicate draws the sorted base items with "
                          "replacement via default_rng(%d).choice, every row of a drawn base "
                          "item -- risk and twin, all models, both depths -- moves together; "
                          "same stream as the paper's interaction bootstrap, seed %d + %d). "
                          "Proportions, not percentage points." % (args.bootstrap, rd_seed,
                                                                   args.seed, RD_SEED_OFFSET),
                "labelings": sec_a},
            "b_benign_or": {"labelings": sec_b},
            "c_vb_scenario_sd": {
                "note": "SD = exp(posterior mean of log SD) of the scenario random intercept; "
                        "statsmodels fit_vb with the frozen formula; the frozen _fit_vb used "
                        "rng=None (OS-entropy start values), so it is refitted here from %d "
                        "seeded starts (seeds %d..%d) and the spread is reported; VB posterior "
                        "SDs are optimistic (as stated in the paper). Not stored in the frozen "
                        "n1.json." % (args.vb_starts, args.seed, args.seed + args.vb_starts - 1),
                "labelings": sec_c},
            "hashes": hashes,
        }
        loader.write_json(sanitize(result), out / "posthoc_rd.json")
        write_csv(rows_a, out / "a_rd_did.csv")
        write_csv(rows_b, out / "b_benign_or.csv")
        write_csv(rows_c, out / "c_vb_scenario_sd.csv")
        log("wrote posthoc_rd.json a_rd_did.csv b_benign_or.csv c_vb_scenario_sd.csv "
            "reproduction_check.json")
        (out / "posthoc_rd.log").write_text("\n".join(logl) + "\n", encoding="utf-8")
    except (ValueError, RuntimeError, KeyError, FileNotFoundError) as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return EXIT_BAD_INPUT
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
