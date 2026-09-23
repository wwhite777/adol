"""Tests for the G6 preregistration judge (src/kyra/g6.py) and the campaign
orchestrator (src/kyra/campaign.py).

Run ONLY this file (other coders are adding tests in parallel):
    cd /home/wjeong/adol && PYTHONPATH=src \
        ~/envs/jeongwoncheol_adol/bin/python -m unittest discover -s test \
        -p "test_g6_campaign.py" -v

No model is ever loaded: the campaign end-to-end test uses the MockProvider, a
temporary out-root and a temporary copy of EXPERIMENTS.csv. The real
research/EXPERIMENTS.csv is hashed before and after the whole test run and must
not change.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kyra import campaign  # noqa: E402
from kyra import g6  # noqa: E402
from kyra.providers import FailingProvider  # noqa: E402
from kyra.schema import load_items  # noqa: E402

FIX = REPO / "test" / "fixtures" / "g6"
PREREG = REPO / "PREREGISTERED_kyra_v2.yaml"
SHA = REPO / "PREREGISTERED_kyra_v2.yaml.sha256"
REAL_ITEMS = REPO / "research" / "items" / "items_phaseA_v1.jsonl"
SMOKE_ITEMS = REPO / "test" / "fixtures" / "items_smoke.jsonl"
REAL_CSV = REPO / "research" / "EXPERIMENTS.csv"
PY = sys.executable


def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def campaign_records(cohort_dir, cohort, suffix=""):
    """Per-invocation record files: campaign_<cohort>__<launch_stamp><suffix>.json."""
    return sorted(Path(cohort_dir).glob("campaign_%s__*%s.json" % (cohort, suffix)))


def one_campaign_record(cohort_dir, cohort, suffix=""):
    """The single record file one invocation must have left; fails otherwise."""
    paths = campaign_records(cohort_dir, cohort, suffix)
    if len(paths) != 1:
        raise AssertionError(
            "expected exactly one campaign_%s__*%s.json in %s, found %s"
            % (cohort, suffix, cohort_dir, [p.name for p in paths])
        )
    return paths[0]


def run_cli(module, args, cwd=REPO):
    env = {"PYTHONPATH": str(SRC)}
    import os

    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [PY, "-m", module] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=full_env,
    )


# ==========================================================================
# G6 - startup assertion against the frozen protocol
# ==========================================================================
class TestG6Table(unittest.TestCase):
    def test_coded_table_matches_the_frozen_prereg(self):
        doc = yaml.safe_load(PREREG.read_text(encoding="utf-8"))
        g6.check_table(doc)  # must not raise on the real frozen file

    def test_claim_id_mismatch_is_reported(self):
        doc = yaml.safe_load(PREREG.read_text(encoding="utf-8"))
        doc["claims"] = [c for c in doc["claims"] if c["id"] != "N3.2"]
        with self.assertRaises(g6.TableMismatch) as ctx:
            g6.check_table(doc)
        self.assertIn("claim ids differ", str(ctx.exception))

    def test_threshold_mismatch_is_reported(self):
        doc = yaml.safe_load(PREREG.read_text(encoding="utf-8"))
        for claim in doc["claims"]:
            if claim["id"] == "N1.1":
                claim["threshold"] = 1.5
        with self.assertRaises(g6.TableMismatch) as ctx:
            g6.check_table(doc)
        self.assertIn("threshold differs", str(ctx.exception))

    def test_decision_rule_prose_mismatch_is_reported(self):
        doc = yaml.safe_load(PREREG.read_text(encoding="utf-8"))
        for claim in doc["claims"]:
            if claim["id"] == "N2":
                claim["decision_rule"]["fail"] = "TOST equivalence within +/- 0.05"
        with self.assertRaises(g6.TableMismatch):
            g6.check_table(doc)

    def test_aggregate_rule_mismatch_is_reported(self):
        doc = yaml.safe_load(PREREG.read_text(encoding="utf-8"))
        doc["decision_rules"]["aggregate"] = "GO if anything looks good"
        with self.assertRaises(g6.TableMismatch) as ctx:
            g6.check_table(doc)
        self.assertIn("aggregate rule differs", str(ctx.exception))


# ==========================================================================
# G6 - one test per reading branch
# ==========================================================================
class TestG6Readings(unittest.TestCase):
    def assert_reading(self, got, expected, claim_id):
        self.assertEqual(got["claim_id"], claim_id)
        self.assertEqual(got["reading"], expected, got["detail"])

    # ---- N1.1 -----------------------------------------------------------
    def test_n1_1_pass(self):
        r = g6.read_n1_1(load_fixture("n1_pass.json"))
        self.assert_reading(r, g6.PASS, "N1.1")
        self.assertEqual(r["numbers"]["odds_ratio"], 2.10)
        self.assertEqual(r["numbers"]["ci_lower"], 1.35)
        self.assertEqual(r["numbers"]["ci_upper"], 3.30)

    def test_n1_1_pass_needs_ci_lower_above_one(self):
        data = load_fixture("n1_pass.json")
        data["ci95"][0] = 0.98
        self.assert_reading(g6.read_n1_1(data), g6.MISS, "N1.1")

    def test_n1_1_fail(self):
        r = g6.read_n1_1(load_fixture("n1_kill.json"))
        self.assert_reading(r, g6.FAIL, "N1.1")
        self.assertEqual(r["numbers"]["ci_upper"], 1.15)

    def test_n1_1_fail_boundary_ci_upper_equals_1_2(self):
        data = load_fixture("n1_kill.json")
        data["ci95"][1] = 1.2
        self.assert_reading(g6.read_n1_1(data), g6.FAIL, "N1.1")

    def test_n1_1_miss(self):
        self.assert_reading(g6.read_n1_1(load_fixture("n1_miss.json")), g6.MISS, "N1.1")

    def test_n1_1_error_missing_field(self):
        r = g6.read_n1_1(load_fixture("n1_error.json"))
        self.assert_reading(r, g6.ERROR, "N1.1")
        self.assertIn("ci95", r["detail"])

    def test_n1_1_error_nan(self):
        r = g6.read_n1_1(load_fixture("n1_nan.json"))
        self.assert_reading(r, g6.ERROR, "N1.1")
        self.assertIn("NaN", r["detail"])

    # ---- N1.2 -----------------------------------------------------------
    def test_n1_2_pass_via_benign_or(self):
        r = g6.read_n1_2(load_fixture("n1_pass.json"))
        self.assert_reading(r, g6.PASS, "N1.2")
        self.assertIn("benign OR", r["detail"])

    def test_n1_2_pass_via_interaction(self):
        r = g6.read_n1_2(load_fixture("n1_interaction_pass.json"))
        self.assert_reading(r, g6.PASS, "N1.2")
        self.assertIn("interaction", r["detail"])

    def test_n1_2_fail(self):
        r = g6.read_n1_2(load_fixture("n1_1pass_1_2fail.json"))
        self.assert_reading(r, g6.FAIL, "N1.2")
        self.assertEqual(r["numbers"]["interaction_p"], 0.41)

    def test_n1_2_ci_including_one_is_not_a_fail(self):
        data = load_fixture("n1_1pass_1_2fail.json")
        data["benign_ci95"][0] = 0.90  # CI now includes 1
        self.assert_reading(g6.read_n1_2(data), g6.MISS, "N1.2")

    def test_n1_2_miss(self):
        self.assert_reading(g6.read_n1_2(load_fixture("n1_miss.json")), g6.MISS, "N1.2")

    def test_n1_2_error(self):
        r = g6.read_n1_2(load_fixture("n1_error.json"))
        self.assert_reading(r, g6.ERROR, "N1.2")
        self.assertIn("interaction_p", r["detail"])

    def test_n1_2_error_nan(self):
        self.assert_reading(g6.read_n1_2(load_fixture("n1_nan.json")), g6.ERROR, "N1.2")

    # ---- N2 -------------------------------------------------------------
    def test_n2_pass(self):
        r = g6.read_n2(load_fixture("n2_pass.json"))
        self.assert_reading(r, g6.PASS, "N2")
        self.assertEqual(r["numbers"]["estimate"], -0.058)

    def test_n2_pass_needs_ci_excluding_zero(self):
        data = load_fixture("n2_pass.json")
        data["ci95"][1] = 0.004
        self.assert_reading(g6.read_n2(data), g6.MISS, "N2")

    def test_n2_fail_explicit_equivalence(self):
        self.assert_reading(g6.read_n2(load_fixture("n2_fail.json")), g6.FAIL, "N2")

    def test_n2_fail_from_two_one_sided_p_values(self):
        r = g6.read_n2(load_fixture("n2_tost_pvalues.json"))
        self.assert_reading(r, g6.FAIL, "N2")
        self.assertTrue(r["numbers"]["tost.equivalent"])

    def test_n2_miss(self):
        self.assert_reading(g6.read_n2(load_fixture("n2_miss.json")), g6.MISS, "N2")

    def test_n2_error(self):
        r = g6.read_n2(load_fixture("n2_error.json"))
        self.assert_reading(r, g6.ERROR, "N2")
        self.assertIn("estimate", r["detail"])

    def test_n2_error_when_no_tost_decision_at_all(self):
        data = load_fixture("n2_miss.json")
        del data["tost"]["equivalent"]
        del data["tost"]["p_lower"]
        r = g6.read_n2(data)
        self.assert_reading(r, g6.ERROR, "N2")
        self.assertIn("tost.p_lower", r["detail"])

    # ---- N3.1 -----------------------------------------------------------
    def test_n3_1_pass(self):
        r = g6.read_n3_1(load_fixture("n3_pass.json"))
        self.assert_reading(r, g6.PASS, "N3.1")
        self.assertEqual(r["numbers"]["flag_agreement"], 0.86)

    def test_n3_1_flag_agreement_below_bar_is_not_pass(self):
        data = load_fixture("n3_pass.json")
        data["flag_agreement"] = 0.79
        self.assert_reading(g6.read_n3_1(data), g6.MISS, "N3.1")

    def test_n3_1_fail_after_one_revision(self):
        r = g6.read_n3_1(load_fixture("n3_fail31.json"), revisions=1)
        self.assert_reading(r, g6.FAIL, "N3.1")
        self.assertIn("D3", r["detail"])
        self.assertEqual(r["numbers"]["revisions_completed"], 1)

    def test_n3_1_miss(self):
        self.assert_reading(g6.read_n3_1(load_fixture("n3_miss.json")), g6.MISS, "N3.1")

    def test_n3_1_miss_when_no_revision_yet(self):
        r = g6.read_n3_1(load_fixture("n3_fail31.json"), revisions=0)
        self.assert_reading(r, g6.MISS, "N3.1")
        self.assertIn("0 revision(s) completed", r["detail"])

    def test_n3_1_error(self):
        r = g6.read_n3_1(load_fixture("n3_error.json"), revisions=1)
        self.assert_reading(r, g6.ERROR, "N3.1")
        self.assertIn("per_dimension.D5", r["detail"])

    def test_n3_1_error_on_nan_flag_agreement(self):
        data = load_fixture("n3_pass.json")
        data["flag_agreement"] = float("nan")
        self.assert_reading(g6.read_n3_1(data), g6.ERROR, "N3.1")

    # ---- N3.2 -----------------------------------------------------------
    def test_n3_2_pass(self):
        r = g6.read_n3_2(load_fixture("n3_pass.json"))
        self.assert_reading(r, g6.PASS, "N3.2")
        self.assertAlmostEqual(r["numbers"]["max_lofo_change"], 0.04)
        self.assertEqual(r["numbers"]["read_from"], "max_lofo_change")

    def test_n3_2_pass_derived_from_the_lofo_block(self):
        r = g6.read_n3_2(load_fixture("n3_lofo_block.json"))
        self.assert_reading(r, g6.PASS, "N3.2")
        self.assertAlmostEqual(r["numbers"]["max_lofo_change"], 0.06)
        self.assertEqual(r["numbers"]["read_from"], "leave_one_family_out")
        self.assertEqual(r["numbers"]["worst_cell"], "qwen/D4")

    def test_n3_2_fail(self):
        r = g6.read_n3_2(load_fixture("n3_fail32.json"))
        self.assert_reading(r, g6.FAIL, "N3.2")
        self.assertAlmostEqual(r["numbers"]["max_lofo_change"], 0.24)

    def test_n3_2_miss(self):
        r = g6.read_n3_2(load_fixture("n3_miss.json"))
        self.assert_reading(r, g6.MISS, "N3.2")
        self.assertAlmostEqual(r["numbers"]["max_lofo_change"], 0.15)

    def test_n3_2_error(self):
        r = g6.read_n3_2(load_fixture("n3_error.json"))
        self.assert_reading(r, g6.ERROR, "N3.2")
        self.assertIn("max_lofo_change", r["detail"])

    # ---- parents --------------------------------------------------------
    def test_parent_n1(self):
        self.assertEqual(g6.read_n1(g6.PASS, g6.PASS)["reading"], g6.PASS)
        self.assertEqual(g6.read_n1(g6.FAIL, g6.PASS)["reading"], g6.FAIL)
        self.assertEqual(g6.read_n1(g6.FAIL, g6.ERROR)["reading"], g6.FAIL)
        self.assertEqual(g6.read_n1(g6.PASS, g6.MISS)["reading"], g6.MISS)
        self.assertEqual(g6.read_n1(g6.ERROR, g6.PASS)["reading"], g6.ERROR)
        self.assertEqual(g6.read_n1(g6.PASS, g6.ERROR)["reading"], g6.ERROR)

    def test_parent_n3(self):
        self.assertEqual(g6.read_n3(g6.PASS, g6.PASS)["reading"], g6.PASS)
        self.assertEqual(g6.read_n3(g6.FAIL, g6.PASS)["reading"], g6.FAIL)
        self.assertEqual(g6.read_n3(g6.PASS, g6.FAIL)["reading"], g6.FAIL)
        self.assertEqual(g6.read_n3(g6.MISS, g6.PASS)["reading"], g6.MISS)
        self.assertEqual(g6.read_n3(g6.ERROR, g6.PASS)["reading"], g6.ERROR)


# ==========================================================================
# G6 - aggregates
# ==========================================================================
class TestG6Aggregate(unittest.TestCase):
    def agg(self, **readings):
        table = {"N1": g6.MISS, "N1.1": g6.MISS, "N1.2": g6.MISS, "N2": g6.MISS, "N3": g6.MISS}
        table.update(readings)
        return g6.aggregate(table)["verdict"]

    def test_go(self):
        self.assertEqual(
            self.agg(**{"N1": g6.PASS, "N1.1": g6.PASS, "N1.2": g6.PASS}), g6.GO
        )

    def test_kill(self):
        self.assertEqual(
            self.agg(**{"N1": g6.FAIL, "N1.1": g6.FAIL, "N2": g6.FAIL, "N3": g6.FAIL}), g6.KILL
        )

    def test_kill_with_survivor_n2(self):
        self.assertEqual(
            self.agg(**{"N1": g6.FAIL, "N1.1": g6.FAIL, "N2": g6.PASS}), g6.KILL_WITH_SURVIVOR
        )

    def test_kill_with_survivor_n3(self):
        self.assertEqual(
            self.agg(**{"N1": g6.FAIL, "N1.1": g6.FAIL, "N3": g6.PASS}), g6.KILL_WITH_SURVIVOR
        )

    def test_inconclusive_on_miss(self):
        self.assertEqual(self.agg(), g6.INCONCLUSIVE)

    def test_inconclusive_when_n1_1_passes_but_n1_2_does_not(self):
        self.assertEqual(
            self.agg(**{"N1": g6.MISS, "N1.1": g6.PASS, "N1.2": g6.MISS}), g6.INCONCLUSIVE
        )

    def test_error_is_never_kill(self):
        verdict = g6.aggregate(
            {"N1": g6.ERROR, "N1.1": g6.ERROR, "N1.2": g6.ERROR, "N2": g6.ERROR, "N3": g6.ERROR}
        )
        self.assertEqual(verdict["verdict"], g6.INCONCLUSIVE)
        self.assertIn("ERROR is never KILL", verdict["because"])


# ==========================================================================
# G6 - CLI end to end
# ==========================================================================
class TestG6CLI(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="g6cli_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def judge_cli(self, n1, n2, n3, prereg=PREREG, sha=SHA, out=None, revisions=None):
        out = out or (self.tmp / "verdict.json")
        args = [
            "--prereg", str(prereg), "--sha", str(sha),
            "--n1", str(FIX / n1), "--n2", str(FIX / n2), "--n3", str(FIX / n3),
            "--out", str(out),
        ]
        if revisions is not None:
            args += ["--n3-revisions", str(revisions)]
        return run_cli("kyra.g6", args), out

    def test_go_verdict_carries_hashes_and_numbers(self):
        proc, out = self.judge_cli("n1_pass.json", "n2_pass.json", "n3_pass.json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        verdict = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(verdict["aggregate"]["verdict"], g6.GO)
        self.assertEqual(verdict["protocol"]["prereg_sha256"], sha256(PREREG))
        self.assertEqual(SHA.read_text().split()[0], verdict["protocol"]["prereg_sha256"])
        self.assertEqual(verdict["inputs"]["n1"]["sha256"], sha256(FIX / "n1_pass.json"))
        self.assertEqual(verdict["inputs"]["n2"]["sha256"], sha256(FIX / "n2_pass.json"))
        self.assertEqual(verdict["inputs"]["n3"]["sha256"], sha256(FIX / "n3_pass.json"))
        self.assertEqual(
            verdict["reading_table"],
            {"N1": "PASS", "N1.1": "PASS", "N1.2": "PASS", "N2": "PASS",
             "N3": "PASS", "N3.1": "PASS", "N3.2": "PASS"},
        )
        n11 = [r for r in verdict["readings"] if r["claim_id"] == "N1.1"][0]
        self.assertEqual(n11["numbers"], {"odds_ratio": 2.10, "ci_lower": 1.35, "ci_upper": 3.30})
        self.assertEqual(n11["threshold"], 1.6)
        self.assertEqual(verdict["process_inputs"]["n3_revisions"], 0)

    def test_kill_verdict(self):
        proc, out = self.judge_cli("n1_kill.json", "n2_fail.json", "n3_fail32.json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        verdict = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(verdict["aggregate"]["verdict"], g6.KILL)

    def test_kill_with_survivor_verdict(self):
        proc, out = self.judge_cli(
            "n1_kill.json", "n2_pass.json", "n3_fail31.json", revisions=1
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        verdict = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(verdict["aggregate"]["verdict"], g6.KILL_WITH_SURVIVOR)
        self.assertEqual(verdict["reading_table"]["N3.1"], g6.FAIL)
        self.assertEqual(verdict["process_inputs"]["n3_revisions"], 1)

    def test_n3_revisions_is_recorded_and_changes_only_the_fail_branch(self):
        proc, out = self.judge_cli(
            "n1_kill.json", "n2_pass.json", "n3_fail31.json", revisions=0
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        verdict = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(verdict["reading_table"]["N3.1"], g6.MISS)
        self.assertEqual(verdict["process_inputs"]["n3_revisions"], 0)

    def test_inconclusive_verdict(self):
        proc, out = self.judge_cli("n1_miss.json", "n2_miss.json", "n3_miss.json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        verdict = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(verdict["aggregate"]["verdict"], g6.INCONCLUSIVE)

    def test_missing_input_file_is_error_not_kill(self):
        out = self.tmp / "verdict_missing.json"
        proc = run_cli(
            "kyra.g6",
            ["--prereg", str(PREREG), "--sha", str(SHA),
             "--n1", str(self.tmp / "nope.json"), "--n2", str(FIX / "n2_pass.json"),
             "--n3", str(FIX / "n3_pass.json"), "--out", str(out)],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        verdict = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(verdict["reading_table"]["N1.1"], g6.ERROR)
        self.assertEqual(verdict["aggregate"]["verdict"], g6.INCONCLUSIVE)

    def test_tampered_prereg_refuses_before_any_reading(self):
        tampered = self.tmp / "PREREGISTERED_tampered.yaml"
        text = PREREG.read_text(encoding="utf-8")
        tampered.write_text(text.replace("threshold: 1.6", "threshold: 1.2", 1), encoding="utf-8")
        receipt = self.tmp / "PREREGISTERED_tampered.yaml.sha256"
        receipt.write_text(SHA.read_text(encoding="utf-8"), encoding="utf-8")  # frozen hash
        out = self.tmp / "must_not_exist.json"
        proc, _ = self.judge_cli(
            "n1_pass.json", "n2_pass.json", "n3_pass.json",
            prereg=tampered, sha=receipt, out=out,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.returncode, g6.EXIT_MISMATCH)
        self.assertIn("ERROR FREEZE_MISMATCH", proc.stderr)
        self.assertFalse(out.exists(), "no verdict may be written for a tampered protocol")
        self.assertNotIn("PASS", proc.stdout)

    def test_refrozen_but_altered_table_is_an_error(self):
        """Hash matches its own receipt, yet the rules no longer match the code."""
        altered = self.tmp / "PREREGISTERED_altered.yaml"
        text = PREREG.read_text(encoding="utf-8").replace("threshold: 1.6", "threshold: 1.5", 1)
        altered.write_text(text, encoding="utf-8")
        receipt = self.tmp / "PREREGISTERED_altered.yaml.sha256"
        receipt.write_text("%s  %s\n" % (sha256(altered), altered.name), encoding="utf-8")
        out = self.tmp / "must_not_exist2.json"
        proc, _ = self.judge_cli(
            "n1_pass.json", "n2_pass.json", "n3_pass.json",
            prereg=altered, sha=receipt, out=out,
        )
        self.assertEqual(proc.returncode, g6.EXIT_TABLE, proc.stderr)
        self.assertIn("PROTOCOL_TABLE_MISMATCH", proc.stderr)
        self.assertFalse(out.exists())

    def test_missing_prereg_file(self):
        out = self.tmp / "nope_verdict.json"
        proc, _ = self.judge_cli(
            "n1_pass.json", "n2_pass.json", "n3_pass.json",
            prereg=self.tmp / "absent.yaml", sha=SHA, out=out,
        )
        self.assertEqual(proc.returncode, g6.EXIT_MISSING, proc.stderr)
        self.assertFalse(out.exists())


# ==========================================================================
# campaign - subset and guards
# ==========================================================================
class TestCampaignSubset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = load_items(REAL_ITEMS)

    def test_subset_is_twenty_percent_and_deterministic(self):
        ids, plan = campaign.stratified_subset(self.items)
        self.assertEqual(len(self.items), 156)
        self.assertEqual(len(ids), 31)  # round(0.2 * 156)
        self.assertEqual(len(set(ids)), len(ids))
        again, _ = campaign.stratified_subset(self.items)
        self.assertEqual(ids, again)
        known = {it.item_id for it in self.items}
        self.assertTrue(set(ids) <= known)

    def test_every_stratum_is_represented(self):
        _, plan = campaign.stratified_subset(self.items)
        self.assertEqual(len(plan), 14)  # 7 risk groups x 2 turn types
        for stratum in plan:
            self.assertGreaterEqual(stratum["n_selected"], 1, stratum)
            self.assertEqual(len(stratum["item_ids"]), stratum["n_selected"])
        self.assertEqual(sum(s["n_selected"] for s in plan), 31)

    def test_seed_change_changes_the_draw(self):
        a, _ = campaign.stratified_subset(self.items, seed=campaign.SAMPLING_SEED)
        b, _ = campaign.stratified_subset(self.items, seed=campaign.SAMPLING_SEED + 1)
        self.assertNotEqual(a, b)

    def test_smoke_items_subset(self):
        items = load_items(SMOKE_ITEMS)
        ids, _ = campaign.stratified_subset(items)
        self.assertEqual(len(ids), round(0.2 * len(items)))


class TestCampaignGpuPinning(unittest.TestCase):
    """The chosen physical GPU must be pinned before any engine is constructed."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="campaign_gpu_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.csv = self.tmp / "EXPERIMENTS.csv"
        shutil.copy2(REAL_CSV, self.csv)
        self.saved_env = os.environ.get("CUDA_VISIBLE_DEVICES")
        self.addCleanup(self.restore_env)

    def restore_env(self):
        if self.saved_env is None:
            os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        else:
            os.environ["CUDA_VISIBLE_DEVICES"] = self.saved_env

    def test_chosen_gpu_is_pinned_before_the_provider_is_built(self):
        from kyra.providers import MockProvider

        os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        seen = []

        def spy_provider(model, temperature, seed, gpu_index):
            seen.append((model["model_id"], os.environ.get("CUDA_VISIBLE_DEVICES"), gpu_index))
            return MockProvider()

        original = campaign.make_provider
        campaign.make_provider = spy_provider
        self.addCleanup(setattr, campaign, "make_provider", original)

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = campaign.main(
                ["--items", str(SMOKE_ITEMS), "--models", str(FIX / "models_fake_vllm.json"),
                 "--cohort", "gpupin", "--class", "smoke",
                 "--out-root", str(self.tmp / "raw"), "--experiments-csv", str(self.csv)],
                gpu_probe=fake_gpu_probe(),
            )
        self.assertEqual(code, 0, buf.getvalue())
        self.assertTrue(seen)
        for model_id, env_at_build, gpu_index in seen:
            self.assertEqual(env_at_build, "1", "%s built without the GPU pinned" % model_id)
            self.assertEqual(gpu_index, 1)
        self.assertIn("pinned CUDA_VISIBLE_DEVICES=1", buf.getvalue())

        record = json.loads(
            one_campaign_record(self.tmp / "raw" / "gpupin", "gpupin").read_text(encoding="utf-8")
        )
        for pre in record["preflight"]:
            self.assertEqual(pre["gpu"]["chosen"], 1)
            self.assertEqual(pre["gpu"]["pinned_cuda_visible_devices"], "1")
        self.assertEqual({r["gpu"] for r in record["runs"]}, {1})
        with self.csv.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertTrue(all("gpu=1" in row[2] for row in rows[-8:]), rows[-1][2])

    def test_inherited_cuda_visible_devices_restricts_the_candidates(self):
        gpus = [{"index": i, "used_mib": 4} for i in range(4)]
        rec = campaign.select_gpu(
            True, gpu_probe=fake_gpu_probe(gpus=gpus), env_value="2,3"
        )
        self.assertEqual(rec["candidates"], [2])
        self.assertEqual(rec["chosen"], 2)
        self.assertTrue(rec["inherited"])
        self.assertEqual(rec["inherited_cuda_visible_devices"], "2,3")

        only_three = campaign.select_gpu(
            True, gpu_probe=fake_gpu_probe(gpus=gpus), env_value="3"
        )
        self.assertEqual(only_three["candidates"], [])
        self.assertIsNone(only_three["chosen"])
        self.assertFalse(only_three["ok"])

    def test_gpu_override_is_refused_when_busy_or_forbidden(self):
        gpus = [
            {"index": 0, "used_mib": 18779},
            {"index": 1, "used_mib": 4},
            {"index": 2, "used_mib": 4},
            {"index": 3, "used_mib": 4},
        ]
        busy = campaign.select_gpu(True, gpu_probe=fake_gpu_probe(gpus=gpus), override=0)
        self.assertFalse(busy["ok"])
        self.assertIn("already in use", busy["error"])
        forbidden = campaign.select_gpu(True, gpu_probe=fake_gpu_probe(gpus=gpus), override=3)
        self.assertFalse(forbidden["ok"])
        self.assertIn("another user's job", forbidden["error"])
        good = campaign.select_gpu(True, gpu_probe=fake_gpu_probe(gpus=gpus), override=2)
        self.assertTrue(good["ok"])
        self.assertEqual((good["chosen"], good["source"]), (2, "--gpu flag"))

    def test_cli_gpu_override_refusal_is_exit_7(self):
        os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = campaign.main(
                ["--items", str(SMOKE_ITEMS), "--models", str(FIX / "models_fake_vllm.json"),
                 "--cohort", "gpubad", "--class", "smoke", "--dry-run", "--gpu", "3",
                 "--out-root", str(self.tmp / "raw2"), "--experiments-csv", str(self.csv)],
                gpu_probe=fake_gpu_probe(),
            )
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, buf.getvalue())
        self.assertIsNone(os.environ.get("CUDA_VISIBLE_DEVICES"))


