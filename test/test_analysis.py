"""Known-answer tests for the phase-A analysis scripts (src/kyra/analysis).

Every statistical claim is checked against a fixture whose TRUE value is
known by construction, including a null case for each effect, because a
check that cannot fail is worthless.  The Gwet AC2 implementation is
additionally checked against an independent re-implementation of the
published formula written out here in plain loops.

Run with:
  cd /home/wjeong/adol && PYTHONPATH=src \
    ~/envs/jeongwoncheol_adol/bin/python -m unittest discover -s test \
    -p "test_analysis.py" -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
FIX = REPO / "test" / "fixtures" / "analysis"
MAKE = FIX / "make_fixtures.py"
PROTO_SHA = REPO / "PREREGISTERED_kyra_v2.yaml.sha256"

sys.path.insert(0, str(SRC))

# Fixture bootstrap size (the card fixes fixtures at B = 200; the field
# default stays 2000).
B = 200

_CLI_CACHE = {}


def run_cli(module, args, expect_ok=True):
    """Run one analysis CLI in a subprocess; return (returncode, stdout+stderr, json|None)."""
    out_dir = Path(tempfile.mkdtemp(prefix="kyra_analysis_"))
    out_path = out_dir / "out.json"
    env = dict(os.environ, PYTHONPATH=str(SRC))
    proc = subprocess.run(
        [sys.executable, "-m", "kyra.analysis." + module] + args
        + ["--out", str(out_path)],
        cwd=str(REPO), env=env, capture_output=True, text=True,
    )
    payload = None
    if out_path.is_file():
        payload = json.loads(out_path.read_text(encoding="utf-8"))
    if expect_ok and proc.returncode != 0:
        raise AssertionError("%s failed (rc=%d):\n%s\n%s"
                             % (module, proc.returncode, proc.stdout, proc.stderr))
    return proc.returncode, proc.stdout + proc.stderr, payload


def cached(module, args):
    """Run each CLI once per test session: the N1 bootstrap is not cheap."""
    key = (module, tuple(args))
    if key not in _CLI_CACHE:
        _CLI_CACHE[key] = run_cli(module, args)[2]
    return _CLI_CACHE[key]


def manifest():
    return json.loads((FIX / "fixtures_manifest.json").read_text(encoding="utf-8"))


# -- an independent implementation of Gwet's AC2 -----------------------------


def explicit_ac2(ratings_per_subject, categories=(0, 1, 2)):
    """Gwet's AC2 with quadratic weights, written out from the formula.

    Deliberately naive loops, no numpy, no shared code with
    kyra.analysis.n3_reliability: if the two agree to 1e-9 the
    implementation is not merely self-consistent.

        w_kl = 1 - ((v_k - v_l) / (v_max - v_min))^2
        p_a  = mean_i  sum_k r_ik (r*_ik - 1) / (n_i (n_i - 1)),
               r*_ik = sum_l w_kl r_il
        pi_k = mean_i  r_ik / n_i
        p_e  = (sum_kl w_kl) * sum_k pi_k (1 - pi_k) / (q (q - 1))
        AC2  = (p_a - p_e) / (1 - p_e)
    """
    cats = list(categories)
    q = len(cats)
    span = float(cats[-1] - cats[0])
    w = [[1.0 - ((cats[k] - cats[l]) / span) ** 2 for l in range(q)] for k in range(q)]

    subjects = [rs for rs in ratings_per_subject if len(rs) >= 2]
    n = len(subjects)
    pa = 0.0
    for rs in subjects:
        ni = len(rs)
        counts = [sum(1 for r in rs if r == cats[k]) for k in range(q)]
        total = 0.0
        for k in range(q):
            starred = sum(w[k][l] * counts[l] for l in range(q))
            total += counts[k] * (starred - 1.0)
        pa += total / (ni * (ni - 1.0))
    pa /= n

    pi = []
    for k in range(q):
        pi.append(sum(sum(1 for r in rs if r == cats[k]) / len(rs)
                      for rs in subjects) / n)
    t_w = sum(sum(row) for row in w)
    pe = t_w * sum(p * (1.0 - p) for p in pi) / (q * (q - 1.0))
    return (pa - pe) / (1.0 - pe)


# -- loader derivations ------------------------------------------------------


class TestLoaderDerivations(unittest.TestCase):
    def test_failure_event_recovery_and_censoring(self):
        from kyra.analysis import loader

        df = loader.load_tidy_csv(FIX / "transitions_small.csv")
        by_item = {r["item_id"]: r for r in df.to_dict("records")}

        never = by_item["T-01-LOC"]
        self.assertTrue(never["failure_event_turn"] != never["failure_event_turn"])  # NaN
        self.assertEqual(never["critical_any"], 0)

        recov = by_item["T-02-LOC"]           # crit 0,1,0,0
        self.assertEqual(recov["failure_event_turn"], 2.0)
        self.assertEqual(recov["immediate_recovery"], 1.0)
        self.assertEqual(recov["eventual_recovery"], 1.0)
        self.assertEqual(recov["censored_final_turn"], 0.0)

        stuck = by_item["T-03-LOC"]           # crit 0,1,1,1
        self.assertEqual(stuck["failure_event_turn"], 2.0)
        self.assertEqual(stuck["immediate_recovery"], 0.0)
        self.assertEqual(stuck["eventual_recovery"], 0.0)

        last = by_item["T-04-LOC"]            # fails on the final turn
        self.assertEqual(last["failure_event_turn"], 4.0)
        self.assertEqual(last["censored_final_turn"], 1.0)
        self.assertTrue(last["immediate_recovery"] != last["immediate_recovery"])
        self.assertTrue(last["eventual_recovery"] != last["eventual_recovery"])

    def test_base_item_condition_and_crri(self):
        from kyra.analysis import loader
        from kyra.crri import crri

        self.assertEqual(loader.split_item_id("R1-M03-LOC"), ("R1-M03", "LOC"))
        self.assertEqual(loader.split_item_id("R1-S01-CTRL"), ("R1-S01", "CTRL"))
        df = loader.load_tidy_csv(FIX / "transitions_small.csv")
        row = df[df["item_id"] == "T-01-LOC"].iloc[0]
        self.assertEqual(row["base_item"], "T-01")
        self.assertEqual(row["condition"], "LOC")
        self.assertEqual(row["source_group"], "T")
        self.assertAlmostEqual(row["crri"], crri([1, 1, 1, 1]), places=12)

    def test_prefix_view_panel_records(self):
        """One panel record per (item_id, condition, depth) -> series columns."""
        from kyra.analysis import loader

        root = FIX / "prefix_run"
        df = loader.build_tidy(root / "items.jsonl", [root / "run"],
                               [root / "run" / "panel.jsonl"])
        hand = manifest()["fixtures"]["prefix_run/run/panel.jsonl"]["hand_answer"]
        by_item = {r["item_id"]: r for r in df.to_dict("records")}
        self.assertEqual(set(by_item), set(hand))
        for item_id, want in hand.items():
            got = by_item[item_id]
            with self.subTest(item=item_id):
                self.assertTrue(got["per_turn_available"])
                self.assertEqual(got["view_depths"],
                                 ";".join(str(d) for d in want["view_depths"]))
                self.assertEqual(got["n_turns"], want["n_turns"])
                self.assertEqual(got["critical_any"], want["critical_any"])
                self.assertAlmostEqual(got["crri"], want["crri"], places=12)
                for key in ("failure_event_turn", "immediate_recovery",
                            "eventual_recovery", "censored_final_turn",
                            "crit_by_depth_1", "crit_by_depth_3",
                            "crit_by_depth_6"):
                    if want[key] is None:
                        self.assertTrue(got[key] != got[key],
                                        "%s %s should be NaN (censored)" % (item_id, key))
                    else:
                        self.assertEqual(got[key], want[key], "%s %s" % (item_id, key))

    def test_prefix_view_over_refusal_and_helpfulness(self):
        from kyra.analysis import loader

        root = FIX / "prefix_run"
        df = loader.build_tidy(root / "items.jsonl", [root / "run"],
                               [root / "run" / "panel.jsonl"])
        ben = df[df["item_id"] == "R1-M01-BEN"].iloc[0]
        self.assertEqual(ben["over_refusal"], 0.0)
        self.assertEqual(ben["helpfulness"], 2.0)

    def test_panel_v0_record_yields_no_series(self):
        """A record without `depth` is panel v0: no invented per-turn series."""
        from kyra.analysis import loader
        import json as _json

        root = FIX / "prefix_run"
        tmp = Path(tempfile.mkdtemp()) / "panel_v0.jsonl"
        with (root / "run" / "panel.jsonl").open(encoding="utf-8") as fh:
            recs = [_json.loads(line) for line in fh if line.strip()]
        keep = []
        for rec in recs:
            if rec["depth"] != 6:
                continue
            rec.pop("depth")
            rec["n_turns"] = 6
            keep.append(rec)
        tmp.write_text("".join(_json.dumps(r) + "\n" for r in keep), encoding="utf-8")
        df = loader.build_tidy(root / "items.jsonl", [root / "run"], [tmp])
        self.assertFalse(df["per_turn_available"].any())
        self.assertTrue(df["failure_event_turn"].isna().all())

    def test_inconsistent_flag_is_an_error(self):
        from kyra.analysis import loader
        import pandas as pd

        bad = pd.DataFrame([{"item_id": "X-01-LOC", "model_id": "m",
                             "n_turns": 2, "critical_failure": 0,
                             "crit_turns": "0;1"}])
        with self.assertRaises(ValueError):
            loader.finalize(bad)


# -- N1 ----------------------------------------------------------------------


class TestN1(unittest.TestCase):
    def test_recovers_designed_odds_ratio(self):
        res = cached("n1_escalation",
                     ["--fixture", str(FIX / "n1_effect.csv"), "--bootstrap", str(B)])
        info = manifest()["fixtures"]["n1_effect.csv"]
        self.assertAlmostEqual(info["true_or_design_logit_scale"], 2.0684, places=3)
        self.assertGreaterEqual(res["or"], 1.6, "OR below the acceptance band")
        self.assertLessEqual(res["or"], 2.8, "OR above the acceptance band")
        self.assertGreater(res["ci95"][0], 1.0,
                           "95%% CI must exclude 1 on the effect fixture: %s"
                           % (res["ci95"],))
        self.assertEqual(res["B"], B)

    def test_null_fixture_ci_includes_one(self):
        res = cached("n1_escalation",
                     ["--fixture", str(FIX / "n1_null.csv"), "--bootstrap", str(B)])
        lo, hi = res["ci95"]
        self.assertLessEqual(lo, 1.0)
        self.assertGreaterEqual(hi, 1.0)

    def test_benign_twin_and_interaction_reported(self):
        eff = cached("n1_escalation",
                     ["--fixture", str(FIX / "n1_effect.csv"), "--bootstrap", str(B)])
        # benign twins were generated with a true OR of 1
        self.assertIsNotNone(eff["benign_or"])
        self.assertLessEqual(eff["benign_ci95"][0], 1.0)
        self.assertGreaterEqual(eff["benign_ci95"][1], 1.0)
        # the 48 x 5 effect fixture is NOT powered for the interaction (the
        # benign arm sits at a .05 base rate); the honest bootstrap p says so
        self.assertIsNotNone(eff["interaction_p"])
        self.assertGreater(eff["interaction"]["or"], 1.0)
        null = cached("n1_escalation",
                      ["--fixture", str(FIX / "n1_null.csv"), "--bootstrap", str(B)])
        self.assertGreaterEqual(null["interaction_p"], 0.05)
        lo, hi = null["interaction"]["ci95"]
        self.assertLessEqual(lo, 1.0)
        self.assertGreaterEqual(hi, 1.0)

    def test_interaction_p_is_the_bootstrap_p_holm_adjusted(self):
        res = cached("n1_escalation",
                     ["--fixture", str(FIX / "n1_interaction.csv"),
                      "--bootstrap", str(B)])
        inter = res["interaction"]
        # headline p is the Holm-adjusted BOOTSTRAP p, not the VB Wald p
        self.assertEqual(res["interaction_p"], inter["p_holm"])
        self.assertEqual(res["interaction_p_vb"], inter["p_wald_vb"])
        self.assertGreaterEqual(inter["p_holm"], inter["p_bootstrap"])
        # the bootstrap p cannot be below its own resolution 2/(B+1)
        self.assertGreaterEqual(inter["p_bootstrap"],
                                2.0 / (inter["bootstrap_used"] + 1))
        self.assertEqual(inter["bootstrap_b"], B)
        # this fixture IS powered for the interaction: it must be detected
        self.assertLess(res["interaction_p"], 0.05)
        self.assertGreater(inter["ci95"][0], 1.0)
        truth = manifest()["fixtures"]["n1_interaction.csv"]["true_interaction_log_or"]
        self.assertAlmostEqual(truth, 0.7268, places=3)

    def test_vb_p_is_anticonservative_and_is_not_the_headline(self):
        """The VB Wald p is kept only as a secondary reading."""
        res = cached("n1_escalation",
                     ["--fixture", str(FIX / "n1_interaction.csv"),
                      "--bootstrap", str(B)])
        self.assertLess(res["interaction_p_vb"], res["interaction_p"])
        self.assertIn("bootstrap", res["p_method"])

    def test_bootstrap_p_helper(self):
        from kyra.analysis.n1_escalation import bootstrap_p

        self.assertAlmostEqual(bootstrap_p([1.0] * 99), 2.0 / 100, places=12)
        self.assertAlmostEqual(bootstrap_p([-1.0] * 99), 2.0 / 100, places=12)
        self.assertEqual(bootstrap_p([-1.0] * 50 + [1.0] * 49), 1.0)
        self.assertTrue(bootstrap_p([]) != bootstrap_p([]))  # NaN on no replicates

    def test_gee_sensitivity_present(self):
        res = cached("n1_escalation",
                     ["--fixture", str(FIX / "n1_effect.csv"), "--bootstrap", str(B)])
        self.assertIn("or", res["sensitivity_gee"])
        self.assertGreater(res["sensitivity_gee"]["or"], 1.0)

    def test_holm_adjustment(self):
        from kyra.analysis.n1_escalation import holm

        adj = holm({"a": 0.01, "b": 0.02, "c": 0.5})
        self.assertAlmostEqual(adj["a"], 0.03, places=12)
        self.assertAlmostEqual(adj["b"], 0.04, places=12)
        self.assertAlmostEqual(adj["c"], 0.5, places=12)


# -- N2 ----------------------------------------------------------------------


class TestN2(unittest.TestCase):
    def test_recovers_paired_difference(self):
        res = cached("n2_localization",
                     ["--fixture", str(FIX / "n2_effect.csv"), "--bootstrap", str(B)])
        truth = manifest()["fixtures"]["n2_effect.csv"]["true_paired_difference"]
        self.assertAlmostEqual(truth, 0.06, places=12)
        self.assertLessEqual(abs(res["estimate"] - truth), 0.03,
                             "paired difference %.4f is more than 0.03 from the "
                             "true %.4f" % (res["estimate"], truth))
        self.assertGreater(res["ci95"][0], 0.0,
                           "95%% CI must exclude 0: %s" % (res["ci95"],))
        self.assertEqual(res["components"], "not_separable_in_phase_A")

    def test_null_fixture_passes_tost(self):
        res = cached("n2_localization",
                     ["--fixture", str(FIX / "n2_null.csv"), "--bootstrap", str(B)])
        self.assertAlmostEqual(res["estimate"], 0.0, delta=0.03)
        self.assertEqual(res["tost"]["bound"], 0.03)
        self.assertTrue(res["tost"]["equivalent"],
                        "TOST should establish equivalence on the null fixture: %s"
                        % (res["tost"],))

    def test_effect_fixture_does_not_pass_tost(self):
        res = cached("n2_localization",
                     ["--fixture", str(FIX / "n2_effect.csv"), "--bootstrap", str(B)])
        self.assertFalse(res["tost"]["equivalent"])

    def test_ci_method_is_named(self):
        res = cached("n2_localization",
                     ["--fixture", str(FIX / "n2_effect.csv"), "--bootstrap", str(B)])
        self.assertIn(res["ci_method"],
                      ("paired_mixed_model_lpm", "paired_cluster_bootstrap_pairs"))


# -- N3 ----------------------------------------------------------------------


class TestN3(unittest.TestCase):
    def test_hand_case_matches_the_explicit_formula(self):
        import csv as _csv
        from kyra.analysis import n3_reliability as n3

        with (FIX / "n3_hand.csv").open(encoding="utf-8") as fh:
            rows = list(_csv.DictReader(fh))
        res = cached("n3_reliability",
                     ["--fixture", str(FIX / "n3_hand.csv"), "--bootstrap", "50"])
        for dim in ("D1", "D2", "D3", "D4", "D5", "D6"):
            per_subject = {}
            for r in rows:
                per_subject.setdefault(r["conversation_id"], []).append(int(r[dim]))
            expected = explicit_ac2(list(per_subject.values()))
            self.assertAlmostEqual(res["per_dimension"][dim]["ac2"], expected,
                                   delta=1e-9,
                                   msg="%s: %r vs explicit %r"
                                       % (dim, res["per_dimension"][dim]["ac2"], expected))
            # and the library function agrees with the CLI output
            self.assertAlmostEqual(n3.ac2(per_subject)["ac2"], expected, delta=1e-9)

    def test_hand_case_flag_agreement(self):
        res = cached("n3_reliability",
                     ["--fixture", str(FIX / "n3_hand.csv"), "--bootstrap", "50"])
        truth = manifest()["fixtures"]["n3_hand.csv"]["true_flag_agreement"]
        self.assertAlmostEqual(res["flag_agreement"], truth, places=12)

    def test_identity_weights_reduce_to_ac1(self):
        from kyra.analysis import n3_reliability as n3

        subjects = {"a": [2, 2, 1], "b": [0, 1, 1], "c": [2, 2, 2], "d": [1, 0, 2]}
        weighted = n3.ac2(subjects)["ac2"]
        unweighted = n3.ac2(subjects, weights=n3.identity_weights())["ac2"]
        self.assertNotAlmostEqual(weighted, unweighted, places=6)
        self.assertGreater(weighted, unweighted)  # ordinal credit for near misses

    def test_simulated_panel_lands_in_its_band(self):
        res = cached("n3_reliability",
                     ["--fixture", str(FIX / "n3_sim.csv"), "--bootstrap", str(B)])
        lo, hi = manifest()["fixtures"]["n3_sim.csv"]["ac2_band"]
        for dim in ("D1", "D2", "D3", "D4", "D5", "D6"):
            value = res["per_dimension"][dim]["ac2"]
            self.assertGreaterEqual(value, lo, "%s AC2 %.4f below band" % (dim, value))
            self.assertLessEqual(value, hi, "%s AC2 %.4f above band" % (dim, value))
            ci = res["per_dimension"][dim]["ci95"]
            self.assertLessEqual(ci[0], value)
            self.assertGreaterEqual(ci[1], value)

    def test_leave_one_family_out_is_reported(self):
        res = cached("n3_reliability",
                     ["--fixture", str(FIX / "n3_sim.csv"), "--bootstrap", str(B)])
        self.assertEqual(sorted(res["families"]), ["google", "lg", "qwen"])
        self.assertEqual(len(res["leave_one_family_out"]), 3)
        self.assertIsNotNone(res["max_lofo_change"])
        self.assertGreaterEqual(res["max_lofo_change"], 0.0)
        for entry in res["leave_one_family_out"]:
            for dim in ("D1", "D6"):
                self.assertIn("ac2", entry["per_dimension"][dim])


# -- transitions / pareto ----------------------------------------------------


class TestTransitions(unittest.TestCase):
    def setUp(self):
        self.res = cached("transitions",
                          ["--fixture", str(FIX / "transitions_small.csv")])
        self.hand = manifest()["fixtures"]["transitions_small.csv"]["hand_answer"]["model_A/R1"]
        self.group = next(g for g in self.res["by_model_and_risk_group"]
                          if g["model_id"] == "model_A" and g["risk_group"] == "R1")

    def test_per_turn_counts(self):
        self.assertEqual(self.group["n_conversations"], self.hand["n_conversations"])
        for entry in self.group["per_turn"]:
            t = str(entry["turn"])
            self.assertEqual(entry["fail"], self.hand["per_turn_fail"][t])
            self.assertEqual(entry["safe"], self.hand["per_turn_safe"][t])

    def test_first_failure_distribution(self):
        self.assertEqual(self.group["first_failure_turn"],
                         self.hand["first_failure_turn"])

    def test_recovery_counts_with_denominators(self):
        self.assertEqual(self.group["recovery"]["immediate"]["n"],
                         self.hand["immediate_recovery"]["n"])
        self.assertEqual(self.group["recovery"]["immediate"]["denominator"],
                         self.hand["immediate_recovery"]["denominator"])
        self.assertEqual(self.group["recovery"]["eventual"]["n"],
                         self.hand["eventual_recovery"]["n"])
        self.assertEqual(self.group["recovery"]["eventual"]["denominator"],
                         self.hand["eventual_recovery"]["denominator"])
        self.assertEqual(self.group["censored_final_turn"],
                         self.hand["censored_final_turn"])

    def test_hazard(self):
        for entry in self.group["hazard"]:
            t = str(entry["turn"])
            self.assertEqual(entry["at_risk"], self.hand["hazard_at_risk"][t])
            self.assertEqual(entry["events"], self.hand["hazard_events"][t])
            expected = self.hand["hazard_events"][t] / self.hand["hazard_at_risk"][t]
            self.assertAlmostEqual(entry["hazard"], expected, places=12)


class TestPareto(unittest.TestCase):
    def setUp(self):
        self.res = cached("pareto",
                          ["--fixture", str(FIX / "pareto_small.csv"),
                           "--bootstrap", str(B)])
        self.hand = manifest()["fixtures"]["pareto_small.csv"]["hand_answer"]

    def test_rates_match_hand_counts(self):
        for entry in self.res["by_model"]:
            want = self.hand[entry["model_id"]]
            for key in ("critical_failure_rate_risk", "over_refusal_rate_control",
                        "helpfulness_mean_control"):
                self.assertAlmostEqual(entry[key], want[key], places=12,
                                       msg="%s %s" % (entry["model_id"], key))
            for key in ("n_risk", "n_control", "n_risk_events", "n_over_refusals"):
                self.assertEqual(entry[key], want[key])

    def test_default_method_is_the_panel_flag(self):
        self.assertEqual(self.res["over_refusal_method"], "panel_over_refusal_flag")
        self.assertIn("over_refusal flag", self.res["over_refusal_definition"])

    def test_proxy_fallback_is_opt_in_and_named(self):
        res = cached("pareto", ["--fixture", str(FIX / "pareto_small.csv"),
                                "--bootstrap", str(B), "--proxy-d3d4"])
        self.assertEqual(res["over_refusal_method"], "proxy_d3d4")
        self.assertIn("D3 == 0 and D4 == 0", res["over_refusal_definition"])
        self.assertIn("PROXY", res["over_refusal_definition"])
        # the fixture sets the flag and the proxy to agree, so the rates match
        for entry, direct in zip(res["by_model"], self.res["by_model"]):
            self.assertEqual(entry["over_refusal_rate_control"],
                             direct["over_refusal_rate_control"])

    def test_missing_flag_without_the_opt_in_is_an_error(self):
        """No silent fallback: an old panel without the flag must fail loudly."""
        import csv as _csv

        tmp = Path(tempfile.mkdtemp()) / "no_flag.csv"
        with (FIX / "pareto_small.csv").open(encoding="utf-8") as fh:
            rows = list(_csv.reader(fh))
        header = rows[0]
        col = header.index("over_refusal")
        for r in rows[1:]:
            r[col] = ""
        with tmp.open("w", encoding="utf-8", newline="\n") as fh:
            _csv.writer(fh, lineterminator="\n").writerows(rows)
        rc, text, payload = run_cli("pareto", ["--fixture", str(tmp)],
                                    expect_ok=False)
        self.assertNotEqual(rc, 0)
        self.assertIn("over_refusal", text)
        self.assertIn("--proxy-d3d4", text)
        self.assertIsNone(payload)
        # ... and with the opt-in it works
        rc2, _, payload2 = run_cli("pareto", ["--fixture", str(tmp),
                                              "--bootstrap", "20", "--proxy-d3d4"])
        self.assertEqual(rc2, 0)
        self.assertEqual(payload2["over_refusal_method"], "proxy_d3d4")

    def test_cis_bracket_the_point_estimates(self):
        for entry in self.res["by_model"]:
            for point, ci in (("critical_failure_rate_risk", "critical_failure_ci95"),
                              ("over_refusal_rate_control", "over_refusal_ci95")):
                self.assertLessEqual(entry[ci][0], entry[point])
                self.assertGreaterEqual(entry[ci][1], entry[point])


# -- CLI contract ------------------------------------------------------------


EMPTY_CASES = [
    ("n1_escalation", ["--fixture", str(FIX / "empty_tidy.csv")]),
    ("n2_localization", ["--fixture", str(FIX / "empty_tidy.csv")]),
    ("transitions", ["--fixture", str(FIX / "empty_tidy.csv")]),
    ("pareto", ["--fixture", str(FIX / "empty_tidy.csv")]),
    ("n3_reliability", ["--fixture", str(FIX / "empty_judges.csv")]),
]

FIXTURE_CASES = [
    ("n1_escalation", ["--fixture", str(FIX / "n1_effect.csv"), "--bootstrap", str(B)]),
    ("n2_localization", ["--fixture", str(FIX / "n2_effect.csv"), "--bootstrap", str(B)]),
    ("n3_reliability", ["--fixture", str(FIX / "n3_sim.csv"), "--bootstrap", str(B)]),
    ("transitions", ["--fixture", str(FIX / "transitions_small.csv")]),
    ("pareto", ["--fixture", str(FIX / "pareto_small.csv"), "--bootstrap", str(B)]),
]


class TestCliContract(unittest.TestCase):
    def test_empty_input_exits_nonzero_with_a_message(self):
        for module, args in EMPTY_CASES:
            with self.subTest(module=module):
                rc, text, payload = run_cli(module, args, expect_ok=False)
                self.assertNotEqual(rc, 0,
                                    "%s exited 0 on an empty input" % module)
                self.assertIn("ERROR", text)
                self.assertIsNone(payload, "%s wrote an output on empty input" % module)

    def test_outputs_are_valid_json_naming_the_frozen_protocol(self):
        sha = PROTO_SHA.read_text(encoding="utf-8").split()[0]
        self.assertEqual(len(sha), 64)
        for module, args in FIXTURE_CASES:
            with self.subTest(module=module):
                payload = cached(module, args)
                self.assertIn("version", payload)
                self.assertIn(sha, payload["version"])
                self.assertIn("PREREGISTERED_kyra_v2.yaml", payload["version"])
                self.assertEqual(payload["analysis"], module)
                json.dumps(payload)  # round-trips, so no bare NaN token

    def test_g6_facing_field_names(self):
        """The names the G6 coder aligned to must all be present."""
        n1 = cached("n1_escalation",
                    ["--fixture", str(FIX / "n1_effect.csv"), "--bootstrap", str(B)])
        for key in ("or", "ci95", "benign_or", "benign_ci95", "interaction_p",
                    "interaction_p_vb", "n", "B", "seed"):
            self.assertIn(key, n1)
        n2 = cached("n2_localization",
                    ["--fixture", str(FIX / "n2_effect.csv"), "--bootstrap", str(B)])
        for key in ("estimate", "ci95", "tost", "ci_method", "components"):
            self.assertIn(key, n2)
        self.assertIn("equivalent", n2["tost"])
        n3 = cached("n3_reliability",
                    ["--fixture", str(FIX / "n3_sim.csv"), "--bootstrap", str(B)])
        for key in ("per_dimension", "flag_agreement", "max_lofo_change"):
            self.assertIn(key, n3)
        for dim in ("D1", "D2", "D3", "D4", "D5", "D6"):
            self.assertIn("ac2", n3["per_dimension"][dim])
            self.assertIn("ci95", n3["per_dimension"][dim])
        pa = cached("pareto", ["--fixture", str(FIX / "pareto_small.csv"),
                               "--bootstrap", str(B)])
        for key in ("over_refusal_method", "over_refusal_definition", "by_model"):
            self.assertIn(key, pa)

    def test_fixture_and_run_inputs_are_mutually_exclusive(self):
        rc, text, _ = run_cli(
            "transitions",
            ["--fixture", str(FIX / "transitions_small.csv"), "--items", "x.jsonl"],
            expect_ok=False)
        self.assertNotEqual(rc, 0)
        self.assertIn("ERROR", text)


class TestFixturesAreDeterministic(unittest.TestCase):
    def test_regeneration_reproduces_every_csv(self):
        import hashlib

        out = Path(tempfile.mkdtemp(prefix="kyra_fixtures_"))
        proc = subprocess.run([sys.executable, str(MAKE), "--out-dir", str(out)],
                              cwd=str(REPO), capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        recorded = manifest()["fixtures"]
        for name, info in recorded.items():
            with self.subTest(fixture=name):
                fresh = hashlib.sha256((out / name).read_bytes()).hexdigest()
                committed = hashlib.sha256((FIX / name).read_bytes()).hexdigest()
                self.assertEqual(fresh, committed,
                                 "%s is not reproducible from make_fixtures.py" % name)
                self.assertEqual(committed, info["sha256"],
                                 "%s does not match the manifest hash" % name)


if __name__ == "__main__":
    unittest.main()
