"""Tests for kyra.items: the phase-A item builder and its fail-closed design gate.

Fixtures under test/fixtures/items/ are synthetic; no authored item text is copied.
Tests run with --tokenizer none (character fallback) so they need no model files;
one test exercises the real local EXAONE tokenizer and is skipped when it cannot load.
"""

from __future__ import annotations

import csv
import io
import json
import contextlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kyra import items as kitems  # noqa: E402
from kyra.schema import load_items  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "items"


def run_build(src, out, strata, expect=("R1",), tokenizer="none"):
    """Run the CLI in-process; return (exit_code, stdout+stderr)."""
    argv = [
        "build",
        "--src", str(src),
        "--out", str(out),
        "--strata", str(strata),
        "--expect-groups", *expect,
        "--tokenizer", tokenizer,
    ]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = kitems.main(argv)
    return code, buf.getvalue()


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kyra_items_test_"))
        self.out = self.tmp / "items.jsonl"
        self.strata = self.tmp / "strata.csv"
        self.addCleanup(shutil.rmtree, self.tmp, True)


class TestRequestCounting(unittest.TestCase):
    def test_question_mark_is_a_request(self):
        self.assertEqual(kitems.count_requests("이거 괜찮아?"), 1)

    def test_korean_request_endings(self):
        for ending in kitems.REQUEST_ENDINGS:
            with self.subTest(ending=ending):
                self.assertEqual(kitems.count_requests("계획 %s." % ending), 1)

    def test_statement_is_not_a_request(self):
        self.assertEqual(kitems.count_requests("오늘은 일찍 잤어."), 0)

    def test_multiple_sentences_counted_separately(self):
        text = "오늘 학교 갔어. 내일 계획 알려줘. 그거 괜찮아?"
        self.assertEqual(kitems.count_requests(text), 2)

    def test_line_breaks_split_sentences(self):
        self.assertEqual(kitems.count_requests("첫 줄 알려줘\n둘째 줄이야"), 1)

    def test_endings_configured_in_one_place(self):
        self.assertEqual(
            tuple(kitems.REQUEST_ENDINGS),
            ("줘", "줘요", "주세요", "줄래", "줄래요", "줄 수 있어", "줄 수 있어요"),
        )

    def test_suffix_match_covers_compound_verbs(self):
        """Verbs ending in one of the suffixes count without being listed."""
        for text in ("내일 계획 알려줘.", "노래 추천해줘.", "숙제 도와줘.", "이유 말해줘.",
                     "계획 짜 주세요.", "한 번만 해 줄래요."):
            with self.subTest(text=text):
                self.assertEqual(kitems.count_requests(text), 1)

    def test_other_verb_endings_are_not_requests(self):
        for text in ("내가 도와줄게.", "내일 알려줄 거야.", "선물 줬어.", "고마워."):
            with self.subTest(text=text):
                self.assertEqual(kitems.count_requests(text), 0)

    def test_trailing_punctuation_is_stripped_before_matching(self):
        self.assertEqual(kitems.count_requests("계획 짜줘!"), 1)
        self.assertEqual(kitems.count_requests("계획 짜줘..."), 1)


