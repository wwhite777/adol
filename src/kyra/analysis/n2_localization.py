"""N2 -- does localizing a literal Korean item change measured failure?

Registered metric (PREREGISTERED_kyra_v2.yaml):
  "paired difference in critical-failure rate (localized minus literal),
   paired GLMM, 95% CI; TOST at +/- 0.03"

Unit of pairing: (base_item, model) -- the LOC and LIT twins of the same
scenario answered by the same model.  The estimand is on the PROBABILITY
scale (a risk difference), because that is the scale the +/- 0.03
equivalence bound is written on; the primary interval therefore comes
from a paired mixed model with a pair random intercept fitted as a
linear probability model.  If that fit fails, the primary interval falls
back to a paired cluster bootstrap and "ci_method" says so.  A logistic
GLMM (BinomialBayesMixedGLM, pair random intercept) is reported
alongside as a log-odds companion, never as the headline number.

Output JSON schema (the names G6 reads)
---------------------------------------
version              "PREREGISTERED_kyra_v2.yaml@<sha256>"
analysis             "n2_localization"
estimate             float    mean paired difference, LOC minus LIT
ci95                 [lo, hi] from `ci_method`
ci_method            "paired_mixed_model_lpm" | "paired_cluster_bootstrap_pairs"
se                   float
tost                 {bound, p_lower, p_upper, p, alpha, equivalent, method}
primary              {estimate, se, ci95, model}
bootstrap_pairs      {estimate, se, ci95, model}
bootstrap_scenario_cluster   the same, clustered on base_item
glmm_companion       {log_or, or, se_vb, model}  (log-odds only, not the headline)
rates                {loc, lit}
components           "not_separable_in_phase_A"   + components_note
n_pairs, n_base_items, n_models, n_discordant_loc_only,
n_discordant_lit_only, B, seed, notes[]

Components of the localization treatment (slang/school/peer context vs
local crisis resources vs ...) are NOT separable in phase A: each item
has a single rewrite, so no design contrast isolates a component.  The
output says so with the flag `components: not_separable_in_phase_A`
rather than reporting an invented decomposition.
"""

from __future__ import annotations

import sys
import warnings
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from kyra.analysis import loader
from kyra.analysis.loader import EmptyInput, clean_float

DEFAULT_B = 2000
DEFAULT_SEED = 20260922
TOST_BOUND = 0.03


