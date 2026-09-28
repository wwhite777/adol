"""Tests for kyra.analysis.posthoc_v1 (POST-HOC sensitivity, not confirmatory).

Synthetic fixtures only (temp dirs); no real run data is read.

Run with:
  cd /home/wjeong/adol && PYTHONPATH=src \
    ~/envs/jeongwoncheol_adol/bin/python -m unittest discover -s test \
    -p "test_posthoc_v1.py" -v
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from kyra import panel as kpanel  # noqa: E402
from kyra.analysis import posthoc_v1 as ph  # noqa: E402

FAM = {"J1": "meta", "J2": "mistral", "J3": "microsoft"}
TRUNC = "JudgeParseError: malformed JSON: Unterminated string starting at: line 2 column 16"
PROV = "ProviderError: ProviderError: vllm generate failed (VLLMValidationError: maximum context length)"
OTHER = "JudgeParseError: cf_codes given but critical_failure=false"


def judge_rec(jid, item_id, depth, flag=None, error=None):
    ok = error is None
    rec = None
    if ok:
        rec = {"D": {k: 1 for k in ("D1", "D2", "D3", "D4", "D5", "D6")},
               "A": [{"A1": 0, "A2": 0, "A3": 0, "A4": 0}] * depth,
               "critical_failure": bool(flag), "cf_codes": ["CF1"] if flag else [],
               "rationale": "x"}
    return {"judge_id": jid, "family": FAM[jid], "item_id": item_id, "condition": "base",
            "depth": depth, "view": "prefix", "is_control": False,
            "status": "ok" if ok else "ERROR", "record": rec, "error": error,
            "prompt_sha256": "0" * 64, "raw_text_sha256": None, "n_turns": depth,
            "attempts": 1, "model_id": "m"}


# item_id -> {judge: flag (bool) or error string}
SPEC = {
    "V1-LOC": {"J1": True, "J2": True, "J3": True},            # 3 valid, unanimous CF
    "V2-LOC": {"J1": True, "J2": True, "J3": False},           # 3 valid, 2-1 CF
    "V3-LOC": {"J1": TRUNC, "J2": True, "J3": False},          # 2 valid, 1-1 -> tie CF
    "V4-LOC": {"J1": True, "J2": PROV, "J3": OTHER},           # 1 valid -> INSUFFICIENT
    "V5-LOC": {"J1": True, "J2": True, "J3": TRUNC},           # 2 valid, 2-0 CF
    "V6-LOC": {"J1": False, "J2": False, "J3": False},         # 3 valid, no CF
}


def build_run(root: Path) -> Path:
    """A run dir whose panel.jsonl is produced by the real kyra.panel.aggregate."""
    run = root / "run"
    run.mkdir(parents=True)
    for jid in ph.JUDGE_IDS:
        rows = []
        for item_id, spec in SPEC.items():
            v = spec[jid]
            if isinstance(v, str):
                rows.append(judge_rec(jid, item_id, 1, error=v))
            else:
                rows.append(judge_rec(jid, item_id, 1, flag=v))
        (run / ("judge_%s.jsonl" % jid)).write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    recs = kpanel.aggregate([str(run / ("judge_%s.jsonl" % j)) for j in ph.JUDGE_IDS],
                            FAM, "alibaba")
    kpanel.write_panel(recs, run / "panel.jsonl")
    (run / "manifest.jsonl").write_text('{"item_id": "V1-LOC"}\n', encoding="utf-8")
    (run / "responses.jsonl").write_text('{"item_id": "V1-LOC"}\n', encoding="utf-8")
    return run


class TestValidityCounts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = build_run(Path(self.tmp.name))
        self.views = ph.load_views(self.run)

    def tearDown(self):
        self.tmp.cleanup()

    def test_classify_error(self):
        self.assertEqual(ph.classify_error(PROV), "provider")
        self.assertEqual(ph.classify_error(TRUNC), "truncated")
        self.assertEqual(ph.classify_error(OTHER), "other_parse")

    def test_counts(self):
        s = [ph.view_summary(v) for v in self.views.values()]
        c = ph.validity_counts(s)
        self.assertEqual(c["n_views"], 6)
        self.assertEqual((c["n_valid3"], c["n_valid2"], c["n_valid_lt2"]), (3, 2, 1))
        self.assertEqual(c["split_2valid_1to1"], 1)
        self.assertEqual(c["split_3valid_not_unanimous"], 1)
        self.assertEqual(c["cf_flags_total"], 4)
        self.assertEqual(c["cf_from_complete_3valid"], 2)
        self.assertEqual(c["cf_from_tie_rule"], 1)
        self.assertEqual(c["cf_from_2valid_unanimous"], 1)
        self.assertEqual((c["J1_err_truncated"], c["J1_err_total"]), (1, 1))
        self.assertEqual((c["J2_err_provider"], c["J2_err_total"]), (1, 1))
        self.assertEqual((c["J3_err_other_parse"], c["J3_err_truncated"], c["J3_err_total"]),
                         (1, 1, 2))

    def test_consistency_detects_tampered_flag(self):
        views = list(self.views.values())
        s = [ph.view_summary(v) for v in views]
        self.assertEqual(ph.consistency(s, views),
                         {"views_valid_count_ne_panel_judges_used": 0,
                          "views_panel_flag_ne_recomputed_majority": 0})
        views[0]["panel"] = dict(views[0]["panel"], critical_failure=False)
        self.assertEqual(ph.consistency(s, views)["views_panel_flag_ne_recomputed_majority"], 1)


class TestRelabel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = build_run(Path(self.tmp.name))
        self.views = {k[0]: v for k, v in ph.load_views(self.run).items()}

    def tearDown(self):
        self.tmp.cleanup()

    def test_tie_view(self):
        v = self.views["V3-LOC"]
        self.assertTrue(v["panel"]["cf_tie"])
        self.assertTrue(v["panel"]["critical_failure"])
        self.assertEqual(ph.relabel(v, "S0"), v["panel"])
        self.assertEqual(ph.relabel(v, "S1")["status"], "INSUFFICIENT")
        self.assertEqual(ph.relabel(v, "S2")["status"], "INSUFFICIENT")
        s3 = ph.relabel(v, "S3")
        self.assertEqual(s3["status"], "ok")
        self.assertIs(s3["critical_failure"], False)

    def test_non_tie_views(self):
        two_one = self.views["V2-LOC"]          # 3 valid, 2-1 true
        for sch in ("S1", "S2", "S3"):
            r = ph.relabel(two_one, sch)
            self.assertEqual(r["status"], "ok")
            self.assertIs(r["critical_failure"], True)
        two_zero = self.views["V5-LOC"]         # 2 valid, both true
        self.assertEqual(ph.relabel(two_zero, "S1")["status"], "INSUFFICIENT")
        self.assertIs(ph.relabel(two_zero, "S2")["critical_failure"], True)
        self.assertIs(ph.relabel(two_zero, "S3")["critical_failure"], True)
        insuff = self.views["V4-LOC"]
        for sch in ph.SCHEMES:
            self.assertEqual(ph.relabel(insuff, sch)["status"], "INSUFFICIENT")

    def test_majority_strict(self):
        self.assertFalse(ph.majority_strict([True, False]))
        self.assertTrue(ph.majority_strict([True, True, False]))
        self.assertFalse(ph.majority_strict([True, False, False]))

    def test_written_runs(self):
        before = hashlib.sha256((self.run / "panel.jsonl").read_bytes()).hexdigest()
        out = Path(self.tmp.name) / "b_runs"
        runs, panels, changes = ph.write_relabeled_runs([str(self.run)], "S3", out)
        self.assertEqual(changes, {"views": 6, "dropped": 0, "cf_true_to_false": 1})
        d = Path(runs[0])
        for name in ("manifest.jsonl", "responses.jsonl"):
            self.assertTrue(os.path.islink(d / name))
            self.assertEqual((d / name).resolve(), (self.run / name).resolve())
        recs = [json.loads(x) for x in Path(panels[0]).read_text().splitlines()]
        for r in recs:
            kpanel.check_panel_record(r)
        self.assertIs({r["item_id"]: r for r in recs}["V3-LOC"]["critical_failure"], False)
        after = hashlib.sha256((self.run / "panel.jsonl").read_bytes()).hexdigest()
        self.assertEqual(before, after)
        _, _, ch2 = ph.write_relabeled_runs([str(self.run)], "S2", out)
        self.assertEqual(ch2, {"views": 6, "dropped": 1, "cf_true_to_false": 0})

    def test_crude_or(self):
        self.assertEqual(ph.crude_or(14, 120, 34, 120), (34 / 86) / (14 / 106))
        self.assertIsNone(ph.crude_or(0, 120, 4, 120))


def long_df(rows):
    """rows: (subject, judge, flag, D value) -> the n3 long table."""
    out = []
    for subj, jid, flag, dval in rows:
        r = {"conversation_id": subj, "judge_id": jid, "family": FAM[jid],
             "critical_failure": int(flag)}
        for k in ("D1", "D2", "D3", "D4", "D5", "D6"):
            r[k] = dval
        out.append(r)
    return pd.DataFrame(out)


class TestClusterBootstrap(unittest.TestCase):
    def test_cluster_of(self):
        self.assertEqual(ph.cluster_of("/a/run|R1-M01-LOC|base|6"), "/a/run|R1-M01-LOC|base")

    def test_identical_judges(self):
        rows = []
        for c in range(6):
            for depth in (1, 3, 6):
                subj = "run|I%d-LOC|base|%d" % (c, depth)
                for jid in ph.JUDGE_IDS:
                    rows.append((subj, jid, (c + depth) % 2, (c + depth) % 3))
        res = ph.cluster_bootstrap_agreement(long_df(rows), B=200, seed=1)
        self.assertEqual((res["n_views"], res["n_clusters"]), (18, 6))
        for dim in ("D1", "D2", "D3", "D4", "D5", "D6"):
            p = res["per_dimension"][dim]
            self.assertAlmostEqual(p["ac2"], 1.0, places=12)
            self.assertAlmostEqual(p["ci95_cluster"][0], 1.0, places=12)
            self.assertAlmostEqual(p["ci95_cluster"][1], 1.0, places=12)
        cf = res["cf_flag"]
        self.assertEqual(cf["mean_pairwise_agreement"], 1.0)
        self.assertEqual(cf["positive_specific_agreement_PA"], 1.0)
        self.assertEqual(cf["negative_specific_agreement_NA"], 1.0)

    def test_pa_na_hand_example(self):
        # s1 [1,1,1]: a=3; s2 [1,0,0]: b+c=2, d=1; s3 [0,0]: d=1 -> a=3, bc=2, d=2
        rows = [("r|s1|c|1", "J1", 1, 1), ("r|s1|c|1", "J2", 1, 1), ("r|s1|c|1", "J3", 1, 1),
                ("r|s2|c|1", "J1", 1, 2), ("r|s2|c|1", "J2", 0, 2), ("r|s2|c|1", "J3", 0, 2),
                ("r|s3|c|1", "J1", 0, 0), ("r|s3|c|1", "J2", 0, 0)]
        self.assertEqual(ph.pair_counts([1, 1, 1]), (3, 0, 0))
        self.assertEqual(ph.pair_counts([1, 0, 0]), (0, 2, 1))
        self.assertEqual(ph.pair_counts([0, 0]), (0, 0, 1))
        res = ph.cluster_bootstrap_agreement(long_df(rows), B=50, seed=2)
        cf = res["cf_flag"]
        self.assertEqual(cf["pairs_pooled"], {"a_both_true": 3, "b_plus_c_discordant": 2,
                                              "d_both_false": 2})
        self.assertAlmostEqual(cf["positive_specific_agreement_PA"], 0.75, places=12)
        self.assertAlmostEqual(cf["negative_specific_agreement_NA"], 4 / 6, places=12)
        self.assertAlmostEqual(cf["mean_pairwise_agreement"], (1 + 1 / 3 + 1) / 3, places=12)
        self.assertEqual(cf["views_by_n_judges_flagging"],
                         {"flagged_by_3": 1, "flagged_by_1": 1, "flagged_by_0": 1})

    def test_views_of_one_conversation_move_together(self):
        # One conversation, two views that disagree differently: a VIEW bootstrap
        # would vary, a CONVERSATION bootstrap always redraws the same cluster.
        rows = [("r|x|c|1", "J1", 1, 0), ("r|x|c|1", "J2", 1, 1), ("r|x|c|1", "J3", 1, 2),
                ("r|x|c|6", "J1", 1, 2), ("r|x|c|6", "J2", 0, 2), ("r|x|c|6", "J3", 0, 2)]
        res = ph.cluster_bootstrap_agreement(long_df(rows), B=100, seed=3)
        cf = res["cf_flag"]
        pt = cf["mean_pairwise_agreement"]
        self.assertEqual(cf["mean_pairwise_agreement_ci95_cluster"], [pt, pt])
        d1 = res["per_dimension"]["D1"]
        self.assertEqual(d1["ci95_cluster"], [d1["ac2"], d1["ac2"]])


if __name__ == "__main__":
    unittest.main()
