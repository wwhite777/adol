"""Multi-run regression tests for the phase-A analysis inputs (2026-09-26).

Bug fixed: kyra.analysis.loader.build_tidy keyed manifest entries and panel
records by (item_id, condition) only, so several run dirs (five models, each
with main + repeat runs) collided ("duplicate prefix depths [1, 1, 1, 1, 1]").
kyra.analysis.n3_reliability keyed its subjects by "item_id|condition", which
pooled every model, run and prefix depth into one subject.

Synthetic fixtures only (built in a temp dir); no real run data is read.

Run with:
  cd /home/wjeong/adol && PYTHONPATH=src \
    ~/envs/jeongwoncheol_adol/bin/python -m unittest discover -s test \
    -p "test_analysis_multirun.py" -v
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
sys.path.insert(0, str(SRC))

from kyra.analysis import loader  # noqa: E402
from kyra.analysis import n1_escalation, n2_localization, pareto, transitions  # noqa: E402
from kyra.analysis import n3_reliability as n3  # noqa: E402

N_SCEN = 10
DEPTHS = (1, 3, 6)
B_SMALL = 30


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _item_ids():
    out = []
    for s in range(1, N_SCEN + 1):
        base = "R1-S%02d" % s
        out += [base + "-LOC", base + "-LIT", base + "-BEN"]
    return out


def write_items(path: Path):
    rows = []
    for s in range(1, N_SCEN + 1):
        base = "R1-S%02d" % s
        common = {"age_band": "12-14", "explicitness": "explicit", "turn_type": "multi",
                  "turns": ["t1", "t2", "t3", "t4", "t5", "t6"], "cue_variant": None}
        rows.append(dict(common, item_id=base + "-LOC", risk_group="R1",
                         localization="localized", twin_id=base + "-LIT",
                         control_pair_id=base + "-BEN"))
        rows.append(dict(common, item_id=base + "-LIT", risk_group="R1",
                         localization="literal", twin_id=base + "-LOC",
                         control_pair_id=None))
        rows.append(dict(common, item_id=base + "-BEN", risk_group="CTRL",
                         localization="localized", twin_id=None,
                         control_pair_id=base + "-LOC"))
    _write_jsonl(path, rows)


def write_run(run_dir: Path, model_id: str, seed: int):
    """One run dir: manifest, responses, prefix-view panel (depths 1, 3, 6)."""
    rng = np.random.default_rng(seed)
    manifest, responses, panel = [], [], []
    for item_id in _item_ids():
        ben = item_id.endswith("-BEN")
        manifest.append({"condition": "base", "item_id": item_id, "model_id": model_id,
                         "n_turns": 6, "status": "ok"})
        responses.append({"condition": "base", "item_id": item_id, "model_text": "r",
                          "turn_index": 0, "user_text": "t1"})
        probs = (0.05, 0.1, 0.15) if ben else (0.15, 0.4, 0.6)
        for d, pr in zip(DEPTHS, probs):
            crit = bool(rng.random() < pr)
            panel.append({
                "item_id": item_id, "condition": "base", "depth": d, "status": "ok",
                "D": {"D1": 2, "D2": 2, "D3": 2, "D4": 2, "D5": 2, "D6": 2},
                "A": [{"A1": 1, "A2": 0, "A3": 0, "A4": 0} for _ in range(d)],
                "critical_failure": crit, "cf_codes": ["CF3"] if crit else [],
                "n_turns": d, "evaluated_family": model_id,
                "over_refusal": (bool(rng.random() < 0.3) if ben else None),
                "helpfulness": (2 if ben else None),
            })
    _write_jsonl(run_dir / "manifest.jsonl", manifest)
    _write_jsonl(run_dir / "responses.jsonl", responses)
    _write_jsonl(run_dir / "panel.jsonl", panel)
    return run_dir


class MultiRunFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="kyra_multirun_"))
        cls.items = cls.tmp / "items.jsonl"
        write_items(cls.items)
        raw = cls.tmp / "raw"
        cls.a_main = write_run(raw / "model_A" / "main" / "r1", "model_A", 1)
        cls.b_main = write_run(raw / "model_B" / "main" / "r2", "model_B", 2)
        cls.a_rep = write_run(raw / "model_A" / "repeat_1" / "r3", "model_A", 3)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def mains(self):
        runs = [self.a_main, self.b_main]
        return runs, [r / "panel.jsonl" for r in runs]


class TestLoaderMultiRun(MultiRunFixture):
    def test_one_row_per_run_and_item(self):
        runs, panels = self.mains()
        df = loader.build_tidy(self.items, runs, panels)
        n_items = 3 * N_SCEN
        self.assertEqual(len(df), 2 * n_items)
        self.assertEqual(int(df.groupby(["run_dir", "item_id"]).size().max()), 1)
        self.assertEqual(sorted(df["run_dir"].unique()), sorted(str(r) for r in runs))
        self.assertEqual(set(df["view_depths"]), {"1;3;6"})
        self.assertEqual(
            dict(df.groupby("model_id")["run_dir"].first()),
            {"model_A": str(self.a_main), "model_B": str(self.b_main)})

    def test_relative_run_and_absolute_panel_match(self):
        runs, panels = self.mains()
        rel = [os.path.relpath(str(r)) for r in runs]
        df = loader.build_tidy(self.items, rel, [p.resolve() for p in panels])
        self.assertEqual(len(df), 2 * 3 * N_SCEN)
        self.assertEqual(sorted(df["run_dir"].unique()), sorted(rel))

    def test_panel_outside_the_runs_raises(self):
        with self.assertRaisesRegex(ValueError, "not inside any of the given run dirs"):
            loader.build_tidy(self.items, [self.a_main, self.b_main],
                              [self.a_main / "panel.jsonl", self.a_rep / "panel.jsonl"])

    def test_same_run_dir_twice_raises(self):
        with self.assertRaisesRegex(ValueError, "run directory given twice"):
            loader.build_tidy(self.items, [self.a_main, os.path.relpath(str(self.a_main))],
                              [self.a_main / "panel.jsonl"])

    def test_n1_and_descriptives_run_on_the_multi_run_table(self):
        runs, panels = self.mains()
        df = loader.build_tidy(self.items, runs, panels)
        res = n1_escalation.analyse(df, B=B_SMALL, seed=7)
        self.assertEqual(res["counts"]["models"], 2)
        self.assertEqual(res["counts"]["loc_conversations"], 2 * N_SCEN)
        self.assertEqual(res["risk"]["n_rows"], 2 * 2 * N_SCEN)   # (conv x depth 1, 6)
        r2 = n2_localization.analyse(df, B=B_SMALL, seed=7)
        self.assertEqual(r2["n_pairs"], 2 * N_SCEN)
        tr = transitions.analyse(df)
        self.assertEqual(tr["overall"]["n_with_per_turn_series"], 2 * 3 * N_SCEN)
        pa = pareto.analyse(df, B=B_SMALL, seed=7)
        self.assertEqual([m["n_risk"] for m in pa["by_model"]], [2 * N_SCEN, 2 * N_SCEN])

    def test_two_runs_of_one_model_are_refused(self):
        runs = [self.a_main, self.a_rep]
        df = loader.build_tidy(self.items, runs, [r / "panel.jsonl" for r in runs])
        self.assertEqual(len(df), 2 * 3 * N_SCEN)
        for name, fn in (
            ("n1", lambda: n1_escalation.analyse(df, B=B_SMALL)),
            ("n2", lambda: n2_localization.analyse(df, B=B_SMALL)),
            ("transitions", lambda: transitions.analyse(df)),
            ("pareto", lambda: pareto.analyse(df, B=B_SMALL)),
        ):
            with self.subTest(module=name):
                with self.assertRaisesRegex(ValueError, "more than one run dir"):
                    fn()

    def test_n1_cli_exits_nonzero_on_two_runs_of_one_model(self):
        out = self.tmp / "n1_same_model.json"
        env = dict(os.environ, PYTHONPATH=str(SRC))
        runs = [self.a_main, self.a_rep]
        proc = subprocess.run(
            [sys.executable, "-m", "kyra.analysis.n1_escalation", "--items", str(self.items),
             "--runs"] + [str(r) for r in runs]
            + ["--panels"] + [str(r / "panel.jsonl") for r in runs]
            + ["--bootstrap", str(B_SMALL), "--out", str(out)],
            cwd=str(REPO), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, loader.EXIT_BAD_INPUT, proc.stderr)
        self.assertIn("more than one run dir", proc.stderr)
        self.assertFalse(out.exists())

    def test_single_run_input_unchanged(self):
        df = loader.build_tidy(self.items, [self.a_main], [self.a_main / "panel.jsonl"])
        self.assertEqual(len(df), 3 * N_SCEN)
        self.assertEqual(set(df["run_dir"]), {str(self.a_main)})


# -- N3 subjects ---------------------------------------------------------------

JUDGES = (("J1", "famX"), ("J2", "famY"), ("J3", "famZ"))
RISK_ITEMS = ("R1-S01-LOC", "R1-S01-LIT", "R1-S02-LOC", "R1-S02-LIT")
CTRL_ITEMS = ("R1-S01-BEN", "R1-S02-BEN")


def write_judge_files(run_dir: Path, seed: int):
    """judge_J*.jsonl for one run dir; the same item ids and depths in every run."""
    rng = np.random.default_rng(seed)
    run_dir.mkdir(parents=True, exist_ok=True)
    truth = {}
    for jid, fam in JUDGES:
        rows = []
        for item_id in RISK_ITEMS + CTRL_ITEMS:
            for d in DEPTHS:
                D = {"D%d" % k: int(rng.integers(0, 3)) for k in range(1, 7)}
                crit = bool(rng.random() < 0.3)
                rows.append({"judge_id": jid, "family": fam, "item_id": item_id,
                             "condition": "base", "depth": d, "view": "prefix",
                             "is_control": item_id in CTRL_ITEMS, "status": "ok",
                             "record": {"D": D, "critical_failure": crit}})
                if item_id not in CTRL_ITEMS:
                    truth.setdefault((str(run_dir), item_id, "base", d), {})[jid] = (D, crit, fam)
        _write_jsonl(run_dir / ("judge_%s.jsonl" % jid), rows)
    return truth


class TestN3Subjects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="kyra_n3_multirun_"))
        cls.run_a = cls.tmp / "model_A" / "main" / "r1"
        cls.run_b = cls.tmp / "model_B" / "main" / "r2"
        cls.truth = {}
        cls.truth.update(write_judge_files(cls.run_a, 11))
        cls.truth.update(write_judge_files(cls.run_b, 12))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def files(self):
        return [str(r / ("judge_%s.jsonl" % j)) for r in (self.run_a, self.run_b)
                for j, _ in JUDGES]

    def test_subject_is_the_judged_view_and_controls_are_excluded(self):
        df = n3.long_from_judge_files(self.files())
        n_views = 2 * len(RISK_ITEMS) * len(DEPTHS)
        self.assertEqual(df["conversation_id"].nunique(), n_views)
        self.assertEqual(len(df), n_views * len(JUDGES))
        self.assertEqual(int(df.groupby(["conversation_id", "judge_id"]).size().max()), 1)
        res = n3.analyse(df, B=50, seed=5)
        self.assertEqual(res["n_subjects"], n_views)
        for dim in ("D1", "D2", "D3", "D4", "D5", "D6"):
            self.assertEqual(res["per_dimension"][dim]["n_subjects"], n_views)
        self.assertEqual(res["n_control_views_excluded"], 2 * len(CTRL_ITEMS) * len(DEPTHS))
        self.assertEqual(res["n_control_records_excluded"],
                         2 * len(CTRL_ITEMS) * len(DEPTHS) * len(JUDGES))
        self.assertEqual(res["subject_unit"],
                         "judged view (run_dir, item_id, condition, depth); "
                         "control views excluded")

    def test_ac2_and_lofo_match_an_independent_subject_table(self):
        df = n3.long_from_judge_files(self.files())
        res = n3.analyse(df, B=50, seed=5)
        subj = {k: [v[j][0]["D1"] for j, _ in JUDGES] for k, v in self.truth.items()}
        self.assertAlmostEqual(res["per_dimension"]["D1"]["ac2"],
                               n3.ac2(subj)["ac2"], places=12)
        drop = {e["dropped_family"]: e for e in res["leave_one_family_out"]}
        kept = {k: [v[j][0]["D1"] for j, f in JUDGES if f != "famX"]
                for k, v in self.truth.items()}
        self.assertAlmostEqual(drop["famX"]["per_dimension"]["D1"]["ac2"],
                               n3.ac2(kept)["ac2"], places=12)

    def test_a_judge_rating_one_view_twice_raises(self):
        bad = self.tmp / "dup" / "judge_J1.jsonl"
        src = (self.run_a / "judge_J1.jsonl").read_text(encoding="utf-8")
        first = src.splitlines()[0]
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text(src + first + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "rated the same judged view twice"):
            n3.long_from_judge_files([str(bad)])

    def test_the_same_judge_file_twice_is_refused_by_the_cli(self):
        out = self.tmp / "n3_twice.json"
        env = dict(os.environ, PYTHONPATH=str(SRC))
        proc = subprocess.run(
            [sys.executable, "-m", "kyra.analysis.n3_reliability",
             "--judges"] + self.files() + ["--runs", str(self.run_a), str(self.run_b),
                                           "--bootstrap", "50", "--out", str(out)],
            cwd=str(REPO), env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, loader.EXIT_BAD_INPUT, proc.stderr)
        self.assertIn("given more than once", proc.stderr)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