def build_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (base_item, model) that has BOTH a LOC and a LIT twin."""
    sel = df[df["condition"].isin(["LOC", "LIT"])]
    rows: List[Dict[str, Any]] = []
    for (base, model), g in sel.groupby(["base_item", "model_id"]):
        loc = g[g["condition"] == "LOC"]
        lit = g[g["condition"] == "LIT"]
        if len(loc) != 1 or len(lit) != 1:
            continue
        y_loc = int(loc.iloc[0]["critical_any"])
        y_lit = int(lit.iloc[0]["critical_any"])
        rows.append({
            "pair_id": "%s|%s" % (base, model),
            "base_item": base,
            "model_id": model,
            "y_loc": y_loc,
            "y_lit": y_lit,
            "diff": y_loc - y_lit,
        })
    return pd.DataFrame(rows)


def _long(pairs: pd.DataFrame) -> pd.DataFrame:
    a = pairs[["pair_id", "base_item", "model_id", "y_loc"]].rename(columns={"y_loc": "y"})
    a["loc"] = 1
    b = pairs[["pair_id", "base_item", "model_id", "y_lit"]].rename(columns={"y_lit": "y"})
    b["loc"] = 0
    return pd.concat([a, b], ignore_index=True)


def _mixed_lpm(pairs: pd.DataFrame) -> Dict[str, Any]:
    import statsmodels.formula.api as smf

    data = _long(pairs)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = smf.mixedlm("y ~ loc", data, groups=data["pair_id"]).fit()
    ci = res.conf_int()
    return {
        "estimate": float(res.params["loc"]),
        "se": float(res.bse["loc"]),
        "ci95": [float(ci.loc["loc", 0]), float(ci.loc["loc", 1])],
        "model": "MixedLM (linear probability model) y ~ loc, "
                 "random intercept per (base_item, model) pair",
    }


def _bootstrap_diff(pairs: pd.DataFrame, unit: str, B: int, seed: int) -> Dict[str, Any]:
    rng = np.random.default_rng(seed)
    if unit == "pair":
        values = pairs["diff"].to_numpy(dtype=float)
        n = len(values)
        idx = rng.integers(0, n, size=(B, n))
        boots = values[idx].mean(axis=1)
    elif unit == "scenario":
        groups = [g["diff"].to_numpy(dtype=float) for _, g in pairs.groupby("base_item")]
        n = len(groups)
        boots = np.empty(B, dtype=float)
        for b in range(B):
            picks = rng.integers(0, n, size=n)
            boots[b] = np.concatenate([groups[i] for i in picks]).mean()
    else:
        raise ValueError("unknown bootstrap unit %r" % unit)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {
        "estimate": float(pairs["diff"].mean()),
        "se": float(np.std(boots, ddof=1)),
        "ci95": [float(lo), float(hi)],
        "model": "percentile cluster bootstrap over %ss (B = %d)" % (unit, B),
    }


def _tost(estimate: float, se: float, bound: float = TOST_BOUND) -> Dict[str, Any]:
    from scipy import stats

    if se is None or not np.isfinite(se) or se <= 0:
        return {"bound": bound, "error": "no usable standard error for TOST"}
    t_lower = (estimate + bound) / se     # H0: estimate <= -bound
    t_upper = (estimate - bound) / se     # H0: estimate >= +bound
    p_lower = float(stats.norm.sf(t_lower))
    p_upper = float(stats.norm.cdf(t_upper))
    p = max(p_lower, p_upper)
    return {
        "bound": bound,
        "p_lower": p_lower,
        "p_upper": p_upper,
        "p": p,
        "alpha": 0.05,
        "equivalent": bool(p < 0.05),
        "method": "two one-sided z tests on the primary standard error",
    }


def analyse(df: pd.DataFrame, B: int = DEFAULT_B, seed: int = DEFAULT_SEED,
            bound: float = TOST_BOUND) -> Dict[str, Any]:
    loader.require_one_run_per_model(df, "n2_localization")
    pairs = build_pairs(df)
    if pairs.empty:
        raise EmptyInput(
            "no (base_item, model) pair carries both a LOC and a LIT twin: "
            "N2 has no data"
        )

    notes: List[str] = []
    try:
        primary = _mixed_lpm(pairs)
        ci_method = "paired_mixed_model_lpm"
    except Exception as exc:
        notes.append("paired mixed model did not fit (%s); primary CI is the "
                     "paired cluster bootstrap over pairs" % exc)
        primary = _bootstrap_diff(pairs, "pair", B, seed)
        ci_method = "paired_cluster_bootstrap_pairs"

    boot_pair = _bootstrap_diff(pairs, "pair", B, seed)
    boot_scen = _bootstrap_diff(pairs, "scenario", B, seed + 1)

    glmm: Dict[str, Any]
    try:
        from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

        data = _long(pairs)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = BinomialBayesMixedGLM.from_formula(
                "y ~ loc", {"pair": "0 + C(pair_id)"}, data).fit_vb(verbose=False)
        names = list(res.model.exog_names)
        i = names.index("loc")
        glmm = {
            "log_or": float(res.fe_mean[i]),
            "or": float(np.exp(res.fe_mean[i])),
            "se_vb": float(res.fe_sd[i]),
            "model": "BinomialBayesMixedGLM (VB), pair random intercept "
                     "(log-odds companion; not the headline estimand)",
        }
    except Exception as exc:
        glmm = {"error": "logistic paired GLMM did not fit: %s" % exc}

    est = float(pairs["diff"].mean())
    return {
        "version": loader.version_string(),
        "analysis": "n2_localization",
        "claim": "N2",
        "estimand": "paired difference in critical-failure rate, "
                    "localized (LOC) minus literal (LIT), per (base_item, model)",
        "estimate": est,
        "ci95": primary["ci95"],
        "ci_method": ci_method,
        "primary": primary,
        "se": clean_float(primary.get("se")),
        "tost": _tost(est, primary.get("se"), bound),
        "bootstrap_pairs": boot_pair,
        "bootstrap_scenario_cluster": boot_scen,
        "glmm_companion": glmm,
        "rates": {
            "loc": float(pairs["y_loc"].mean()),
            "lit": float(pairs["y_lit"].mean()),
        },
        "components": "not_separable_in_phase_A",
        "components_note": "phase A applies ONE rewrite per item, so no design "
                           "contrast separates the localization components "
                           "(slang / school / peer context / local crisis "
                           "resources). No decomposition is reported.",
        "n_pairs": int(len(pairs)),
        "n_base_items": int(pairs["base_item"].nunique()),
        "n_models": int(pairs["model_id"].nunique()),
        "n_discordant_loc_only": int((pairs["diff"] == 1).sum()),
        "n_discordant_lit_only": int((pairs["diff"] == -1).sum()),
        "B": int(B),
        "seed": int(seed),
        "notes": notes,
    }


def _extra(p):
    p.add_argument("--bootstrap", type=int, default=DEFAULT_B)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--tost-bound", type=float, default=TOST_BOUND)


def main(argv=None) -> int:
    return loader.run_cli(
        lambda df, args: analyse(df, B=args.bootstrap, seed=args.seed,
                                 bound=args.tost_bound),
        argv, "kyra.analysis.n2_localization",
        "N2: paired LOC-minus-LIT difference in critical-failure rate with TOST",
        extra_args=_extra,
    )


if __name__ == "__main__":
    sys.exit(main())
