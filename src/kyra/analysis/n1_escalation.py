"""N1 -- critical failure rises with turn depth (PREREGISTERED_kyra_v2.yaml).

Registered definition used here, verbatim from the freeze:
  window          "fixed prefixes of 1, 3 and 6 turns"
  N1.1 metric     OR(critical failure, 6-turn vs 1-turn) in risk scripts,
                  logistic GLMM with a scenario random effect, scenario
                  cluster bootstrap 95% CI (B = 2000)
  N1.2 metric     the same OR in the item-paired benign twins, plus the
                  risk x turn-depth interaction (Holm-adjusted p)

So the outcome is "a critical failure has been observed by turn depth d"
for d in {1, 3, 6}, read off the SAME 6-turn conversation: one row per
(conversation, depth).  The primary contrast is d = 6 vs d = 1; d = 3 vs
d = 1 is reported as secondary.

Point estimate: statsmodels BinomialBayesMixedGLM (variational Bayes),
scenario (base_item) random intercept.  95% CI: percentile scenario
cluster bootstrap, the same estimator refitted on each resample.
p-values are Wald statistics from the VB posterior (mean / sd); VB
posterior SDs are known to be optimistic, so the CI -- not the p -- is
the CI of record, and this is stated in the output.

Sensitivity: GEE with an exchangeable working correlation, clustered on
the scenario, robust SEs.

This module reports; it never judges.  The G6 script applies the frozen
decision rules to its output.

Output JSON schema (the names G6 reads)
---------------------------------------
version              "PREREGISTERED_kyra_v2.yaml@<sha256>"
analysis             "n1_escalation"
or                   float   OR(critical failure, depth 6 vs depth 1), LOC risk
ci95                 [lo, hi]  scenario cluster bootstrap, the interval of record
benign_or            float   the same contrast in the BEN twins
benign_ci95          [lo, hi]
interaction_p        float   risk x depth, Holm-adjusted BOOTSTRAP p (primary)
interaction_p_vb     float   the same term's raw VB Wald p (secondary)
n, B, seed           int
risk / benign        {or, ci95, log_or, se_vb, p_bootstrap, p_wald_vb, p_holm,
                      p_holm_vb, bootstrap_b, bootstrap_used,
                      bootstrap_failures, n_rows, n_scenarios, n_models,
                      n_events}
risk_depth3_vs_1     the same block for the secondary depth-3 contrast
interaction          {term, or, ci95, log_or, se_vb, p_bootstrap, p_wald_vb,
                      p_holm, p_holm_vb, bootstrap_*}
sensitivity_gee      {model, or, ci95, log_or, p}
counts               {loc_conversations, ben_conversations, scenarios, models}
"""

from __future__ import annotations

import sys
import warnings
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from kyra.analysis import loader
from kyra.analysis.loader import EmptyInput, clean_float

DEFAULT_B = 2000
DEFAULT_SEED = 20260922
MIN_DEPTH_TURNS = 6


# -- model fitting -----------------------------------------------------------


def _fit_vb(data: pd.DataFrame, formula: str, cluster: str = "scenario"):
    """Logistic GLMM by variational Bayes; returns (mean, sd) dicts by term."""
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = BinomialBayesMixedGLM.from_formula(
            formula, {"scen": "0 + C(%s)" % cluster}, data
        )
        res = model.fit_vb(verbose=False)
    names = list(res.model.exog_names)
    return dict(zip(names, map(float, res.fe_mean))), dict(zip(names, map(float, res.fe_sd)))


def _fit_gee(data: pd.DataFrame, formula: str, cluster: str = "scenario"):
    import statsmodels.api as sm
    import statsmodels.formula.api as smf

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = smf.gee(
            formula, groups=cluster, data=data,
            family=sm.families.Binomial(), cov_struct=sm.cov_struct.Exchangeable(),
        ).fit()
    return res


def _wald_p(mean: float, sd: float) -> float:
    from scipy import stats

    if sd is None or not np.isfinite(sd) or sd <= 0:
        return float("nan")
    return float(2.0 * stats.norm.sf(abs(mean) / sd))