class TestCampaignGpuGuard(unittest.TestCase):
    def test_first_free_gpu_of_0_1_2(self):
        gpus = [
            {"index": 0, "used_mib": 18779},
            {"index": 1, "used_mib": 4},
            {"index": 2, "used_mib": 4},
            {"index": 3, "used_mib": 4},
        ]
        self.assertEqual(campaign.choose_gpu(gpus), 1)

    def test_gpu_three_is_never_chosen(self):
        gpus = [
            {"index": 0, "used_mib": 40000},
            {"index": 1, "used_mib": 40000},
            {"index": 2, "used_mib": 40000},
            {"index": 3, "used_mib": 0},
        ]
        self.assertIsNone(campaign.choose_gpu(gpus))

    def test_gpu_zero_when_free(self):
        self.assertEqual(campaign.choose_gpu([{"index": 0, "used_mib": 10}]), 0)


# ==========================================================================
# campaign - dry run
# ==========================================================================
def fake_gpu_probe(gpus=None, error=None):
    if gpus is None and error is None:
        gpus = [
            {"index": 0, "used_mib": 18779},
            {"index": 1, "used_mib": 4},
            {"index": 2, "used_mib": 4},
            {"index": 3, "used_mib": 4},
        ]

    def probe():
        return gpus, error

    return probe


