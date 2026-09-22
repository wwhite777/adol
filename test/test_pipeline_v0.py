"""Wrapper self-tests for KYRA-Bench pipeline v0.

Design doc component 5: known-safe / known-fail / known-critical / timeout /
API-error fixtures must be tested against the very functions the pipeline calls;
an error must never become a silent 0. A 0-item run must terminate abnormally.

Runnable as `python -m unittest discover -s test` from the repo root: the repo's
src/ directory is put on sys.path below so no PYTHONPATH is required.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ITEMS_SMOKE = FIXTURES / "items_smoke.jsonl"

from kyra import manifest as mf  # noqa: E402
from kyra.crri import crri, turn_score  # noqa: E402
from kyra.judge_wrapper import JudgeParseError, parse_judge_output  # noqa: E402
from kyra.providers import FailingProvider, MockProvider, get_provider  # noqa: E402
from kyra.runner import execute_run, main as runner_main  # noqa: E402
from kyra.schema import Item, JudgeRecord, load_items  # noqa: E402


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestCRRI(unittest.TestCase):
    def test_known_value(self):
        # (1*2 + 2*4 + 3*8) / (1+2+3) = 34/6
        self.assertAlmostEqual(crri([2, 4, 8]), 34.0 / 6.0, delta=1e-9)

    def test_single_turn_equals_value(self):
        self.assertAlmostEqual(crri([5]), 5.0, delta=1e-9)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            crri([])

    def test_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            crri([0, 9])
        with self.assertRaises(ValueError):
            crri([-1])

    def test_non_numeric_raises(self):
        with self.assertRaises(ValueError):
            crri([1, "2"])

    def test_turn_score(self):
        self.assertEqual(turn_score({"A1": 2, "A2": 1, "A3": 0, "A4": 2}), 5)
        with self.assertRaises(ValueError):
            turn_score({"A1": 2, "A2": 1, "A3": 0})
        with self.assertRaises(ValueError):
            turn_score({"A1": 3, "A2": 0, "A3": 0, "A4": 0})

    def test_crri_from_judge_record(self):
        rec = parse_judge_output(read_fixture("judge_known_fail.json"))
        r = [turn_score(a) for a in rec.A]
        self.assertEqual(r, [2, 5])
        self.assertAlmostEqual(crri(r), (1 * 2 + 2 * 5) / 3.0, delta=1e-9)


class TestJudgeWrapper(unittest.TestCase):
    def test_known_safe(self):
        rec = parse_judge_output(read_fixture("judge_known_safe.json"))
        self.assertIsInstance(rec, JudgeRecord)
        self.assertEqual(rec.D, {"D1": 2, "D2": 2, "D3": 2, "D4": 2, "D5": 2, "D6": 2})
        self.assertEqual(len(rec.A), 2)
        self.assertFalse(rec.critical_failure)
        self.assertEqual(rec.cf_codes, [])

    def test_known_fail(self):
        rec = parse_judge_output(read_fixture("judge_known_fail.json"))
        self.assertEqual(rec.D["D2"], 0)
        self.assertEqual(rec.D["D4"], 0)
        self.assertFalse(rec.critical_failure)
        self.assertEqual(rec.cf_codes, [])

    def test_known_critical(self):
        rec = parse_judge_output(read_fixture("judge_known_critical.json"))
        self.assertTrue(rec.critical_failure)
        self.assertEqual(rec.cf_codes, ["CF1", "CF4"])
        self.assertEqual(rec.D["D1"], 0)

    def test_malformed_json_raises(self):
        with self.assertRaises(JudgeParseError):
            parse_judge_output(read_fixture("judge_malformed.json"))

    def test_empty_string_raises(self):
        with self.assertRaises(JudgeParseError):
            parse_judge_output("")
        with self.assertRaises(JudgeParseError):
            parse_judge_output("   \n ")
        with self.assertRaises(JudgeParseError):
            parse_judge_output(read_fixture("judge_empty.txt"))

    def test_error_is_never_a_silent_zero(self):
        """Every bad input raises; nothing returns an all-zero JudgeRecord."""
        bad_inputs = [
            "",
            read_fixture("judge_malformed.json"),
            json.dumps({"D": {"D1": 0}, "A": [], "critical_failure": False,
                        "cf_codes": [], "rationale": "x"}),
            json.dumps({"D": {k: 0 for k in
                              ("D1", "D2", "D3", "D4", "D5", "D6")},
                        "A": [{"A1": 0, "A2": 0, "A3": 0, "A4": 0}],
                        "critical_failure": False, "cf_codes": [],
                        "rationale": ""}),
        ]
        for text in bad_inputs:
            with self.subTest(text=text[:40]):
                with self.assertRaises(JudgeParseError):
                    parse_judge_output(text)

    def test_out_of_range_and_missing_fields_raise(self):
        base = json.loads(read_fixture("judge_known_safe.json"))
        bad = json.loads(json.dumps(base))
        bad["D"]["D3"] = 3
        with self.assertRaises(JudgeParseError):
            parse_judge_output(json.dumps(bad))
        bad = json.loads(json.dumps(base))
        del bad["D"]["D5"]
        with self.assertRaises(JudgeParseError):
            parse_judge_output(json.dumps(bad))
        bad = json.loads(json.dumps(base))
        del bad["rationale"]
        with self.assertRaises(JudgeParseError):
            parse_judge_output(json.dumps(bad))
        bad = json.loads(json.dumps(base))
        bad["cf_codes"] = ["CF9"]
        bad["critical_failure"] = True
        with self.assertRaises(JudgeParseError):
            parse_judge_output(json.dumps(bad))
        bad = json.loads(json.dumps(base))
        bad["critical_failure"] = True
        with self.assertRaises(JudgeParseError):
            parse_judge_output(json.dumps(bad))


class TestSchema(unittest.TestCase):
    def test_load_smoke_items(self):
        items = load_items(ITEMS_SMOKE)
        self.assertGreaterEqual(len(items), 6)
        kinds = {it.turn_type for it in items}
        self.assertEqual(kinds, {"single", "multi"})
        for it in items:
            self.assertTrue(it.turns)

    def test_missing_field_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.jsonl"
            p.write_text(json.dumps({"item_id": "X", "risk_group": "R1"}) + "\n",
                         encoding="utf-8")
            with self.assertRaises(ValueError):
                load_items(p)

    def test_invalid_enum_and_turn_count_raise(self):
        good = {
            "item_id": "X1", "risk_group": "R1", "turn_type": "single",
            "turns": ["안녕"], "age_band": "12-14", "explicitness": "explicit",
            "localization": "localized",
        }
        with tempfile.TemporaryDirectory() as d:
            for mutate in (
                lambda o: o.update({"risk_group": "R9"}),
                lambda o: o.update({"age_band": "18-20"}),
                lambda o: o.update({"localization": "korean"}),
                lambda o: o.update({"turn_type": "multi"}),
                lambda o: o.update({"turns": []}),
            ):
                obj = dict(good)
                mutate(obj)
                p = Path(d) / "bad.jsonl"
                p.write_text(json.dumps(obj) + "\n", encoding="utf-8")
                with self.subTest(obj=obj):
                    with self.assertRaises(ValueError):
                        load_items(p)

    def test_empty_file_loads_zero_items(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "empty.jsonl"
            p.write_text("", encoding="utf-8")
            self.assertEqual(load_items(p), [])


class TestMockProvider(unittest.TestCase):
    def test_deterministic(self):
        p = MockProvider()
        msgs = [{"role": "user", "content": "테스트 발화"}]
        self.assertEqual(p.generate(msgs), p.generate(msgs))

    def test_different_utterances_may_differ_but_are_stable(self):
        p, q = MockProvider(), get_provider("mock")
        a = [{"role": "user", "content": "첫 번째"}]
        b = [{"role": "user", "content": "두 번째"}]
        self.assertEqual(p.generate(a), q.generate(a))
        self.assertTrue(p.generate(a).endswith("]"))
        self.assertTrue(p.generate(b).endswith("]"))

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            get_provider("openai")


class TestRunnerAndValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kyra_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_mock_run_produces_marker(self):
        items = load_items(ITEMS_SMOKE)
        run_dir = self.tmp / "mock" / "run1"
        ok, reasons = execute_run(items, MockProvider(), ["base"], run_dir)
        self.assertTrue(ok, reasons)
        self.assertTrue((run_dir / "manifest.jsonl").is_file())
        self.assertTrue((run_dir / "responses.jsonl").is_file())
        self.assertTrue((run_dir / "MARKER").is_file())
        manifest = [json.loads(l) for l in
                    (run_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        responses = [json.loads(l) for l in
                     (run_dir / "responses.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(manifest), len(items))
        self.assertEqual(len(responses), sum(it.n_turns for it in items))
        for rec in manifest:
            self.assertEqual(rec["status"], "ok")
            self.assertEqual(rec["model_id"], "mock-v0")
            self.assertEqual(rec["api_version"], "0")
            self.assertIsNotNone(rec["finished_utc"])

    def test_planted_violation_missing_response_record(self):
        """A run directory with one response record removed must FAIL validation."""
        items = load_items(ITEMS_SMOKE)
        run_dir = self.tmp / "mock" / "run2"
        ok, _ = execute_run(items, MockProvider(), ["base"], run_dir)
        self.assertTrue(ok)
        resp_path = run_dir / "responses.jsonl"
        lines = [l for l in resp_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        # drop the last record of a single-turn item -> whole unit disappears
        single_ids = [it.item_id for it in items if it.turn_type == "single"]
        kept = [l for l in lines if json.loads(l)["item_id"] != single_ids[0]]
        self.assertEqual(len(kept), len(lines) - 1)
        resp_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        ok2, reasons = mf.validate_run(run_dir, len(items), 1,
                                       item_ids=[it.item_id for it in items])
        self.assertFalse(ok2)
        self.assertTrue(any("count mismatch" in r for r in reasons), reasons)
        self.assertTrue(any("response record count mismatch" in r for r in reasons), reasons)

    def test_planted_violation_dropped_turn_inside_multi_item(self):
        items = load_items(ITEMS_SMOKE)
        run_dir = self.tmp / "mock" / "run3"
        ok, _ = execute_run(items, MockProvider(), ["base"], run_dir)
        self.assertTrue(ok)
        resp_path = run_dir / "responses.jsonl"
        lines = [l for l in resp_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        multi_id = [it.item_id for it in items if it.turn_type == "multi"][0]
        dropped = False
        kept = []
        for l in lines:
            rec = json.loads(l)
            if not dropped and rec["item_id"] == multi_id and rec["turn_index"] == 1:
                dropped = True
                continue
            kept.append(l)
        self.assertTrue(dropped)
        resp_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        ok2, reasons = mf.validate_run(run_dir, len(items), 1)
        self.assertFalse(ok2)
        self.assertTrue(any("count mismatch" in r and multi_id in r for r in reasons), reasons)

    def test_marker_not_written_when_validation_fails(self):
        items = load_items(ITEMS_SMOKE)
        run_dir = self.tmp / "mock" / "run4"
        run_dir.mkdir(parents=True)
        # empty run dir: nothing written at all
        ok, reasons = mf.validate_run(run_dir, len(items), 1)
        self.assertFalse(ok)
        self.assertFalse(mf.write_marker(run_dir, len(items), 1))
        self.assertFalse((run_dir / "MARKER").exists())

    def test_provider_error_is_labelled_and_blocks_marker(self):
        """API error / timeout: status=error, no MARKER, runner-level failure."""
        items = load_items(ITEMS_SMOKE)[:2]
        for exc in (TimeoutError("simulated timeout"), RuntimeError("simulated API 500")):
            with self.subTest(exc=type(exc).__name__):
                run_dir = self.tmp / "mock" / ("err_" + type(exc).__name__)
                ok, reasons = execute_run(items, FailingProvider(exc), ["base"], run_dir)
                self.assertFalse(ok)
                self.assertFalse((run_dir / "MARKER").exists())
                manifest = [json.loads(l) for l in
                            (run_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
                            if l.strip()]
                self.assertTrue(all(r["status"] == "error" for r in manifest))
                self.assertTrue(all(r["error_text"] for r in manifest))
                self.assertTrue(any("status=error" in r for r in reasons), reasons)

    def test_item_id_missing_from_outputs_is_reported(self):
        items = load_items(ITEMS_SMOKE)
        run_dir = self.tmp / "mock" / "run5"
        execute_run(items, MockProvider(), ["base"], run_dir)
        ok, reasons = mf.validate_run(run_dir, len(items) + 1, 1,
                                      item_ids=[it.item_id for it in items] + ["GHOST-1"])
        self.assertFalse(ok)
        self.assertTrue(any("GHOST-1" in r for r in reasons), reasons)

    def test_runner_cli_zero_items_exits_nonzero(self):
        empty = self.tmp / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        out_root = self.tmp / "raw"
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = runner_main(["--items", str(empty), "--provider", "mock",
                              "--cohort", "mock", "--out-root", str(out_root)])
        self.assertNotEqual(rc, 0)
        self.assertIn("zero items", err.getvalue())
        self.assertFalse(out_root.exists())

    def test_runner_cli_smoke_run_exits_zero(self):
        out_root = self.tmp / "raw"
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            rc = runner_main(["--items", str(ITEMS_SMOKE), "--provider", "mock",
                              "--cohort", "mock", "--out-root", str(out_root),
                              "--conditions", "base"])
        self.assertEqual(rc, 0)
        runs = list((out_root / "mock").iterdir())
        self.assertEqual(len(runs), 1)
        for name in ("manifest.jsonl", "responses.jsonl", "MARKER"):
            self.assertTrue((runs[0] / name).is_file(), name)
        self.assertIn("MARKER written", out.getvalue())

    def test_runner_cli_bad_provider_and_condition_exit_nonzero(self):
        out_root = self.tmp / "raw2"
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            rc1 = runner_main(["--items", str(ITEMS_SMOKE), "--provider", "gpt-x",
                               "--out-root", str(out_root)])
            rc2 = runner_main(["--items", str(ITEMS_SMOKE), "--conditions", "armB",
                               "--out-root", str(out_root)])
            rc3 = runner_main(["--items", str(self.tmp / "nope.jsonl"),
                               "--out-root", str(out_root)])
        self.assertNotEqual(rc1, 0)
        self.assertNotEqual(rc2, 0)
        self.assertNotEqual(rc3, 0)

    def test_manifest_records_the_mocks_own_params(self):
        """Provenance: the manifest reports what the provider used, not the
        condition table's request (mock samples nothing and caps nothing)."""
        from kyra.runner import CONDITIONS

        items = load_items(ITEMS_SMOKE)
        run_dir = self.tmp / "mock" / "run_params"
        ok, reasons = execute_run(items, MockProvider(), ["base"], run_dir)
        self.assertTrue(ok, reasons)
        manifest = [json.loads(l) for l in
                    (run_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
                    if l.strip()]
        expected = MockProvider().effective_params()
        self.assertEqual(expected["max_tokens"], None)
        for rec in manifest:
            self.assertEqual(rec["max_tokens"], expected["max_tokens"])
            self.assertEqual(rec["temperature"], expected["temperature"])
            self.assertEqual(rec["top_p"], expected["top_p"])
            self.assertNotEqual(rec["max_tokens"], CONDITIONS["base"]["max_tokens"])

    def test_condition_defaults_stand_for_a_provider_declaring_nothing(self):
        from kyra.runner import CONDITIONS, provider_effective_params

        items = load_items(ITEMS_SMOKE)[:1]
        run_dir = self.tmp / "mock" / "run_silent"

        class SilentProvider(MockProvider):
            def effective_params(self):
                return {}

        self.assertEqual(provider_effective_params(SilentProvider()), {})
        ok, reasons = execute_run(items, SilentProvider(), ["base"], run_dir)
        self.assertTrue(ok, reasons)
        rec = json.loads(
            (run_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[0]
        )
        self.assertEqual(rec["max_tokens"], CONDITIONS["base"]["max_tokens"])
        self.assertEqual(rec["temperature"], CONDITIONS["base"]["temperature"])
        self.assertEqual(rec["top_p"], CONDITIONS["base"]["top_p"])

    def test_optional_provenance_fields_are_accepted_required_ones_still_guarded(self):
        """The manifest guard allows the two optional provenance fields only."""
        p = self.tmp / "opt.jsonl"
        rec = {k: None for k in mf.MANIFEST_FIELDS}
        rec["status"] = "ok"
        rec["chat_template_source"] = "tokenizer.chat_template"
        rec["chat_template_sha256"] = "0" * 64
        mf.write_manifest_record(p, rec)
        written = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(written["chat_template_sha256"], "0" * 64)
        with self.assertRaises(ValueError):
            mf.write_manifest_record(p, dict(rec, surprise=1))

    def test_manifest_record_field_guard(self):
        p = self.tmp / "m.jsonl"
        with self.assertRaises(ValueError):
            mf.write_manifest_record(p, {"run_id": "r", "item_id": "i"})
        self.assertFalse(p.exists())


if __name__ == "__main__":
    unittest.main()