def holm(pvals: Dict[str, float]) -> Dict[str, float]:
    """Holm step-down adjustment over a named family of p-values."""
    items = [(k, v) for k, v in pvals.items() if v is not None and np.isfinite(v)]
    n = len(items)
    items.sort(key=lambda kv: kv[1])
    out: Dict[str, float] = {k: float("nan") for k in pvals}
    running = 0.0
    for i, (k, p) in enumerate(items):
        adj = min(1.0, (n - i) * p)
        running = max(running, adj)
        out[k] = running
    return out


# -- data shaping ------------------------------------------------------------


def depth_frame(df: pd.DataFrame, depths=(1, 6)) -> pd.DataFrame:
    """One row per (conversation, depth) with the by-depth critical outcome."""
    rows: List[Dict[str, Any]] = []
    for rec in df.to_dict("records"):
        for d in depths:
            col = "crit_by_depth_%d" % d
            val = rec.get(col)
            if val is None or (isinstance(val, float) and np.isnan(val)):
                continue
            rows.append({
                "scenario": rec["base_item"],
                "model_id": rec["model_id"],
                "item_id": rec["item_id"],
                "condition": rec["condition"],
                "depth": d,
                "y": int(val),
            })
    return pd.DataFrame(rows)


def _select(df: pd.DataFrame, condition: str) -> pd.DataFrame:
    sel = df[(df["condition"] == condition) & (df["n_turns"] >= MIN_DEPTH_TURNS)]
    return sel.copy()


def _check_depths(df: pd.DataFrame, label: str) -> None:
    cols = ["crit_by_depth_%d" % d for d in (1, 6)]
    if len(df) and all(df[c].isna().all() for c in cols):
        raise ValueError(
            "%s: no by-depth critical-failure outcome is available, so "
            "OR(6-turn vs 1-turn) cannot be computed. Supply either a "
            "per-turn critical series (crit_turns / per-turn panel records, "
            "one 6-turn conversation) or explicit crit_by_depth_1 / _3 / _6 "
            "columns (one conversation per prefix depth). kyra.panel v0 "
            "records only a conversation-level flag." % label
        )


# -- estimation --------------------------------------------------------------


def _cluster_resample(data: pd.DataFrame, rng) -> pd.DataFrame:
    """Resample whole scenarios with replacement; duplicates become new clusters."""
    scenarios = sorted(data["scenario"].unique())
    by_scen = {s: g for s, g in data.groupby("scenario")}
    picks = rng.choice(len(scenarios), size=len(scenarios), replace=True)
    parts = []
    for k, idx in enumerate(picks):
        g = by_scen[scenarios[idx]].copy()
        g["scenario"] = "%s#%d" % (scenarios[idx], k)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def bootstrap_p(boots: List[float], null: float = 0.0) -> float:
    """Two-sided percentile bootstrap p-value for a coefficient.

    p = 2 * min(#{b <= null}, #{b >= null}) / B, with the usual +1
    continuity correction so an all-on-one-side bootstrap reports
    2/(B+1) rather than an impossible 0.
    """
    if not boots:
        return float("nan")
    arr = np.asarray(boots, dtype=float)
    n = arr.size
    n_le = int(np.sum(arr <= null))
    n_ge = int(np.sum(arr >= null))
    return float(min(1.0, 2.0 * (min(n_le, n_ge) + 1) / (n + 1)))