class TestCampaignDryRun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="campaign_dry_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out_root = self.tmp / "raw"
        self.csv = self.tmp / "EXPERIMENTS.csv"

    def dry_run(self, models, run_class, prereg=PREREG, sha=SHA, probe=None):
        argv = [
            "--items", str(REAL_ITEMS),
            "--models", str(models),
            "--cohort", "dryrun",
            "--class", run_class,
            "--dry-run",
            "--out-root", str(self.out_root),
            "--experiments-csv", str(self.csv),
            "--prereg", str(prereg),
            "--sha", str(sha),
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = campaign.main(argv, gpu_probe=probe or fake_gpu_probe())
        return code, buf.getvalue()

    def test_dry_run_plan_smoke(self):
        code, out = self.dry_run(FIX / "models_fake.json", "smoke")
        self.assertEqual(code, 0, out)
        self.assertIn("repeat subset: 31 item(s)", out)
        self.assertIn("n=156", out)
        self.assertIn("run main", out)
        self.assertIn("run repeat_3", out)
        self.assertIn("temperature=0.7", out)
        self.assertIn("runs: 8 (2 model(s) x 4 run(s))", out)
        record = json.loads(
            one_campaign_record(self.out_root / "dryrun", "dryrun").read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "dry-run")
        self.assertEqual(record["runs"], [])
        self.assertEqual(record["plan"]["subset"]["n_selected"], 31)
        self.assertFalse(self.csv.exists(), "a dry run must not touch EXPERIMENTS.csv")

    def test_dry_run_confirmatory_verifies_freeze_and_chooses_a_gpu(self):
        code, out = self.dry_run(FIX / "models_fake_vllm.json", "confirmatory")
        self.assertEqual(code, 0, out)
        self.assertIn("GPU 1 via first free candidate", out)
        self.assertIn("CUDA_VISIBLE_DEVICES=1", out)
        self.assertIn("preflight freeze: OK sha256=%s" % sha256(PREREG), out)
        record = json.loads(
            one_campaign_record(self.out_root / "dryrun", "dryrun").read_text(encoding="utf-8")
        )
        for pre in record["preflight"]:
            self.assertEqual(pre["gpu"]["chosen"], 1)
            self.assertEqual(pre["gpu"]["never"], 3)
            self.assertEqual(pre["freeze"]["sha256"], sha256(PREREG))

    def test_confirmatory_refuses_a_mismatched_freeze_hash(self):
        tampered = self.tmp / "PREREGISTERED_kyra_v2.yaml"
        raw = PREREG.read_bytes()
        tampered.write_bytes(raw[:-1] + b"#")  # one byte changed
        receipt = self.tmp / "PREREGISTERED_kyra_v2.yaml.sha256"
        receipt.write_text(SHA.read_text(encoding="utf-8"), encoding="utf-8")
        code, out = self.dry_run(
            FIX / "models_fake_vllm.json", "confirmatory", prereg=tampered, sha=receipt
        )
        self.assertEqual(code, campaign.EXIT_FREEZE_MISMATCH, out)
        record = json.loads(
            one_campaign_record(self.out_root / "dryrun", "dryrun").read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "refused")
        self.assertIn("FREEZE_MISMATCH", record["preflight"][0]["freeze"]["error"])
        self.assertEqual(record["runs"], [])

    def test_confirmatory_refuses_a_mock_provider(self):
        code, out = self.dry_run(FIX / "models_fake.json", "confirmatory")
        self.assertEqual(code, campaign.EXIT_BAD_INPUT, out)

    def test_no_free_gpu_is_a_preflight_refusal(self):
        busy = [{"index": i, "used_mib": 40000} for i in range(3)] + [
            {"index": 3, "used_mib": 0}
        ]
        code, out = self.dry_run(
            FIX / "models_fake_vllm.json", "confirmatory", probe=fake_gpu_probe(gpus=busy)
        )
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)

    def test_dry_run_without_out_root_writes_nothing(self):
        cwd = self.tmp / "cwd"
        cwd.mkdir()
        proc = run_cli(
            "kyra.campaign",
            ["--items", str(REAL_ITEMS), "--models", str(FIX / "models_fake.json"),
             "--cohort", "dryrun", "--class", "smoke", "--dry-run"],
            cwd=cwd,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("not written (pass --out-root", proc.stdout)
        self.assertFalse((cwd / "result").exists(), "a dry run must not write into result/raw")

    def test_cli_dry_run_exits_zero(self):
        proc = run_cli(
            "kyra.campaign",
            ["--items", str(REAL_ITEMS), "--models", str(FIX / "models_fake.json"),
             "--cohort", "dryrun", "--class", "smoke", "--dry-run",
             "--out-root", str(self.out_root), "--experiments-csv", str(self.csv)],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("repeat subset: 31 item(s)", proc.stdout)
        self.assertIn("DRY RUN: nothing executed", proc.stdout)


# ==========================================================================
# campaign - smoke end to end with the mock provider
# ==========================================================================
class TestCampaignSmokeRun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="campaign_run_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out_root = self.tmp / "raw"
        self.csv = self.tmp / "EXPERIMENTS.csv"
        shutil.copy2(REAL_CSV, self.csv)  # temp copy: the real CSV is never written
        self.real_csv_sha = sha256(REAL_CSV)

    def tearDown(self):
        self.assertEqual(sha256(REAL_CSV), self.real_csv_sha, "real EXPERIMENTS.csv changed")

    def run_campaign(self, cohort="smoketest"):
        argv = [
            "--items", str(SMOKE_ITEMS),
            "--models", str(FIX / "models_fake.json"),
            "--cohort", cohort,
            "--class", "smoke",
            "--out-root", str(self.out_root),
            "--experiments-csv", str(self.csv),
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = campaign.main(argv, gpu_probe=fake_gpu_probe())
        return code, buf.getvalue()

    def test_two_fake_models_end_to_end(self):
        with self.csv.open(encoding="utf-8", newline="") as fh:
            before = list(csv.reader(fh))
        code, out = self.run_campaign()
        self.assertEqual(code, 0, out)

        record = json.loads(
            one_campaign_record(self.out_root / "smoketest", "smoketest").read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "completed")
        self.assertEqual(len(record["runs"]), 8)  # 2 models x (main + 3 repeats)
        tags = [r["tag"] for r in record["runs"]]
        self.assertEqual(
            tags,
            ["main", "repeat_1", "repeat_2", "repeat_3"] * 2,
            "models must run one at a time, main before repeats",
        )
        for run in record["runs"]:
            self.assertEqual(run["status"], "completed", run)
            marker = Path(run["run_dir"]) / "MARKER"
            self.assertTrue(marker.is_file(), run["run_dir"])
            self.assertEqual(run["marker_sha256"], sha256(marker))
            self.assertTrue(Path(run["log"]).is_file())
            expected_temp = 0.0 if run["tag"] == "main" else 0.7
            self.assertEqual(run["temperature_requested"], expected_temp)
            expected_condition = "base" if run["tag"] == "main" else run["tag"]
            self.assertEqual(run["condition_tag"], expected_condition)
            manifest = [
                json.loads(line)
                for line in (Path(run["run_dir"]) / "manifest.jsonl")
                .read_text(encoding="utf-8").splitlines() if line.strip()
            ]
            self.assertEqual(
                {rec["condition"] for rec in manifest},
                {expected_condition},
                "the manifest must carry the real condition tag",
            )
        self.assertEqual([r["n_items"] for r in record["runs"]][:4], [7, 1, 1, 1])

        with self.csv.open(encoding="utf-8", newline="") as fh:
            after = list(csv.reader(fh))
        self.assertEqual(after[0], list(campaign.EXPERIMENTS_HEADER))
        self.assertEqual(len(after) - len(before), 8)
        for row in after[-8:]:
            fields = dict(zip(campaign.EXPERIMENTS_HEADER, row))
            self.assertEqual(fields["class"], "smoke")
            self.assertEqual(fields["status"], "completed")
            self.assertTrue(fields["marker"].startswith("MARKER sha256 "), fields["marker"])
            self.assertIn("never evidence", fields["failure"])
            self.assertIn("condition=", fields["config"])
            self.assertTrue(Path(fields["log"]).is_file())
            self.assertTrue(Path(fields["raw"]).is_dir())
        self.assertIn("condition=repeat_3", after[-1][2])

    def test_a_failed_run_stops_the_campaign(self):
        original = campaign.make_provider
        calls = {"n": 0}

        def flaky(model, temperature, seed, gpu_index):
            calls["n"] += 1
            if calls["n"] == 2:  # the first repeat of the first model
                return FailingProvider()
            return original(model, temperature, seed, gpu_index)

        campaign.make_provider = flaky
        self.addCleanup(setattr, campaign, "make_provider", original)

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = campaign.main(
                [
                    "--items", str(SMOKE_ITEMS),
                    "--models", str(FIX / "models_fake.json"),
                    "--cohort", "stoptest",
                    "--class", "smoke",
                    "--out-root", str(self.out_root),
                    "--experiments-csv", str(self.csv),
                ],
                gpu_probe=fake_gpu_probe(),
            )
        self.assertEqual(code, campaign.EXIT_RUN_FAILED, buf.getvalue())
        record = json.loads(
            one_campaign_record(self.out_root / "stoptest", "stoptest").read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "failed")
        self.assertEqual(len(record["runs"]), 2)
        self.assertEqual(record["runs"][-1]["status"], "failed")
        self.assertIn("run ", record["stopped_because"])
        with self.csv.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[-1][0].split("__")[1], "fake-tiny-a")
        self.assertEqual(rows[-1][8], "failed")
        self.assertNotIn("fake-tiny-b", "".join(r[0] for r in rows))


# ==========================================================================
# campaign - per-model generation options (chat_template_kwargs / stop_token_ids)
# ==========================================================================
OPTIONS_MODELS = FIX / "models_fake_vllm_options.json"


class TestCampaignGenerationOptions(unittest.TestCase):
    """Optional per-model vLLM options: models.json -> provider, plan, record, CSV."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="campaign_opts_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out_root = self.tmp / "raw"
        self.csv = self.tmp / "EXPERIMENTS.csv"
        shutil.copy2(REAL_CSV, self.csv)
        self.real_csv_sha = sha256(REAL_CSV)
        self.saved_env = os.environ.get("CUDA_VISIBLE_DEVICES")
        self.addCleanup(self.restore_env)

    def restore_env(self):
        if self.saved_env is None:
            os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        else:
            os.environ["CUDA_VISIBLE_DEVICES"] = self.saved_env

    def tearDown(self):
        self.assertEqual(sha256(REAL_CSV), self.real_csv_sha, "real EXPERIMENTS.csv changed")

    def write_models(self, name, models):
        path = self.tmp / name
        path.write_text(json.dumps(models), encoding="utf-8")
        return path

    def run_campaign(self, models_path, cohort, extra=(), spy=None):
        if spy is not None:
            original = campaign.make_provider
            campaign.make_provider = spy
            self.addCleanup(setattr, campaign, "make_provider", original)
        argv = [
            "--items", str(SMOKE_ITEMS),
            "--models", str(models_path),
            "--cohort", cohort,
            "--class", "smoke",
            "--out-root", str(self.out_root),
            "--experiments-csv", str(self.csv),
        ] + list(extra)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = campaign.main(argv, gpu_probe=fake_gpu_probe())
        return code, out.getvalue(), err.getvalue()

    # -- models.json ------------------------------------------------------
    def test_load_models_keeps_the_options_and_nulls_when_absent(self):
        models = campaign.load_models(OPTIONS_MODELS, "smoke")
        self.assertEqual(models[0]["chat_template_kwargs"], {"skip_reasoning": True})
        self.assertEqual(models[0]["stop_token_ids"], [100273, 100275, 100274])
        self.assertIsNone(models[1]["chat_template_kwargs"])
        self.assertIsNone(models[1]["stop_token_ids"])

    def test_make_provider_passes_the_options_to_the_vllm_provider(self):
        from kyra.providers import VLLMProvider

        model = campaign.load_models(OPTIONS_MODELS, "smoke")[0]
        provider = campaign.make_provider(model, 0.0, 20260922, None)  # builds no engine
        self.assertIsInstance(provider, VLLMProvider)
        self.assertEqual(provider.chat_template_kwargs, {"skip_reasoning": True})
        self.assertEqual(provider.stop_token_ids, [100273, 100275, 100274])
        plain = campaign.make_provider(
            campaign.load_models(OPTIONS_MODELS, "smoke")[1], 0.0, 20260922, None
        )
        self.assertEqual(plain.chat_template_kwargs, {})
        self.assertEqual(plain.stop_token_ids, [])

    def test_a_non_vllm_provider_warns_and_ignores_the_options(self):
        from kyra.providers import MockProvider

        models = self.write_models(
            "mock_with_options.json",
            [
                {
                    "model_id": "fake/tiny-a",
                    "model_path": "fake/tiny-a",
                    "family": "fake_a",
                    "provider": "mock",
                    "chat_template_kwargs": {"skip_reasoning": True},
                }
            ],
        )
        model = campaign.load_models(models, "smoke")[0]
        err = io.StringIO()
        with redirect_stderr(err):
            provider = campaign.make_provider(model, 0.0, 20260922, None)
        self.assertIsInstance(provider, MockProvider)
        self.assertIn("WARNING", err.getvalue())
        self.assertIn("fake/tiny-a", err.getvalue())

    # -- plan + record ----------------------------------------------------
    def test_dry_run_plan_prints_the_options_and_the_record_carries_them(self):
        code, out, _ = self.run_campaign(OPTIONS_MODELS, "optdry", extra=["--dry-run"])
        self.assertEqual(code, 0, out)
        self.assertIn('chat_template_kwargs: {"skip_reasoning":true}', out)
        self.assertIn("stop_token_ids: [100273,100275,100274]", out)
        # the model declaring nothing prints neither line
        self.assertEqual(out.count("chat_template_kwargs: "), 1)
        self.assertEqual(out.count("stop_token_ids: "), 1)
        record = json.loads(
            one_campaign_record(self.out_root / "optdry", "optdry").read_text(encoding="utf-8")
        )
        plan_models = {m["model_id"]: m for m in record["plan"]["models"]}
        self.assertEqual(
            plan_models["fake/tiny-vllm-think"]["chat_template_kwargs"],
            {"skip_reasoning": True},
        )
        self.assertEqual(
            plan_models["fake/tiny-vllm-think"]["stop_token_ids"],
            [100273, 100275, 100274],
        )
        self.assertIsNone(plan_models["fake/tiny-vllm-plain"]["chat_template_kwargs"])
        self.assertIsNone(plan_models["fake/tiny-vllm-plain"]["stop_token_ids"])

    # -- EXPERIMENTS config string ---------------------------------------
    def test_config_string_carries_the_options_only_when_declared(self):
        from kyra.providers import MockProvider

        seen = []

        def spy(model, temperature, seed, gpu_index):
            seen.append(
                (model["model_id"], model["chat_template_kwargs"], model["stop_token_ids"])
            )
            return MockProvider()

        code, out, _ = self.run_campaign(OPTIONS_MODELS, "optrun", spy=spy)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(seen), 8)  # 2 models x (main + 3 repeats)
        self.assertEqual(
            seen[0], ("fake/tiny-vllm-think", {"skip_reasoning": True}, [100273, 100275, 100274])
        )
        self.assertEqual(seen[-1], ("fake/tiny-vllm-plain", None, None))

        with self.csv.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        configs = {}
        for row in rows[-8:]:
            fields = dict(zip(campaign.EXPERIMENTS_HEADER, row))
            configs.setdefault(fields["run"].split("__")[1], []).append(fields["config"])

        think_main = configs["fake-tiny-vllm-think"][0]
        self.assertEqual(
            think_main,
            "model=fake/tiny-vllm-think; family=fake_a; provider=vllm; temperature=0.0; "
            "seed=20260922; condition=base; items=7; gpu=1; cohort=optrun; "
            "item_scope=full item set; "
            'chat_template_kwargs={"skip_reasoning":true}; '
            "stop_token_ids=[100273,100275,100274]",
        )
        # a model without the options keeps exactly the previous config format
        plain_main = configs["fake-tiny-vllm-plain"][0]
        self.assertEqual(
            plain_main,
            "model=fake/tiny-vllm-plain; family=fake_b; provider=vllm; temperature=0.0; "
            "seed=20260922; condition=base; items=7; gpu=1; cohort=optrun; "
            "item_scope=full item set",
        )
        self.assertNotIn("chat_template_kwargs", plain_main)
        self.assertNotIn("stop_token_ids", plain_main)

    # -- refusals ---------------------------------------------------------
    def test_invalid_options_are_bad_input_naming_the_model(self):
        bad_kwargs = self.write_models(
            "bad_kwargs.json",
            [
                {
                    "model_id": "fake/bad-kwargs",
                    "model_path": "fake/bad-kwargs",
                    "family": "fake_a",
                    "provider": "vllm",
                    "chat_template_kwargs": {"opts": {"nested": 1}},
                }
            ],
        )
        code, out, err = self.run_campaign(bad_kwargs, "optbad1", extra=["--dry-run"])
        self.assertEqual(code, campaign.EXIT_BAD_INPUT, out)
        self.assertIn("fake/bad-kwargs", err)
        self.assertIn("chat_template_kwargs", err)

        bad_ids = self.write_models(
            "bad_ids.json",
            [
                {
                    "model_id": "fake/bad-ids",
                    "model_path": "fake/bad-ids",
                    "family": "fake_a",
                    "provider": "vllm",
                    "stop_token_ids": [100273, "100275"],
                }
            ],
        )
        code, out, err = self.run_campaign(bad_ids, "optbad2", extra=["--dry-run"])
        self.assertEqual(code, campaign.EXIT_BAD_INPUT, out)
        self.assertIn("fake/bad-ids", err)
        self.assertIn("stop_token_ids", err)

        not_a_list = self.write_models(
            "bad_ids2.json",
            [
                {
                    "model_id": "fake/bad-ids-2",
                    "model_path": "fake/bad-ids-2",
                    "family": "fake_a",
                    "provider": "vllm",
                    "stop_token_ids": 100273,
                }
            ],
        )
        code, out, err = self.run_campaign(not_a_list, "optbad3", extra=["--dry-run"])
        self.assertEqual(code, campaign.EXIT_BAD_INPUT, out)
        self.assertIn("fake/bad-ids-2", err)


# ==========================================================================
# campaign score: judges + panel over finished run directories
# ==========================================================================
ANCHORS = REPO / "research" / "judge_anchors_v1.json"


def fake_judge_outputs(run_dir, items_path, offset=0):
    """One canned judge reply per prefix view, in the order kyra.judge asks.

    The A list must have exactly `depth` turn objects and control views (items
    whose risk_group is CTRL) must carry over_refusal/helpfulness, else the
    panel drops the judge - so the double is built from the run's own
    responses.jsonl and the item file.
    """
    from kyra.judge import read_conversations

    control = {it.item_id for it in load_items(items_path) if it.risk_group == "CTRL"}
    outputs = []
    for conv in read_conversations(run_dir):
        is_control = conv["item_id"] in control
        for depth in range(1, len(conv["turns"]) + 1):
            rec = {
                "D": {"D1": 2, "D2": 2, "D3": 1 + offset, "D4": 1, "D5": 2, "D6": 2},
                "A": [{"A1": 0, "A2": 1, "A3": 0, "A4": 0} for _ in range(depth)],
                "critical_failure": False,
                "cf_codes": [],
                "rationale": "canned fake judge reply (depth %d)" % depth,
            }
            if is_control:
                rec["over_refusal"] = False
                rec["helpfulness"] = 2
            outputs.append(json.dumps(rec, ensure_ascii=False))
    return outputs


class TestCampaignScoring(unittest.TestCase):
    """End-to-end: generate a smoke run with mock models, then score it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="campaign_score_"))
        cls.out_root = cls.tmp / "raw"
        cls.csv = cls.tmp / "EXPERIMENTS.csv"
        shutil.copy2(REAL_CSV, cls.csv)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = campaign.main(
                ["--items", str(SMOKE_ITEMS), "--models", str(FIX / "models_fake.json"),
                 "--cohort", "scoreme", "--class", "smoke",
                 "--out-root", str(cls.out_root), "--experiments-csv", str(cls.csv)],
                gpu_probe=fake_gpu_probe(),
            )
        assert code == 0, buf.getvalue()
        record = json.loads(
            one_campaign_record(cls.out_root / "scoreme", "scoreme").read_text(encoding="utf-8")
        )
        cls.runs = [r["run_dir"] for r in record["runs"]]
        cls.main_run = cls.runs[0]          # fake/tiny-a, condition base
        cls.second_run = cls.runs[1]        # fake/tiny-a, repeat_1
        cls.judges_doc = json.loads((FIX / "judges_fake.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def judges_file(self, run_dir, keep=None, offset=0):
        """judges.json with fake_outputs generated for this run directory."""
        doc = json.loads(json.dumps(self.judges_doc))
        judges = doc["judges"] if keep is None else [
            j for j in doc["judges"] if j["judge_id"] in keep
        ]
        for i, judge in enumerate(judges):
            out = self.tmp / ("fake_outputs_%s_%s.json" % (judge["judge_id"], Path(run_dir).name))
            out.write_text(
                json.dumps(fake_judge_outputs(run_dir, SMOKE_ITEMS, offset=i + offset)),
                encoding="utf-8",
            )
            judge["fake_outputs"] = str(out)
        path = self.tmp / ("judges_%s.json" % Path(run_dir).name)
        path.write_text(json.dumps({"judges": judges}), encoding="utf-8")
        return path

    def score(self, run_dir, judges_path, cohort, extra=None):
        argv = [
            "score",
            "--items", str(SMOKE_ITEMS),
            "--models", str(FIX / "models_fake.json"),
            "--judges", str(judges_path),
            "--cohort", cohort,
            "--runs", str(run_dir),
            "--anchors", str(ANCHORS),
            "--out-root", str(self.out_root),
            "--experiments-csv", str(self.csv),
        ] + list(extra or [])
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = campaign.main(argv, gpu_probe=fake_gpu_probe())
        return code, buf.getvalue()

    def read_jsonl(self, path):
        return [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_1_dry_run_prints_the_plan(self):
        code, out = self.score(
            self.main_run, self.judges_file(self.main_run), "scoredry", extra=["--dry-run"]
        )
        self.assertEqual(code, 0, out)
        self.assertIn("SCORING PLAN cohort=scoredry", out)
        self.assertIn("views: prefix", out)
        self.assertIn(sha256(ANCHORS), out)
        self.assertIn("judge -> ", out)
        self.assertIn("panel -> ", out)
        self.assertIn("class=smoke", out)
        self.assertIn("evaluated_family=fake_a", out)
        self.assertIn("control) - every id present in the items file", out)
        self.assertFalse((Path(self.main_run) / "judge_JF1.jsonl").exists())

    def test_2_two_fake_judges_and_panel_end_to_end(self):
        with self.csv.open(encoding="utf-8", newline="") as fh:
            before = len(list(csv.reader(fh)))
        code, out = self.score(self.main_run, self.judges_file(self.main_run), "scored")
        self.assertEqual(code, 0, out)

        run_dir = Path(self.main_run)
        judge_records = {}
        for judge_id in ("JF1", "JF2"):
            path = run_dir / ("judge_%s.jsonl" % judge_id)
            self.assertTrue(path.is_file(), out)
            rows = self.read_jsonl(path)
            judge_records[judge_id] = rows
            self.assertTrue(all(r["view"] == "prefix" for r in rows))
            self.assertTrue(all(r["status"] == "ok" for r in rows), rows[:1])
            controls = [r for r in rows if r["is_control"]]
            self.assertTrue(controls, "the items file must mark CTRL items as controls")
            for r in controls:
                self.assertIn("over_refusal", r["record"])
                self.assertIn("helpfulness", r["record"])
            for r in rows:
                if not r["is_control"]:
                    self.assertNotIn("over_refusal", r["record"])

        panel_rows = self.read_jsonl(run_dir / "panel.jsonl")
        self.assertEqual(len(panel_rows), len(judge_records["JF1"]))
        depths = {(r["item_id"], r["depth"]) for r in panel_rows}
        self.assertEqual(len(depths), len(panel_rows), "one panel record per (item, depth)")
        self.assertTrue(all(r["status"] == "ok" for r in panel_rows), panel_rows[:1])
        for r in panel_rows:
            self.assertEqual(sorted(r["judges_used"]), ["JF1", "JF2"])
            self.assertEqual(r["evaluated_family"], "fake_a")
            self.assertEqual(len(r["A"]), r["depth"])
            if r["is_control"]:
                self.assertIsInstance(r["over_refusal"], bool)
                self.assertIsNotNone(r["helpfulness"])
            else:
                self.assertIsNone(r["over_refusal"])
        multi = [r for r in panel_rows if r["item_id"] == "KYRA-SMK-004"]
        self.assertEqual(sorted(r["depth"] for r in multi), [1, 2, 3])

        record = json.loads(
            one_campaign_record(self.out_root / "scored", "scored", "_scoring").read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "completed")
        self.assertEqual(len(record["judge_runs"]), 2)
        self.assertEqual(len(record["panel_runs"]), 1)
        self.assertEqual(record["plan"]["anchors_sha256"], sha256(ANCHORS))
        self.assertEqual(record["plan"]["family_map"], {"JF1": "judge_x", "JF2": "judge_y"})
        self.assertTrue(all(j["anchors_sha256"] == sha256(ANCHORS) for j in record["judge_runs"]))
        self.assertEqual(record["freeze"]["required"], False)

        with self.csv.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows) - before, 3)  # two judges + one panel
        for row in rows[-3:]:
            fields = dict(zip(campaign.EXPERIMENTS_HEADER, row))
            self.assertEqual(fields["class"], "smoke")
            self.assertEqual(fields["status"], "completed")
            self.assertIn("anchors_sha256=%s" % sha256(ANCHORS), fields["config"])
            self.assertTrue(Path(fields["log"]).is_file())
        self.assertIn("--views prefix", rows[-3][4])
        self.assertIn("--items", rows[-3][4])
        self.assertIn("kyra.panel", rows[-1][4])

    def test_3_existing_judge_file_is_refused(self):
        code, out = self.score(self.main_run, self.judges_file(self.main_run), "scoreagain")
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)

    def test_4_single_judge_panel_is_insufficient(self):
        code, out = self.score(
            self.second_run, self.judges_file(self.second_run, keep={"JF1"}), "scoreone"
        )
        self.assertEqual(code, 0, out)
        panel_rows = self.read_jsonl(Path(self.second_run) / "panel.jsonl")
        self.assertTrue(panel_rows)
        for r in panel_rows:
            self.assertEqual(r["status"], "INSUFFICIENT")
            self.assertIsNone(r["D"])
            self.assertIn("minimum 2", r["reason"])

    def test_5_missing_marker_is_refused(self):
        bare = self.tmp / "no_marker_run"
        bare.mkdir()
        shutil.copy2(Path(self.main_run) / "responses.jsonl", bare / "responses.jsonl")
        shutil.copy2(Path(self.main_run) / "manifest.jsonl", bare / "manifest.jsonl")
        code, out = self.score(bare, self.judges_file(self.main_run), "scorebare")
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertFalse((bare / "judge_JF1.jsonl").exists())

    def test_6a_items_not_covering_the_run_is_refused(self):
        """The mistake this guard exists for: scoring a smoke run against the
        phase-A item file would turn every control view into a risk view."""
        argv = [
            "score",
            "--items", str(REAL_ITEMS),          # wrong item file for this run
            "--models", str(FIX / "models_fake.json"),
            "--judges", str(self.judges_file(self.runs[2])),
            "--cohort", "scorecover",
            "--runs", str(self.runs[2]),
            "--anchors", str(ANCHORS),
            "--out-root", str(self.out_root),
            "--experiments-csv", str(self.csv),
        ]
        buf = io.StringIO()
        with self.csv.open(encoding="utf-8", newline="") as fh:
            before = len(list(csv.reader(fh)))
        with redirect_stdout(buf):
            code = campaign.main(argv, gpu_probe=fake_gpu_probe())
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, buf.getvalue())
        self.assertFalse((Path(self.runs[2]) / "judge_JF1.jsonl").exists())
        self.assertEqual(
            campaign_records(self.out_root / "scorecover", "scorecover", "_scoring"), []
        )
        with self.csv.open(encoding="utf-8", newline="") as fh:
            self.assertEqual(len(list(csv.reader(fh))), before)

    def test_6b_panel_overwrite_is_refused_without_the_flag(self):
        run_dir = Path(self.runs[3])
        judges_path = self.judges_file(run_dir)
        code, out = self.score(run_dir, judges_path, "scorepanel1")
        self.assertEqual(code, 0, out)
        panel_before = sha256(run_dir / "panel.jsonl")

        # judge files now exist too, so clear them to isolate the panel guard
        for judge_id in ("JF1", "JF2"):
            (run_dir / ("judge_%s.jsonl" % judge_id)).unlink()
        code, out = self.score(run_dir, judges_path, "scorepanel2")
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertEqual(sha256(run_dir / "panel.jsonl"), panel_before)
        self.assertFalse((run_dir / "judge_JF1.jsonl").exists())

        code, out = self.score(
            run_dir, judges_path, "scorepanel3", extra=["--allow-panel-overwrite"]
        )
        self.assertEqual(code, 0, out)
        record = json.loads(
            one_campaign_record(self.out_root / "scorepanel3", "scorepanel3", "_scoring")
            .read_text(encoding="utf-8")
        )
        self.assertTrue(record["allow_panel_overwrite"])
        self.assertTrue(record["plan"]["allow_panel_overwrite"])
        self.assertEqual(record["status"], "completed")

    def test_7_declared_batch_size_reaches_the_judge_command_and_the_config(self):
        """judges.json "batch_size": 16 -> kyra.judge --batch-size 16 and a
        config string that says so; a judge that does not declare it keeps the
        exact config string it had before the option existed."""
        run_dir = Path(self.runs[4])
        judges_path = self.judges_file(run_dir)
        doc = json.loads(judges_path.read_text(encoding="utf-8"))
        doc["judges"][0]["batch_size"] = 16          # JF1 declares, JF2 does not
        judges_path.write_text(json.dumps(doc), encoding="utf-8")

        with self.csv.open(encoding="utf-8", newline="") as fh:
            before = len(list(csv.reader(fh)))
        code, out = self.score(run_dir, judges_path, "scorebatch")
        self.assertEqual(code, 0, out)

        record = json.loads(
            one_campaign_record(self.out_root / "scorebatch", "scorebatch", "_scoring")
            .read_text(encoding="utf-8")
        )
        plan_judges = {j["judge_id"]: j for j in record["plan"]["judges"]}
        self.assertEqual(plan_judges["JF1"]["batch_size"], 16)
        self.assertNotIn("batch_size", plan_judges["JF2"])

        with self.csv.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows) - before, 3)  # two judges + one panel
        fields = {}
        for row in rows[-3:]:
            f = dict(zip(campaign.EXPERIMENTS_HEADER, row))
            fields[f["run"].split("__")[-1]] = f

        def expected_config(judge_id, family, model, extra=""):
            return (
                "judge=%s; family=%s; provider=fake; model=%s; views=prefix; "
                "items=%s; anchors=%s; anchors_sha256=%s; evaluated_family=%s; "
                "gpu=%s; run_dir=%s%s"
                % (judge_id, family, model, SMOKE_ITEMS, ANCHORS, sha256(ANCHORS),
                   record["plan"]["runs"][0]["evaluated_family"],
                   record["gpu"]["chosen"], run_dir, extra)
            )

        jf1 = fields["judge_JF1"]
        self.assertIn("--batch-size 16", jf1["command"])
        self.assertEqual(
            jf1["config"],
            expected_config("JF1", "judge_x", "fake/judge-1", "; batch_size=16"),
        )
        jf2 = fields["judge_JF2"]
        self.assertNotIn("--batch-size", jf2["command"])
        self.assertEqual(
            jf2["config"], expected_config("JF2", "judge_y", "fake/judge-2")
        )
        self.assertNotIn("batch_size", jf2["config"])
        # the judge file itself is unaffected by the flag
        rows_jf1 = self.read_jsonl(run_dir / "judge_JF1.jsonl")
        rows_jf2 = self.read_jsonl(run_dir / "judge_JF2.jsonl")
        self.assertEqual(len(rows_jf1), len(rows_jf2))
        self.assertTrue(all(r["status"] == "ok" for r in rows_jf1))
        meta = json.loads((run_dir / "judge_JF1.meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["batch_size"], 16)
        self.assertEqual(meta["n_views"], len(rows_jf1))
        self.assertEqual(meta["items_sha256"], sha256(SMOKE_ITEMS))
        self.assertEqual(meta["anchors_sha256"], sha256(ANCHORS))

    def test_6_unknown_run_glob_is_refused(self):
        code, out = self.score(
            self.tmp / "nothing_here_*", self.judges_file(self.main_run), "scoreglob"
        )
        self.assertEqual(code, campaign.EXIT_BAD_INPUT, out)


# ==========================================================================
# campaign score --resume: reuse verified judge output, run only what is missing
# ==========================================================================
ENGINE_ENV_NAMES = ("KYRA_VLLM_ENGINE_KWARGS", "VLLM_BATCH_INVARIANT", "VLLM_ATTENTION_BACKEND")


class TestCampaignScoringResume(unittest.TestCase):
    """The Kanana situation: judges J1/J2 finished, J3's engines failed. A second
    pass with --resume must keep the finished judge files (provenance-checked,
    no subprocess), run only the missing judge, and refuse loudly on any
    provenance difference. Fake judge providers only; no GPU, no weights."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="campaign_resume_"))
        cls.out_root = cls.tmp / "raw"
        cls.csv = cls.tmp / "EXPERIMENTS.csv"
        shutil.copy2(REAL_CSV, cls.csv)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = campaign.main(
                ["--items", str(SMOKE_ITEMS), "--models", str(FIX / "models_fake.json"),
                 "--cohort", "resumeme", "--class", "smoke",
                 "--out-root", str(cls.out_root), "--experiments-csv", str(cls.csv)],
                gpu_probe=fake_gpu_probe(),
            )
        assert code == 0, buf.getvalue()
        record = json.loads(
            one_campaign_record(cls.out_root / "resumeme", "resumeme").read_text(encoding="utf-8")
        )
        cls.runs = [r["run_dir"] for r in record["runs"]]
        cls.judges_doc = json.loads((FIX / "judges_fake.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def setUp(self):
        # --resume compares the engine knobs only when this process exports them,
        # so every test starts from "not exported" and puts back what it found.
        for name in ENGINE_ENV_NAMES:
            if name in os.environ:
                self.addCleanup(os.environ.__setitem__, name, os.environ[name])
                del os.environ[name]
            else:
                self.addCleanup(os.environ.pop, name, None)

    # -- fixtures ------------------------------------------------------------

    def judges_file(self, run_dir, keep=None):
        """judges.json with fake_outputs generated for this run directory."""
        doc = json.loads(json.dumps(self.judges_doc))
        judges = doc["judges"] if keep is None else [
            j for j in doc["judges"] if j["judge_id"] in keep
        ]
        for i, judge in enumerate(judges):
            out = self.tmp / ("fake_outputs_%s_%s.json" % (judge["judge_id"], Path(run_dir).name))
            out.write_text(
                json.dumps(fake_judge_outputs(run_dir, SMOKE_ITEMS, offset=i)),
                encoding="utf-8",
            )
            judge["fake_outputs"] = str(out)
        path = self.tmp / ("judges_%s.json" % Path(run_dir).name)
        path.write_text(json.dumps({"judges": judges}), encoding="utf-8")
        return path

    def score(self, run_dir, judges_path, cohort, extra=None):
        argv = [
            "score",
            "--items", str(SMOKE_ITEMS),
            "--models", str(FIX / "models_fake.json"),
            "--judges", str(judges_path),
            "--cohort", cohort,
            "--runs", str(run_dir),
            "--anchors", str(ANCHORS),
            "--out-root", str(self.out_root),
            "--experiments-csv", str(self.csv),
        ] + list(extra or [])
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            code = campaign.main(argv, gpu_probe=fake_gpu_probe())
        return code, buf.getvalue()

    def read_jsonl(self, path):
        return [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def make_judge_output(self, run_dir, judges_path, judge_id, extra=None):
        """Produce judge_<id>.jsonl + its sidecar exactly as the campaign would.

        Same argv kyra.campaign.judge_command builds for a fake judge (views
        prefix, the items file, the anchors file, no --batch-size), so the
        sidecar this leaves IS a finished judge of the plan under test.
        """
        from kyra.judge import main as judge_main

        entries = {
            j["judge_id"]: j
            for j in json.loads(judges_path.read_text(encoding="utf-8"))["judges"]
        }
        judge = entries[judge_id]
        out_path = Path(run_dir) / ("judge_%s.jsonl" % judge_id)
        argv = [
            "--run-dir", str(run_dir), "--provider", "fake", "--judge-id", judge_id,
            "--family", judge["family"], "--views", "prefix", "--items", str(SMOKE_ITEMS),
            "--out", str(out_path), "--fake-outputs", str(judge["fake_outputs"]),
            "--anchors", str(ANCHORS),
        ] + list(extra or [])
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = judge_main(argv)
        self.assertEqual(rc, 0, buf.getvalue())
        return out_path

    def spy_on_judges(self):
        """Record every judge that actually starts a subprocess."""
        calls = []
        real = campaign.run_one_judge

        def spy(judge, *args, **kwargs):
            calls.append(judge["judge_id"])
            return real(judge, *args, **kwargs)

        campaign.run_one_judge = spy
        self.addCleanup(setattr, campaign, "run_one_judge", real)
        return calls

    def refusal_line(self, out):
        """The ERROR line the pass refused with (not the plan echo above it)."""
        lines = [l for l in out.splitlines() if l.startswith("ERROR: --resume refused")]
        self.assertEqual(len(lines), 1, out)
        return lines[0]

    def edit_meta(self, meta_path, **changes):
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        meta.update(changes)
        Path(meta_path).write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")

    # -- 1. reuse one judge, run the other -----------------------------------

    def test_1_complete_judge_is_reused_and_only_the_missing_one_runs(self):
        run_dir = Path(self.runs[0])
        judges_path = self.judges_file(run_dir)
        j1 = self.make_judge_output(run_dir, judges_path, "JF1")
        j1_meta = run_dir / "judge_JF1.meta.json"
        j1_sha, meta_sha = sha256(j1), sha256(j1_meta)
        j1_stat = (j1.stat().st_mtime_ns, j1.stat().st_size)
        n_views = len(self.read_jsonl(j1))
        calls = self.spy_on_judges()
        with self.csv.open(encoding="utf-8", newline="") as fh:
            before = len(list(csv.reader(fh)))

        code, out = self.score(run_dir, judges_path, "resumeone", extra=["--resume"])
        self.assertEqual(code, 0, out)

        # the reused judge never ran and its file was not touched
        self.assertEqual(calls, ["JF2"], out)
        self.assertEqual(sha256(j1), j1_sha)
        self.assertEqual((j1.stat().st_mtime_ns, j1.stat().st_size), j1_stat)
        logs = sorted(p.name for p in (self.out_root / "resumeone" / "scoring_logs").iterdir())
        self.assertFalse([n for n in logs if "judge_JF1" in n], logs)
        self.assertTrue([n for n in logs if "judge_JF2" in n], logs)
        self.assertIn("REUSED", out)
        self.assertIn("(1 reused)", out)

        # the missing judge and the panel were built
        j2 = run_dir / "judge_JF2.jsonl"
        self.assertEqual(len(self.read_jsonl(j2)), n_views)
        panel_rows = self.read_jsonl(run_dir / "panel.jsonl")
        self.assertEqual(len(panel_rows), n_views)
        self.assertTrue(all(sorted(r["judges_used"]) == ["JF1", "JF2"] for r in panel_rows))

        record = json.loads(
            one_campaign_record(self.out_root / "resumeone", "resumeone", "_scoring")
            .read_text(encoding="utf-8")
        )
        self.assertTrue(record["resume"])
        self.assertTrue(record["plan"]["resume"])
        self.assertEqual(record["status"], "completed")
        runs = {r["judge_id"]: r for r in record["judge_runs"]}
        self.assertEqual(runs["JF1"]["status"], "reused")
        self.assertEqual(runs["JF1"]["sha256"], j1_sha)
        self.assertEqual(runs["JF1"]["meta_sha256"], meta_sha)
        self.assertIsNone(runs["JF1"]["exit_code"])
        self.assertEqual(runs["JF1"]["n_views"], n_views)
        self.assertEqual(runs["JF2"]["status"], "completed")
        self.assertEqual(record["panel_runs"][0]["status"], "completed")

        with self.csv.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows) - before, 3)  # reused judge + run judge + panel
        fields = {}
        for row in rows[-3:]:
            f = dict(zip(campaign.EXPERIMENTS_HEADER, row))
            fields[f["run"].split("__")[-1]] = f
        jf1 = fields["judge_JF1"]
        self.assertEqual(jf1["status"], "reused")
        self.assertIn(j1_sha, jf1["marker"])
        self.assertIn("reused", jf1["marker"])
        self.assertIn(meta_sha, jf1["marker"])
        self.assertIn("no subprocess", jf1["command"])
        self.assertEqual(fields["judge_JF2"]["status"], "completed")
        self.assertEqual(fields["panel"]["status"], "completed")
        # the config cell of a reused judge is the cell the pass would have written
        self.assertEqual(
            jf1["config"].replace("judge=JF1; family=judge_x; provider=fake; model=fake/judge-1",
                                  "X"),
            fields["judge_JF2"]["config"].replace(
                "judge=JF2; family=judge_y; provider=fake; model=fake/judge-2", "X"),
        )

    # -- 2. a finished run: every judge and the panel are reused --------------

    def test_2_a_finished_run_reuses_every_judge_and_the_panel(self):
        run_dir = Path(self.runs[1])
        judges_path = self.judges_file(run_dir)
        code, out = self.score(run_dir, judges_path, "resumefull1")  # normal pass
        self.assertEqual(code, 0, out)
        before = {
            name: sha256(run_dir / name)
            for name in ("judge_JF1.jsonl", "judge_JF2.jsonl", "panel.jsonl")
        }
        calls = self.spy_on_judges()

        code, out = self.score(run_dir, judges_path, "resumefull2", extra=["--resume"])
        self.assertEqual(code, 0, out)
        self.assertEqual(calls, [], out)
        self.assertIn("PANEL REUSED", out)
        self.assertIn("(2 reused)", out)
        self.assertEqual({n: sha256(run_dir / n) for n in before}, before)
        record = json.loads(
            one_campaign_record(self.out_root / "resumefull2", "resumefull2", "_scoring")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(
            [r["status"] for r in record["judge_runs"]], ["reused", "reused"]
        )
        self.assertEqual(record["panel_runs"][0]["status"], "reused")
        self.assertEqual(record["panel_runs"][0]["sha256"], before["panel.jsonl"])
        # no panel subprocess either: not one log file was written
        logs = self.out_root / "resumefull2" / "scoring_logs"
        self.assertFalse(
            sorted(p.name for p in logs.iterdir()) if logs.is_dir() else [],
            "a fully reused pass runs no child process at all",
        )

    # -- 3. any provenance difference refuses the whole pass ------------------

    def test_3_a_provenance_difference_refuses_naming_the_field(self):
        run_dir = Path(self.runs[2])
        judges_path = self.judges_file(run_dir)
        j1 = self.make_judge_output(run_dir, judges_path, "JF1")
        meta_path = run_dir / "judge_JF1.meta.json"
        original_meta = meta_path.read_text(encoding="utf-8")
        original_jsonl = j1.read_text(encoding="utf-8")
        n_views = len(self.read_jsonl(j1))
        cases = [
            ("prompt_template_sha256", {"prompt_template_sha256": "0" * 64}),
            ("anchors_sha256", {"anchors_sha256": "0" * 64}),
            ("items_sha256", {"items_sha256": "0" * 64}),
            ("batch_size", {"batch_size": 1}),
            ("model_path", {"model_path": "/models/some-other-model"}),
            ("n_views", {"n_views": n_views - 1}),
            ("decode_mode", {"decode_mode": "sequential"}),
        ]
        for field, change in cases:
            with self.subTest(field=field):
                self.edit_meta(meta_path, **change)
                code, out = self.score(
                    run_dir, judges_path, "resumebad", extra=["--resume", "--dry-run"]
                )
                self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
                line = self.refusal_line(out)
                self.assertIn(str(run_dir), line)
                self.assertIn("judge JF1", line)
                self.assertIn(field, line)
                meta_path.write_text(original_meta, encoding="utf-8")

        # a judge file that lost a record is refused too (the sidecar still agrees)
        j1.write_text(
            "\n".join(original_jsonl.splitlines()[:-1]) + "\n", encoding="utf-8"
        )
        code, out = self.score(run_dir, judges_path, "resumebad", extra=["--resume", "--dry-run"])
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertIn("records", self.refusal_line(out))
        j1.write_text(original_jsonl, encoding="utf-8")

        # a missing sidecar is a refusal, not a silent re-run
        meta_path.unlink()
        code, out = self.score(run_dir, judges_path, "resumebad", extra=["--resume", "--dry-run"])
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertIn("sidecar", self.refusal_line(out))
        meta_path.write_text(original_meta, encoding="utf-8")

        # and with the sidecar restored the same pass is accepted
        code, out = self.score(run_dir, judges_path, "resumeok", extra=["--resume", "--dry-run"])
        self.assertEqual(code, 0, out)
        self.assertIn("[EXISTS - reused", out)

    def test_3b_a_refusal_runs_nothing_and_overwrites_nothing(self):
        run_dir = Path(self.runs[3])
        judges_path = self.judges_file(run_dir)
        j1 = self.make_judge_output(run_dir, judges_path, "JF1")
        before = sha256(j1)
        self.edit_meta(run_dir / "judge_JF1.meta.json", prompt_template_sha256="0" * 64)
        calls = self.spy_on_judges()

        code, out = self.score(run_dir, judges_path, "resumehard", extra=["--resume"])
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertEqual(calls, [], out)
        self.assertIn("prompt_template_sha256", self.refusal_line(out))
        self.assertEqual(sha256(j1), before)
        self.assertFalse((run_dir / "judge_JF2.jsonl").exists())
        self.assertFalse((run_dir / "panel.jsonl").exists())
        record = json.loads(
            one_campaign_record(self.out_root / "resumehard", "resumehard", "_scoring")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "refused")
        self.assertIn("prompt_template_sha256", record["stopped_because"])

    # -- 4. engine knobs are compared only when this process exports them -----

    def test_4_engine_kwargs_and_vllm_env_are_compared_when_set(self):
        run_dir = Path(self.runs[4])
        judges_path = self.judges_file(run_dir)
        self.make_judge_output(run_dir, judges_path, "JF1")
        meta_path = run_dir / "judge_JF1.meta.json"
        self.edit_meta(
            meta_path,
            provider_effective_params={
                "engine_kwargs": {"attention_backend": "FLASH_ATTN"},
                "vllm_env": {"VLLM_BATCH_INVARIANT": "1"},
            },
        )
        dry = ["--resume", "--dry-run"]

        # (a) nothing exported: the knobs are not compared at all
        code, out = self.score(run_dir, judges_path, "resumeenv_a", extra=dry)
        self.assertEqual(code, 0, out)
        self.assertIn("[EXISTS - reused", out)
        self.assertIn("not exported (not compared)", out)

        # (b) exported and equal: still reused
        os.environ["KYRA_VLLM_ENGINE_KWARGS"] = '{"attention_backend": "FLASH_ATTN"}'
        os.environ["VLLM_BATCH_INVARIANT"] = "1"
        code, out = self.score(run_dir, judges_path, "resumeenv_b", extra=dry)
        self.assertEqual(code, 0, out)
        self.assertIn("[EXISTS - reused", out)

        # (c) exported and different engine kwargs: refused, naming the field
        os.environ["KYRA_VLLM_ENGINE_KWARGS"] = '{"attention_backend": "TRITON_ATTN"}'
        code, out = self.score(run_dir, judges_path, "resumeenv_c", extra=dry)
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertIn("provider_effective_params.engine_kwargs", self.refusal_line(out))

        # (d) exported and different vllm env: refused, naming that field
        os.environ["KYRA_VLLM_ENGINE_KWARGS"] = '{"attention_backend": "FLASH_ATTN"}'
        os.environ["VLLM_BATCH_INVARIANT"] = "0"
        code, out = self.score(run_dir, judges_path, "resumeenv_d", extra=dry)
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertIn("provider_effective_params.vllm_env", self.refusal_line(out))

    # -- 5. a failed sharded attempt: shards archived, the judge runs ---------

    def test_5_stray_shard_files_are_archived_and_the_judge_re_runs(self):
        run_dir = Path(self.runs[5])
        judges_path = self.judges_file(run_dir)
        # a crashed sharded attempt: shard 1 of 2 on disk, no merged judge file
        stray = run_dir / "judge_JF1.shard1of2.jsonl"
        self.make_judge_output(
            run_dir, judges_path, "JF1", extra=["--shard", "1/2", "--out", str(stray)]
        )
        # --out is given twice; the last wins, so confirm where it landed
        self.assertTrue(stray.is_file())
        stray_sha = sha256(stray)
        self.assertFalse((run_dir / "judge_JF1.jsonl").exists())

        code, out = self.score(run_dir, judges_path, "resumeshard", extra=["--resume"])
        self.assertEqual(code, 0, out)
        self.assertIn("archived 1 stray shard file(s) of judge JF1", out)
        self.assertFalse(stray.exists(), "the stray shard must leave the run dir root")
        archived = sorted((run_dir / "shards").glob("failed_*/judge_JF1.shard1of2.jsonl"))
        self.assertEqual(len(archived), 1, sorted(p.name for p in (run_dir / "shards").iterdir()))
        self.assertEqual(sha256(archived[0]), stray_sha, "the evidence is kept verbatim")
        self.assertTrue(
            archived[0].with_name("judge_JF1.shard1of2.meta.json").is_file(),
            "the shard's sidecar goes with it",
        )
        merged = run_dir / "judge_JF1.jsonl"
        self.assertTrue(merged.is_file())
        self.assertEqual(
            len(self.read_jsonl(merged)), campaign.expected_view_count(run_dir)
        )
        record = json.loads(
            one_campaign_record(self.out_root / "resumeshard", "resumeshard", "_scoring")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(
            [r["status"] for r in record["judge_runs"]], ["completed", "completed"]
        )

    # -- 6. without --resume nothing changed ---------------------------------

    def test_6_without_resume_the_existing_refusal_is_unchanged(self):
        run_dir = Path(self.runs[6])
        judges_path = self.judges_file(run_dir)
        j1 = self.make_judge_output(run_dir, judges_path, "JF1")
        before = sha256(j1)
        calls = self.spy_on_judges()

        code, out = self.score(run_dir, judges_path, "resumeoff")
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertIn("judge output already exists, refusing to overwrite", out)
        self.assertIn(str(j1), out)
        self.assertEqual(calls, [])
        self.assertEqual(sha256(j1), before)
        self.assertFalse((run_dir / "judge_JF2.jsonl").exists())
        record = json.loads(
            one_campaign_record(self.out_root / "resumeoff", "resumeoff", "_scoring")
            .read_text(encoding="utf-8")
        )
        self.assertFalse(record["resume"])
        self.assertNotIn("resume", record["plan"])
        self.assertNotIn("resume_judges", record["plan"]["runs"][0])

    def test_5b_a_shard_beside_a_reusable_judge_file_is_refused_by_name(self):
        """An unmerged shard in the run dir ROOT next to a merged judge file is an
        inconsistent state - nobody can tell whether the merge contains it, and
        kyra.analysis.n3_reliability's judge_*.jsonl glob would count it as an
        extra judge. Under <run_dir>/shards/ the same file is the archive a
        finished merge leaves, and the judge is reused."""
        run_dir = Path(self.runs[2])
        judges_path = self.judges_file(run_dir)
        j1 = run_dir / "judge_JF1.jsonl"
        if not j1.is_file():   # test_3 leaves one behind; do not depend on order
            self.make_judge_output(run_dir, judges_path, "JF1")
        before = sha256(j1)
        dry = ["--resume", "--dry-run"]
        stray = run_dir / "judge_JF1.shard1of2.jsonl"
        stray_meta = run_dir / "judge_JF1.shard1of2.meta.json"
        stray.write_text("", encoding="utf-8")
        stray_meta.write_text("{}", encoding="utf-8")
        calls = self.spy_on_judges()

        code, out = self.score(run_dir, judges_path, "resumerootshard", extra=dry)
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        line = self.refusal_line(out)
        self.assertIn(str(stray), line, "the refusal must name the file")
        self.assertIn("judge JF1", line)
        self.assertIn("root_shard_file", line)
        self.assertEqual(calls, [])
        self.assertEqual(sha256(j1), before)
        self.assertTrue(stray.is_file(), "the shard is named, never moved or deleted")

        # the sidecar alone is refused as well
        stray.unlink()
        code, out = self.score(run_dir, judges_path, "resumerootshard2", extra=dry)
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertIn(str(stray_meta), self.refusal_line(out))

        # the very same files under shards/ are the archive of a finished merge
        stray.write_text("", encoding="utf-8")
        archive = run_dir / "shards"
        archive.mkdir(exist_ok=True)
        for path in (stray, stray_meta):
            path.rename(archive / path.name)
        code, out = self.score(run_dir, judges_path, "resumerootshard3", extra=dry)
        self.assertEqual(code, 0, out)
        self.assertIn("[EXISTS - reused", out)
        for path in (stray, stray_meta):
            (archive / path.name).unlink()

    def test_6b_a_stray_shard_without_resume_is_still_refused(self):
        run_dir = Path(self.runs[7])
        judges_path = self.judges_file(run_dir)
        doc = json.loads(judges_path.read_text(encoding="utf-8"))
        for judge in doc["judges"]:
            judge["shards"] = 2
        judges_path.write_text(json.dumps(doc), encoding="utf-8")
        stray = run_dir / "judge_JF1.shard1of2.jsonl"
        self.make_judge_output(
            run_dir, judges_path, "JF1", extra=["--shard", "1/2", "--out", str(stray)]
        )
        code, out = self.score(run_dir, judges_path, "resumeoffshard")
        self.assertEqual(code, campaign.EXIT_PREFLIGHT, out)
        self.assertIn("judge output already exists, refusing to overwrite", out)
        self.assertIn(str(stray), out)
        self.assertTrue(stray.is_file(), "no --resume: the shard is left exactly where it is")


# ==========================================================================
# runner: the condition tag / temperature / seed options the campaign uses
# ==========================================================================
class TestRunnerConditionOptions(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="runner_opts_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.items = load_items(SMOKE_ITEMS)

    def manifest_of(self, run_dir):
        lines = (Path(run_dir) / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def test_free_condition_tag_reaches_the_manifest(self):
        from kyra.providers import MockProvider
        from kyra.runner import execute_run

        run_dir = self.tmp / "repeat_run"
        ok, reasons = execute_run(
            self.items, MockProvider(), ["repeat_2"], run_dir, temperature=0.7
        )
        self.assertTrue(ok, reasons)
        records = self.manifest_of(run_dir)
        self.assertEqual({r["condition"] for r in records}, {"repeat_2"})
        # MockProvider samples nothing, so it still reports temperature 0.0:
        # the provider remains the authority on what was applied.
        self.assertEqual({r["temperature"] for r in records}, {0.0})
        self.assertTrue((run_dir / "MARKER").is_file())

    def test_requested_temperature_is_recorded_when_the_provider_declares_nothing(self):
        from kyra.providers import Provider
        from kyra.runner import execute_run

        class SilentProvider(Provider):
            provider_name = "silent"
            model_id = "silent-v0"
            api_version = "0"

            def generate(self, messages):
                return "ok"

        run_dir = self.tmp / "silent_run"
        ok, reasons = execute_run(
            self.items, SilentProvider(), ["repeat_1"], run_dir, temperature=0.7
        )
        self.assertTrue(ok, reasons)
        records = self.manifest_of(run_dir)
        self.assertEqual({r["temperature"] for r in records}, {0.7})
        self.assertEqual({r["condition"] for r in records}, {"repeat_1"})

    def test_cli_condition_and_conditions_are_mutually_exclusive(self):
        from kyra.runner import EXIT_BAD_INPUT, main as runner_main

        code = runner_main([
            "--items", str(SMOKE_ITEMS), "--provider", "mock",
            "--out-root", str(self.tmp / "x"), "--condition", "repeat_1",
            "--conditions", "base",
        ])
        self.assertEqual(code, EXIT_BAD_INPUT)

    def test_cli_rejects_a_malformed_condition_tag(self):
        from kyra.runner import EXIT_BAD_INPUT, main as runner_main

        code = runner_main([
            "--items", str(SMOKE_ITEMS), "--provider", "mock",
            "--out-root", str(self.tmp / "y"), "--condition", "repeat 1!",
        ])
        self.assertEqual(code, EXIT_BAD_INPUT)

    def test_cli_runs_a_tagged_condition(self):
        from kyra.runner import EXIT_OK, main as runner_main

        out_root = self.tmp / "cli"
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = runner_main([
                "--items", str(SMOKE_ITEMS), "--provider", "mock",
                "--cohort", "tagged", "--out-root", str(out_root),
                "--condition", "repeat_3",
            ])
        self.assertEqual(code, EXIT_OK, buf.getvalue())
        run_dirs = list((out_root / "tagged").iterdir())
        self.assertEqual(len(run_dirs), 1)
        self.assertEqual(
            {r["condition"] for r in self.manifest_of(run_dirs[0])}, {"repeat_3"}
        )

    def test_cli_temperature_seed_reach_the_provider_constructor(self):
        """--temperature/--seed are provider options: a provider that does not
        take them is refused (exit 4), never silently ignored."""
        from kyra.runner import EXIT_BAD_INPUT, main as runner_main, provider_opts_from_args
        from kyra.runner import build_parser

        args = build_parser().parse_args([
            "--items", str(SMOKE_ITEMS), "--temperature", "0.7", "--seed", "20260923",
        ])
        self.assertEqual(
            provider_opts_from_args(args), {"temperature": 0.7, "seed": 20260923}
        )
        code = runner_main([
            "--items", str(SMOKE_ITEMS), "--provider", "mock",
            "--out-root", str(self.tmp / "z"), "--temperature", "0.7",
        ])
        self.assertEqual(code, EXIT_BAD_INPUT)


if __name__ == "__main__":
    unittest.main()