class TestValidGroup(TempDirCase):
    def test_build_writes_26_items(self):
        code, log = run_build(FIX / "valid_group.yaml", self.out, self.strata)
        self.assertEqual(code, 0, log)
        self.assertTrue(self.out.is_file(), log)
        loaded = load_items(self.out)
        self.assertEqual(len(loaded), 26, log)

    def test_item_kinds_and_links(self):
        code, log = run_build(FIX / "valid_group.yaml", self.out, self.strata)
        self.assertEqual(code, 0, log)
        by_id = {it.item_id: it for it in load_items(self.out)}
        kinds = {"LOC": 0, "CTRL": 0, "LIT": 0, "BEN": 0}
        for iid in by_id:
            kinds[iid.rsplit("-", 1)[1]] += 1
        self.assertEqual(kinds, {"LOC": 12, "CTRL": 4, "LIT": 6, "BEN": 4}, log)

        s01 = by_id["FX-S01-LOC"]
        self.assertEqual(s01.risk_group, "R1")
        self.assertEqual(s01.turn_type, "single")
        self.assertEqual(s01.localization, "localized")
        self.assertEqual(s01.control_pair_id, "FX-S01-CTRL")
        self.assertIsNone(s01.cue_variant)
        ctrl = by_id["FX-S01-CTRL"]
        self.assertEqual(ctrl.risk_group, "CTRL")
        self.assertEqual(ctrl.control_pair_id, "FX-S01-LOC")
        self.assertEqual(ctrl.age_band, s01.age_band)
        self.assertEqual(ctrl.explicitness, s01.explicitness)

        # single without a contrast carries no control_pair_id
        self.assertIsNone(by_id["FX-S05-LOC"].control_pair_id)

        lit, loc, ben = by_id["FX-M01-LIT"], by_id["FX-M01-LOC"], by_id["FX-M01-BEN"]
        self.assertEqual(lit.localization, "literal")
        self.assertEqual(loc.localization, "localized")
        self.assertEqual(lit.twin_id, "FX-M01-LOC")
        self.assertEqual(loc.twin_id, "FX-M01-LIT")
        self.assertEqual(lit.control_pair_id, "FX-M01-BEN")
        self.assertEqual(loc.control_pair_id, "FX-M01-BEN")
        self.assertEqual(ben.risk_group, "CTRL")
        self.assertEqual(ben.turn_type, "multi")
        self.assertEqual(ben.localization, "localized")
        self.assertEqual(ben.control_pair_id, "FX-M01-LOC")
        self.assertEqual(len(lit.turns), 6)
        self.assertEqual(len(ben.turns), len(loc.turns))

        # non-long-horizon multi: 3 turns, no benign twin
        self.assertEqual(len(by_id["FX-M05-LOC"].turns), 3)
        self.assertIsNone(by_id["FX-M05-LOC"].control_pair_id)
        self.assertNotIn("FX-M05-BEN", by_id)

    def test_stratification_csv(self):
        code, log = run_build(FIX / "valid_group.yaml", self.out, self.strata)
        self.assertEqual(code, 0, log)
        with self.strata.open(encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(tuple(rows[0]), kitems.STRATA_HEADER)
        self.assertEqual(sum(int(r[-1]) for r in rows[1:]), 26)
        self.assertEqual(len(set(tuple(r[:-1]) for r in rows[1:])), len(rows) - 1)

    def test_stratification_has_source_group(self):
        """Contrasts and twins keep their origin group in the source_group column."""
        code, log = run_build(FIX / "valid_group.yaml", self.out, self.strata)
        self.assertEqual(code, 0, log)
        with self.strata.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual({r["source_group"] for r in rows}, {"R1"}, log)
        ctrl = [r for r in rows if r["group"] == "CTRL"]
        self.assertTrue(ctrl, log)
        self.assertEqual({r["source_group"] for r in ctrl}, {"R1"}, log)
        self.assertEqual(sum(int(r["n"]) for r in ctrl), 8, log)  # 4 CTRL + 4 BEN

    def test_jsonl_records_are_schema_clean(self):
        code, log = run_build(FIX / "valid_group.yaml", self.out, self.strata)
        self.assertEqual(code, 0, log)
        for line in self.out.read_text(encoding="utf-8").splitlines():
            obj = json.loads(line)
            self.assertEqual(
                sorted(obj), sorted([
                    "item_id", "risk_group", "turn_type", "turns", "age_band",
                    "explicitness", "localization", "cue_variant", "twin_id",
                    "control_pair_id",
                ])
            )
            self.assertIsNone(obj["cue_variant"])

    def test_character_fallback_prints_warn(self):
        _, log = run_build(FIX / "valid_group.yaml", self.out, self.strata)
        self.assertIn("WARN", log)

    def test_real_tokenizer_path(self):
        tok, warn = kitems.load_tokenizer(kitems.DEFAULT_TOKENIZER, kitems.DEFAULT_HF_HOME)
        if tok is None:
            self.skipTest("local EXAONE tokenizer unavailable: %s" % warn)
        self.assertGreater(kitems.token_length("학교 끝나고 집에 왔어.", tok), 0)
        code, log = run_build(
            FIX / "valid_group.yaml", self.out, self.strata,
            tokenizer=kitems.DEFAULT_TOKENIZER,
        )
        self.assertEqual(code, 0, log)
        self.assertNotIn("WARN", log)
        self.assertEqual(len(load_items(self.out)), 26)


class TestGateFailures(TempDirCase):
    def _assert_gate_fails(self, fixture, needle):
        code, log = run_build(FIX / fixture, self.out, self.strata)
        self.assertEqual(code, 3, log)
        self.assertFalse(self.out.exists(), "output file must not be written")
        self.assertFalse(self.strata.exists(), "strata file must not be written")
        self.assertIn("GATE FAILED", log)
        self.assertIn(needle, log)

    def test_wrong_twin_length(self):
        self._assert_gate_fails("violation_twin_length.yaml", "benign_twin has 5 turns")

    def test_missing_benign_twin(self):
        self._assert_gate_fails("violation_missing_twin.yaml", "no benign_twin")

    def test_request_count_mismatch(self):
        self._assert_gate_fails("violation_request_count.yaml", "information requests differ")

    def test_duplicate_item_id(self):
        self._assert_gate_fails("violation_duplicate_id.yaml", "duplicate source item_id")

    def test_missing_expected_group(self):
        code, log = run_build(FIX / "valid_group.yaml", self.out, self.strata, expect=("R1", "R2"))
        self.assertEqual(code, 3, log)
        self.assertIn("expected group R2 is missing", log)
        self.assertFalse(self.out.exists())

    def test_unlisted_group(self):
        code, log = run_build(FIX / "valid_group.yaml", self.out, self.strata, expect=("R2",))
        self.assertEqual(code, 3, log)
        self.assertIn("not listed in --expect-groups", log)
        self.assertFalse(self.out.exists())

    def test_length_tolerance_violation(self):
        """A benign turn far longer than its risk turn fails the +/-20% rule."""
        import yaml

        doc = yaml.safe_load((FIX / "valid_group.yaml").read_text(encoding="utf-8"))
        doc["multi_turn"][0]["benign_twin"][0] = "나 " * 40
        src = self.tmp / "len_violation.yaml"
        src.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
        code, log = run_build(src, self.out, self.strata)
        self.assertEqual(code, 3, log)
        self.assertIn("outside +/-20%", log)
        self.assertFalse(self.out.exists())

    def test_all_reasons_are_printed(self):
        import yaml

        doc = yaml.safe_load((FIX / "valid_group.yaml").read_text(encoding="utf-8"))
        doc["single_turn"].pop(0)          # 5 singles, 3 lexical contrasts
        doc["multi_turn"][0]["benign_twin"].pop()
        src = self.tmp / "multi_violation.yaml"
        src.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
        code, log = run_build(src, self.out, self.strata)
        self.assertEqual(code, 3, log)
        self.assertIn("expected 6 single_turn items, found 5", log)
        self.assertIn("expected 4 singles with lexical_contrast, found 3", log)
        self.assertIn("benign_twin has 5 turns", log)
        self.assertGreaterEqual(log.count("FAIL"), 3)


class TestBadInput(TempDirCase):
    def test_no_matching_source(self):
        code, log = run_build(self.tmp / "nope_*.yaml", self.out, self.strata)
        self.assertEqual(code, 2, log)

    def test_unparseable_yaml(self):
        src = self.tmp / "broken.yaml"
        src.write_text("group: R1\n  bad: [\n", encoding="utf-8")
        code, log = run_build(src, self.out, self.strata)
        self.assertEqual(code, 2, log)

    def test_missing_top_level_key(self):
        src = self.tmp / "partial.yaml"
        src.write_text("group: R1\nsingle_turn: []\n", encoding="utf-8")
        code, log = run_build(src, self.out, self.strata)
        self.assertEqual(code, 2, log)

    def test_unknown_expect_group(self):
        code, log = run_build(FIX / "valid_group.yaml", self.out, self.strata, expect=("R9",))
        self.assertEqual(code, 2, log)


if __name__ == "__main__":
    unittest.main()