def _or_with_bootstrap(long: pd.DataFrame, B: int, seed: int,
                       predictor: str = "depth6") -> Dict[str, Any]:
    """VB-GLMM point estimate + scenario cluster bootstrap percentile CI."""
    data = long.copy()
    data[predictor] = (data["depth"] == data["depth"].max()).astype(int)
    fe, fesd = _fit_vb(data, "y ~ %s" % predictor)
    log_or = fe[predictor]

    scenarios = sorted(data["scenario"].unique())
    rng = np.random.default_rng(seed)
    boots: List[float] = []
    failures = 0
    for _ in range(B):
        rep = _cluster_resample(data, rng)
        try:
            fe_b, _ = _fit_vb(rep, "y ~ %s" % predictor)
            v = fe_b[predictor]
            if not np.isfinite(v):
                raise ValueError("non-finite estimate")
            boots.append(float(v))
        except Exception:  # a replicate that will not fit is counted, not patched
            failures += 1
    if len(boots) < max(20, B // 10):
        raise ValueError(
            "scenario cluster bootstrap failed on %d of %d replicates: "
            "no usable CI" % (failures, B)
        )
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {
        "log_or": float(log_or),
        "or": float(np.exp(log_or)),
        "ci95": [float(np.exp(lo)), float(np.exp(hi))],
        "ci95_log_or": [float(lo), float(hi)],
        "se_vb": clean_float(fesd.get(predictor)),
        "p_wald_vb": clean_float(_wald_p(log_or, fesd.get(predictor, float("nan")))),
        "p_bootstrap": clean_float(bootstrap_p(boots)),
        "bootstrap_b": int(B),
        "bootstrap_used": int(len(boots)),
        "bootstrap_failures": int(failures),
        "n_rows": int(len(data)),
        "n_scenarios": int(len(scenarios)),
        "n_models": int(data["model_id"].nunique()),
        "n_events": int(data["y"].sum()),
    }


def analyse(df: pd.DataFrame, B: int = DEFAULT_B, seed: int = DEFAULT_SEED) -> Dict[str, Any]:
    risk = _select(df, "LOC")
    risk = risk[risk["risk_group"].astype(str) != "CTRL"] if "risk_group" in risk else risk
    _check_depths(risk, "LOC (risk) conversations")
    long_risk = depth_frame(risk, depths=(1, 6))
    if long_risk.empty or long_risk["depth"].nunique() < 2:
        raise EmptyInput(
            "no LOC conversations with at least %d turns carrying both a "
            "depth-1 and a depth-6 outcome: N1 has no data" % MIN_DEPTH_TURNS
        )

    primary = _or_with_bootstrap(long_risk, B, seed)

    secondary: Optional[Dict[str, Any]] = None
    long13 = depth_frame(risk, depths=(1, 3))
    if not long13.empty and long13["depth"].nunique() == 2:
        try:
            secondary = _or_with_bootstrap(long13, B, seed + 1, predictor="depth3")
        except (ValueError, RuntimeError) as exc:
            secondary = {"error": str(exc)}

    benign = _select(df, "BEN")
    benign_res: Dict[str, Any]
    long_ben = depth_frame(benign, depths=(1, 6)) if len(benign) else pd.DataFrame()
    if long_ben.empty:
        benign_res = {"error": "no BEN (benign twin) conversations with a "
                               "per-turn critical series"}
    else:
        try:
            benign_res = _or_with_bootstrap(long_ben, B, seed + 2)
        except (ValueError, RuntimeError) as exc:
            benign_res = {"error": str(exc)}

    interaction: Dict[str, Any]
    if long_ben.empty:
        interaction = {"error": "no benign twins: the risk x depth interaction "
                                "is not estimable"}
    else:
        pooled = pd.concat([long_risk.assign(risk=1), long_ben.assign(risk=0)],
                           ignore_index=True)
        pooled["depth6"] = (pooled["depth"] == 6).astype(int)
        try:
            fe, fesd = _fit_vb(pooled, "y ~ depth6 * risk")
            term = "depth6:risk"
            if term not in fe:
                term = [k for k in fe if ":" in k][0]
            rng = np.random.default_rng(seed + 3)
            boots: List[float] = []
            failures = 0
            for _ in range(B):
                rep = _cluster_resample(pooled, rng)
                try:
                    fe_b, _ = _fit_vb(rep, "y ~ depth6 * risk")
                    v = fe_b[term]
                    if not np.isfinite(v):
                        raise ValueError("non-finite estimate")
                    boots.append(float(v))
                except Exception:
                    failures += 1
            if len(boots) < max(20, B // 10):
                raise ValueError("interaction bootstrap failed on %d of %d replicates"
                                 % (failures, B))
            lo, hi = np.percentile(boots, [2.5, 97.5])
            interaction = {
                "term": term,
                "log_or": clean_float(fe[term]),
                "or": clean_float(np.exp(fe[term])),
                "ci95": [float(np.exp(lo)), float(np.exp(hi))],
                "ci95_log_or": [float(lo), float(hi)],
                "se_vb": clean_float(fesd[term]),
                "p_bootstrap": clean_float(bootstrap_p(boots)),
                "p_wald_vb": clean_float(_wald_p(fe[term], fesd[term])),
                "bootstrap_b": int(B),
                "bootstrap_used": int(len(boots)),
                "bootstrap_failures": int(failures),
                "n_rows": int(len(pooled)),
            }
        except Exception as exc:
            interaction = {"error": "interaction GLMM did not fit: %s" % exc}

    # Holm within the N1 family, on the BOOTSTRAP p-values (the cluster
    # bootstrap is the inference of record); the VB Wald family is adjusted
    # too and reported as the secondary reading.
    for key, source in (("p_holm", "p_bootstrap"), ("p_holm_vb", "p_wald_vb")):
        fam = {
            "n1_risk_depth": primary.get(source),
            "n1_benign_depth": benign_res.get(source),
            "n1_risk_by_depth_interaction": interaction.get(source),
        }
        adj = holm({k: v for k, v in fam.items() if v is not None})
        if source in primary:
            primary[key] = clean_float(adj.get("n1_risk_depth", float("nan")))
        if source in benign_res:
            benign_res[key] = clean_float(adj.get("n1_benign_depth", float("nan")))
        if source in interaction:
            interaction[key] = clean_float(
                adj.get("n1_risk_by_depth_interaction", float("nan")))

    sens: Dict[str, Any]
    try:
        d = long_risk.copy()
        d["depth6"] = (d["depth"] == 6).astype(int)
        res = _fit_gee(d, "y ~ depth6")
        ci = res.conf_int()
        sens = {
            "model": "GEE binomial, exchangeable working correlation, "
                     "clusters = scenario (base_item), robust SE",
            "log_or": float(res.params["depth6"]),
            "or": float(np.exp(res.params["depth6"])),
            "ci95": [float(np.exp(ci.loc["depth6", 0])), float(np.exp(ci.loc["depth6", 1]))],
            "p": float(res.pvalues["depth6"]),
        }
    except Exception as exc:
        sens = {"error": "GEE sensitivity fit failed: %s" % exc}

    return {
        "version": loader.version_string(),
        "analysis": "n1_escalation",
        "claim": "N1 / N1.1 / N1.2",
        "outcome": "critical failure observed by turn depth d (fixed prefixes "
                   "of 1, 3 and 6 turns) on the same 6-turn conversation",
        "primary_contrast": "depth 6 vs depth 1, LOC risk conversations",
        "estimator": "BinomialBayesMixedGLM (variational Bayes), scenario "
                     "(base_item) random intercept",
        "ci_method": "percentile scenario cluster bootstrap, estimator refitted "
                     "per replicate",
        "p_method": "two-sided percentile bootstrap p from the scenario cluster "
                    "bootstrap distribution of the coefficient; the VB Wald p "
                    "(optimistic posterior SDs) is reported as the secondary "
                    "*_vb reading. Bootstrap CIs are the intervals of record.",
        "multiplicity": "Holm within the N1 family "
                        "{risk depth, benign depth, risk x depth}",
        "or": primary["or"],
        "ci95": primary["ci95"],
        "interaction_p": interaction.get("p_holm"),
        "interaction_p_vb": interaction.get("p_wald_vb"),
        "benign_or": benign_res.get("or"),
        "benign_ci95": benign_res.get("ci95"),
        "n": int(len(risk)),
        "B": int(B),
        "seed": int(seed),
        "risk": primary,
        "risk_depth3_vs_1": secondary,
        "benign": benign_res,
        "interaction": interaction,
        "sensitivity_gee": sens,
        "counts": {
            "loc_conversations": int(len(risk)),
            "ben_conversations": int(len(benign)),
            "scenarios": int(risk["base_item"].nunique()),
            "models": int(risk["model_id"].nunique()),
        },
    }


def _extra(p):
    p.add_argument("--bootstrap", type=int, default=DEFAULT_B,
                   help="cluster bootstrap replicates B (default %d)" % DEFAULT_B)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)


def main(argv=None) -> int:
    return loader.run_cli(
        lambda df, args: analyse(df, B=args.bootstrap, seed=args.seed),
        argv, "kyra.analysis.n1_escalation",
        "N1: OR(critical failure, 6-turn vs 1-turn) with benign twin and interaction",
        extra_args=_extra,
    )


if __name__ == "__main__":
    sys.exit(main())
