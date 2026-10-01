"""Tests for kyra.analysis.posthoc_rd_v1 (POST-HOC, not confirmatory).

Synthetic fixtures only; no run data is read.

Run with:
  cd /home/wjeong/adol && PYTHONPATH=src \
    ~/envs/jeongwoncheol_adol/bin/python -m unittest discover -s test \
    -p "test_posthoc_rd_v1.py" -v
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from kyra.analysis import posthoc_rd_v1 as rd  # noqa: E402


def rows(scenario, arm, depth, k, n):
    return [{"scenario": scenario, "arm": arm, "depth": depth, "y": int(i < k),
             "model_id": "m", "item_id": scenario, "condition": "base"} for i in range(n)]


def fixture_two_scenarios():
    """A: risk 0/1 -> 1/1, benign 0/1 -> 0/1.  B: risk 0/1 -> 0/1, benign 0/1 -> 1/1.

    Point: RD_risk = 0.5, RD_benign = 0.5, DiD = 0.
    Bootstrap (scenarios resampled with all their rows): AA (1/4) -> (1, 0, 1);
    AB/BA (1/2) -> (0.5, 0.5, 0); BB (1/4) -> (0, 1, -1).
    """
    r = []
    r += rows("A", "risk", 1, 0, 1) + rows("A", "risk", 6, 1, 1)
    r += rows("A", "benign", 1, 0, 1) + rows("A", "benign", 6, 0, 1)
    r += rows("B", "risk", 1, 0, 1) + rows("B", "risk", 6, 0, 1)
    r += rows("B", "benign", 1, 0, 1) + rows("B", "benign", 6, 1, 1)
    return pd.DataFrame(r)


class TestRDBootstrap(unittest.TestCase):
    def test_point_and_known_bootstrap_distribution(self):
        out = rd.rd_bootstrap(fixture_two_scenarios(), B=4000, seed=1)
        self.assertAlmostEqual(out["rd_risk"]["estimate"], 0.5)
        self.assertAlmostEqual(out["rd_benign"]["estimate"], 0.5)
        self.assertAlmostEqual(out["did"]["estimate"], 0.0)
        self.assertEqual(out["cells"]["risk_d6"], {"k": 1, "n": 2, "p": 0.5})
        self.assertEqual(out["rd_risk"]["ci95_cluster_bootstrap"], [0.0, 1.0])
        self.assertEqual(out["did"]["ci95_cluster_bootstrap"], [-1.0, 1.0])
        # re-draw the same stream to check the distribution and joint resampling
        scen, K, N = rd.scenario_counts(fixture_two_scenarios())
        rng = np.random.default_rng(1)
        dids = []
        for _ in range(4000):
            p = rng.choice(len(scen), size=len(scen), replace=True)
            dids.append(rd.rd_stats(K[p].sum(0), N[p].sum(0))["did"])
        vals, cnt = np.unique(np.round(dids, 9), return_counts=True)
        # arms move together: only -1, 0, 1 are possible (independent arms would add +-0.5)
        self.assertEqual(sorted(vals.tolist()), [-1.0, 0.0, 1.0])
        freq = dict(zip(vals.tolist(), (cnt / 4000).tolist()))
        self.assertAlmostEqual(freq[0.0], 0.5, delta=0.03)
        self.assertAlmostEqual(freq[1.0], 0.25, delta=0.03)
        self.assertAlmostEqual(freq[-1.0], 0.25, delta=0.03)

    def test_identical_scenarios_give_degenerate_interval(self):
        r = []
        for s in ("A", "B", "C"):
            r += rows(s, "risk", 1, 1, 4) + rows(s, "risk", 6, 3, 4)
            r += rows(s, "benign", 1, 0, 4) + rows(s, "benign", 6, 1, 4)
        out = rd.rd_bootstrap(pd.DataFrame(r), B=200, seed=5)
        self.assertAlmostEqual(out["rd_risk"]["estimate"], 0.5)
        self.assertAlmostEqual(out["rd_benign"]["estimate"], 0.25)
        self.assertAlmostEqual(out["did"]["estimate"], 0.25)
        for key, val in (("rd_risk", 0.5), ("rd_benign", 0.25), ("did", 0.25)):
            lo, hi = out[key]["ci95_cluster_bootstrap"]
            self.assertAlmostEqual(lo, val)
            self.assertAlmostEqual(hi, val)
        self.assertEqual(out["bootstrap_replicates_with_0_benign_depth1_events"], 200)


class TestOddsRatios(unittest.TestCase):
    def test_firth_zero_cell_finite_and_equals_haldane(self):
        # S1-like benign table: depth 6 4/97, depth 1 0/80
        a, b, c, d = 4, 93, 0, 80
        f = rd.firth_or_2x2(a, b, c, d)
        self.assertTrue(f["converged"])
        self.assertTrue(math.isfinite(f["log_or"]))
        # saturated 2 x 2: the Firth estimate is the +0.5-corrected log OR
        expect = math.log((a + .5) * (d + .5) / ((b + .5) * (c + .5)))
        self.assertAlmostEqual(f["log_or"], expect, places=7)
        lo, hi = f["ci95_profile_penalized_likelihood"]
        self.assertTrue(lo is not None and hi is not None and 0 < lo < f["or"] < hi < math.inf)

    def test_firth_profile_survives_underflow(self):
        # S2-like benign table 4/104 vs 0/103: the first run hit a singular information
        # matrix in the profile search; reference bounds from a brute-force profile
        f = rd.firth_or_2x2(4, 100, 0, 103)
        lo, hi = f["ci95_profile_penalized_likelihood"]
        self.assertAlmostEqual(lo, 0.97018152, delta=1e-6)
        self.assertAlmostEqual(hi / 1234.20602, 1.0, delta=1e-6)

    def test_firth_nonzero_table(self):
        a, b, c, d = 20, 100, 1, 119
        f = rd.firth_or_2x2(a, b, c, d)
        expect = math.log((a + .5) * (d + .5) / ((b + .5) * (c + .5)))
        self.assertAlmostEqual(f["log_or"], expect, places=7)

    def test_firth_profile_bound_is_a_likelihood_ratio_root(self):
        a, b, c, d = 4, 93, 0, 80
        f = rd.firth_or_2x2(a, b, c, d)
        X = np.array([[1.0, 1.0], [1.0, 0.0]])
        y = np.array([a, c], float)
        n = np.array([a + b, c + d], float)
        full = rd.firth_fit(X, y, n)
        for bound in f["ci95_profile_penalized_likelihood"]:
            prof = rd.firth_fit(X, y, n, offset_fixed=(1, math.log(bound)))
            self.assertAlmostEqual(2 * (full["pll"] - prof["pll"]), rd.CHI2_1_95, places=5)

    @staticmethod
    def _exact_reference(a, b, c, d):
        """Independent exact conditional MLE / 95% CI from the noncentral hypergeometric."""
        from math import comb
        from scipy.optimize import brentq

        r1, r2, c1 = a + b, c + d, a + c
        xs = np.arange(max(0, c1 - r2), min(r1, c1) + 1)
        w = np.array([comb(r1, int(x)) * comb(r2, int(c1 - x)) for x in xs], float)

        def pmf(psi):
            lv = np.log(w) + xs * math.log(psi)
            v = np.exp(lv - lv.max())
            return v / v.sum()

        mle = brentq(lambda t: float((pmf(math.exp(t)) * xs).sum()) - a, -30, 30, xtol=1e-13)
        lo = 0.0 if a == xs.min() else math.exp(brentq(
            lambda t: float(pmf(math.exp(t))[xs >= a].sum()) - 0.025, -30, 30, xtol=1e-13))
        hi = math.inf if a == xs.max() else math.exp(brentq(
            lambda t: float(pmf(math.exp(t))[xs <= a].sum()) - 0.025, -30, 30, xtol=1e-13))
        return math.exp(mle), lo, hi

    def test_exact_conditional_known_tables(self):
        # Fisher's tea-tasting table (conditional MLE 6.408; R fisher.test prints
        # 0.2117-621.93, its upper limit differing at the root-finder tolerance) and the
        # S0 benign table 20/120 vs 1/120; the reference is computed independently here.
        for tab in ((3, 1, 1, 3), (20, 100, 1, 119)):
            ex = rd.exact_conditional_or(*tab)
            mle, lo, hi = self._exact_reference(*tab)
            self.assertAlmostEqual(ex["or"] / mle, 1.0, delta=1e-5)
            self.assertAlmostEqual(ex["ci95"][0] / lo, 1.0, delta=1e-5)
            self.assertAlmostEqual(ex["ci95"][1] / hi, 1.0, delta=1e-5)
        self.assertAlmostEqual(rd.exact_conditional_or(3, 1, 1, 3)["or"], 6.4083, delta=1e-3)
        # zero depth-1 events: MLE and upper limit are infinite
        z = rd.exact_conditional_or(4, 93, 0, 80)
        self.assertTrue(math.isinf(z["or"]) and math.isinf(z["ci95"][1]))
        self.assertGreater(z["ci95"][0], 0.0)

    def test_woolf_known_values(self):
        w = rd.woolf_or(20, 100, 1, 119)
        self.assertAlmostEqual(w["uncorrected"]["or"], 23.8, places=9)
        lo, hi = w["uncorrected"]["ci95"]
        self.assertTrue(3.1 < lo < 3.2 and 175 < hi < 185)
        z = rd.woolf_or(4, 93, 0, 80)
        self.assertIsNone(z["uncorrected"]["or"])
        self.assertAlmostEqual(z["haldane"]["or"], (4.5 * 80.5) / (93.5 * 0.5))


class TestReproductionCheck(unittest.TestCase):
    def test_compare_counts_detects_a_one_event_change(self):
        cell = {"events": 1, "rows": 120}
        block = {arm: {"depth1": dict(cell), "depth3": dict(cell), "depth6": dict(cell),
                       "conversations_selected": 120} for arm in ("risk", "benign")}
        self.assertEqual(rd.compare_counts(block, block), [])
        other = {arm: {k: (dict(v) if isinstance(v, dict) else v) for k, v in blk.items()}
                 for arm, blk in block.items()}
        other["benign"]["depth1"]["events"] = 0
        diffs = rd.compare_counts(other, block)
        self.assertEqual(len(diffs), 1)
        self.assertIn("benign.depth1.events", diffs[0])


if __name__ == "__main__":
    unittest.main()
