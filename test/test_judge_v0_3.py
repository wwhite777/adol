"""Self-tests for judge prompt v0.3 (the protocol's one in-scoring revision).

What v0.3 changed (DECISION_LOG 2026-09-23 "JUDGE PROMPT REVISION v0.2 -> v0.3",
format compliance only - no rubric, dimension, anchor, manual excerpt, CF code or
threshold text changed):

  1. the format example is rendered with exactly this view's turn count (v0.2's
     fixed two-object `A` was copied by Llama-3.1-8B on 145/156 depth-1 views);
  2. the item type and its key obligation are stated unconditionally per view type
     (v0.2's schema rule 7 cross-referenced section 5, and Mistral-Small-24B
     omitted over_refusal/helpfulness on 106/106 control views);
  3. a rationale that reproduces the example is a parse error, never a score;
  4. ERROR records keep the raw judge text, so a failure stays diagnosable.

Runnable as `PYTHONPATH=src:test python -m unittest test_judge_v0_3`; src/ is put
on sys.path below as in test_judge.py.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = Path(__file__).resolve().parent / "fixtures"

from kyra.analysis import n3_reliability  # noqa: E402
from kyra.judge import (  # noqa: E402
    CONTROL_RULES_TEXT,
    DEFAULT_MANUAL_PATH,
    PROMPT_PATH,
    RISK_RULES_TEXT,
    RULE_CONTROL_CONTROL,
    RULE_CONTROL_RISK,
    RULE_KEYS_CONTROL,
    RULE_KEYS_RISK,
    VIEW_PREFIX,
    VIEW_TYPE_HEADER_CONTROL,
    VIEW_TYPE_HEADER_RISK,
    FakeJudgeProvider,
    build_judge_prompt,
    check_record_fail_closed,
    example_a_turns,
    judge_run,
    load_manual_text,
    main as judge_main,
    make_judge_record,
    meta_path_for,
    render_example_json,
    retry_reminder,
    write_judge_record,
)
from kyra.judge_wrapper import (  # noqa: E402
    EXAMPLE_RATIONALE,
    JudgeParseError,
    parse_judge_output,
)
from kyra.panel import aggregate, load_judge_file  # noqa: E402
from kyra.schema import A_KEYS  # noqa: E402

# The superseded v0.2 template stays on disk for the record and must not change.
V0_2_PATH = SRC / "kyra" / "judge_prompt_v0.md"
V0_2_SHA256 = "d897ea21d94b68a5af1fa021995445cead7c47384e43b8618c7e5c27a6dfc080"

VALID_1T = (FIXTURES / "judge_fake_valid_1turn.json").read_text(encoding="utf-8")
VALID_2T = (FIXTURES / "judge_fake_valid_2turn.json").read_text(encoding="utf-8")
CONTROL_1T = (FIXTURES / "judge_fake_control_1turn.json").read_text(encoding="utf-8")

CONV = [
    {"user_text": "u1", "model_text": "m1"},
    {"user_text": "u2", "model_text": "m2"},
    {"user_text": "u3", "model_text": "m3"},
    {"user_text": "u4", "model_text": "m4"},
    {"user_text": "u5", "model_text": "m5"},
    {"user_text": "u6", "model_text": "m6"},
]


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def schema_block(system: str) -> str:
    start = system.index("```json")
    block = system[start + len("```json"):]
    return block[: block.index("```")]


def copied_output(rationale=EXAMPLE_RATIONALE, n_turns: int = 1) -> str:
    """A judge output that is valid except that it reuses the example rationale."""
    return json.dumps(
        {
            "rationale": rationale,
            "D": {"D1": 2, "D2": 2, "D3": 2, "D4": 1, "D5": 2, "D6": 2},
            "A": [{"A1": 0, "A2": 0, "A3": 1, "A4": 0}] * n_turns,
            "critical_failure": False,
            "cf_codes": [],
        },
        ensure_ascii=False,
    )


def write_run_dir(root: Path, conversations) -> Path:
    run_dir = Path(root)
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "responses.jsonl").open("w", encoding="utf-8") as fh:
        for item_id, condition, turns in conversations:
            for i, (u, m) in enumerate(turns):
                fh.write(
                    json.dumps(
                        {
                            "item_id": item_id,
                            "condition": condition,
                            "turn_index": i,
                            "user_text": u,
                            "model_text": m,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    return run_dir


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kyra_judge_v03_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# -- template files -----------------------------------------------------------


class TestTemplateFiles(unittest.TestCase):
    def test_v0_2_template_is_untouched(self):
        self.assertEqual(sha256_file(V0_2_PATH), V0_2_SHA256)

    def test_default_template_is_v0_3(self):
        self.assertEqual(PROMPT_PATH.name, "judge_prompt_v0_3.md")
        self.assertTrue(PROMPT_PATH.is_file())

    def test_v0_3_template_has_the_v0_3_slots_and_no_schema_extra(self):
        text = PROMPT_PATH.read_text(encoding="utf-8")
        for slot in ("{{VIEW_TYPE_HEADER}}", "{{EXAMPLE_JSON}}", "{{RULE_KEYS}}",
                     "{{RULE_CONTROL}}", "{{MANUAL_EXCERPT}}", "{{N_TURNS}}",
                     "{{CONTROL_RULES}}", "{{ANCHOR_SAFE}}", "{{ANCHOR_FAIL}}"):
            self.assertIn(slot, text, "v0.3 template is missing %s" % slot)
        self.assertNotIn("{{SCHEMA_EXTRA}}", text)


# -- rendering ----------------------------------------------------------------


class TestExampleRendering(unittest.TestCase):
    def _system(self, n_turns: int, is_control: bool) -> str:
        return build_judge_prompt(
            CONV[:n_turns], "", [], is_control=is_control
        )[0]["content"]

    def test_example_a_has_exactly_n_turns_objects(self):
        for n_turns in (1, 2, 6):
            for is_control in (False, True):
                with self.subTest(n_turns=n_turns, is_control=is_control):
                    block = schema_block(self._system(n_turns, is_control))
                    obj = json.loads(block)  # the example block is valid JSON
                    self.assertEqual(len(obj["A"]), n_turns)
                    for turn in obj["A"]:
                        self.assertEqual(sorted(turn), sorted(A_KEYS))
                        self.assertTrue(
                            any(turn[k] != 0 for k in A_KEYS),
                            "example turn is degenerate (all zero): %r" % turn,
                        )

    def test_example_block_is_schema_valid_once_the_rationale_is_replaced(self):
        for n_turns in (1, 2, 6):
            for is_control in (False, True):
                with self.subTest(n_turns=n_turns, is_control=is_control):
                    block = schema_block(self._system(n_turns, is_control))
                    real = block.replace(EXAMPLE_RATIONALE, "실제로 관찰된 근거 문장.")
                    rec = parse_judge_output(real, is_control=is_control)
                    self.assertEqual(len(rec.A), n_turns)

    def test_no_unfilled_slots(self):
        for n_turns in (1, 2, 6):
            for is_control in (False, True):
                with self.subTest(n_turns=n_turns, is_control=is_control):
                    system = self._system(n_turns, is_control)
                    self.assertNotIn("{{", system)
                    self.assertNotIn("}}", system)

    def test_control_view_states_seven_keys_and_the_control_header(self):
        system = self._system(2, True)
        self.assertIn(VIEW_TYPE_HEADER_CONTROL, system)
        self.assertNotIn(VIEW_TYPE_HEADER_RISK, system)
        self.assertIn(RULE_KEYS_CONTROL, system)
        self.assertNotIn(RULE_KEYS_RISK, system)
        self.assertIn(RULE_CONTROL_CONTROL, system)
        self.assertNotIn(RULE_CONTROL_RISK, system)
        self.assertIn(CONTROL_RULES_TEXT, system)
        obj = json.loads(schema_block(system))
        self.assertIn("over_refusal", obj)
        self.assertIn("helpfulness", obj)

    def test_risk_view_states_five_keys_and_the_risk_header(self):
        system = self._system(2, False)
        self.assertIn(VIEW_TYPE_HEADER_RISK, system)
        self.assertNotIn(VIEW_TYPE_HEADER_CONTROL, system)
        self.assertIn(RULE_KEYS_RISK, system)
        self.assertNotIn(RULE_KEYS_CONTROL, system)
        self.assertIn(RULE_CONTROL_RISK, system)
        self.assertNotIn(RULE_CONTROL_CONTROL, system)
        self.assertIn(RISK_RULES_TEXT, system)
        obj = json.loads(schema_block(system))
        self.assertNotIn("over_refusal", obj)
        self.assertNotIn("helpfulness", obj)

    def test_example_turns_cycle_and_reject_a_bad_length(self):
        self.assertEqual(len(example_a_turns(7)), 7)
        self.assertEqual(example_a_turns(7)[6], example_a_turns(1)[0])
        for bad in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                example_a_turns(bad)

    def test_rendered_example_is_fenced_json(self):
        block = render_example_json(3, is_control=True)
        self.assertTrue(block.startswith("```json\n{"))
        self.assertTrue(block.endswith("}\n```"))


# -- the copied-example guard -------------------------------------------------


class TestCopiedRationaleGuard(unittest.TestCase):
    def test_exact_example_rationale_is_a_parse_error(self):
        with self.assertRaises(JudgeParseError) as ctx:
            parse_judge_output(copied_output())
        self.assertIn("copied from the example", str(ctx.exception))

    def test_whitespace_variant_is_a_parse_error(self):
        noisy = "  " + EXAMPLE_RATIONALE.replace(" ", "\n  ") + " "
        with self.assertRaises(JudgeParseError) as ctx:
            parse_judge_output(copied_output(rationale=noisy))
        self.assertIn("copied from the example", str(ctx.exception))

    def test_paraphrase_containing_the_marker_is_a_parse_error(self):
        with self.assertRaises(JudgeParseError) as ctx:
            parse_judge_output(copied_output(rationale="예시 근거 문장을 그대로 씁니다."))
        self.assertIn("copied from the example", str(ctx.exception))

    def test_a_real_rationale_still_parses(self):
        rec = parse_judge_output(copied_output(rationale="AI가 1388을 정확히 안내함."))
        self.assertEqual(rec.rationale, "AI가 1388을 정확히 안내함.")

    def test_guard_also_applies_to_control_records(self):
        obj = json.loads(CONTROL_1T)
        obj["rationale"] = EXAMPLE_RATIONALE
        with self.assertRaises(JudgeParseError) as ctx:
            parse_judge_output(json.dumps(obj, ensure_ascii=False), is_control=True)
        self.assertIn("copied from the example", str(ctx.exception))


class TestCopiedRationaleInARun(TempDirTest):
    def _run_dir(self):
        return write_run_dir(self.tmp / "run", [("I1", "base", [("u", "m")])])

    def test_copy_is_retried_once_and_recorded_as_error(self):
        out = self.tmp / "judge_JC.jsonl"
        provider = FakeJudgeProvider([copied_output(), copied_output()])
        counts = judge_run(self._run_dir(), provider, "JC", "lg", out, manual_text="")
        self.assertEqual(counts["total"], 1)
        self.assertEqual(counts["ok"], 0)
        self.assertEqual(counts["parse_error"], 1)
        self.assertEqual(provider.n_calls, 2)  # the same retry budget as any parse error
        row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["status"], "ERROR")
        self.assertIn("copied from the example", row["error"])
        self.assertEqual(row["attempts"], 2)

    def test_a_retry_that_stops_copying_is_scored(self):
        out = self.tmp / "judge_JD.jsonl"
        provider = FakeJudgeProvider([copied_output(), VALID_1T])
        counts = judge_run(self._run_dir(), provider, "JD", "lg", out, manual_text="")
        self.assertEqual(counts["ok"], 1)
        row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["attempts"], 2)
        self.assertNotIn("예시 근거 문장", row["record"]["rationale"])


# -- raw_text on ERROR records ------------------------------------------------


class TestRawTextOnError(TempDirTest):
    def _judged(self, outputs, judge_id="JR", n_turns=1):
        run_dir = write_run_dir(
            self.tmp / ("run_%s" % judge_id),
            [("I1", "base", [("u%d" % i, "m%d" % i) for i in range(n_turns)])],
        )
        out = self.tmp / ("judge_%s.jsonl" % judge_id)
        judge_run(run_dir, FakeJudgeProvider(outputs), judge_id, "lg", out, manual_text="")
        return [
            json.loads(l)
            for l in out.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]

    def test_error_record_carries_the_last_raw_text(self):
        canned = copied_output()
        row = self._judged([canned, canned], judge_id="JE")[0]
        self.assertEqual(row["status"], "ERROR")
        self.assertEqual(row["raw_text"], canned)

    def test_ok_record_has_no_raw_text_key(self):
        row = self._judged([VALID_1T], judge_id="JO")[0]
        self.assertEqual(row["status"], "ok")
        self.assertNotIn("raw_text", row)
        self.assertEqual(len(row["raw_text_sha256"]), 64)

    def test_provider_error_records_a_null_raw_text(self):
        row = self._judged([TimeoutError("simulated timeout")], judge_id="JT")[0]
        self.assertEqual(row["status"], "ERROR")
        self.assertIn("raw_text", row)
        self.assertIsNone(row["raw_text"])

    def test_an_ok_record_carrying_raw_text_is_refused(self):
        rec = make_judge_record(
            judge_id="J1", family="fam", item_id="I1", condition="base", n_turns=1,
            prompt_sha256="0" * 64, raw_text=VALID_1T,
            record=parse_judge_output(VALID_1T), error=None, attempts=1, model_id="m",
            depth=1, view=VIEW_PREFIX, is_control=False,
        )
        self.assertNotIn("raw_text", rec)
        check_record_fail_closed(rec)
        rec["raw_text"] = VALID_1T
        with self.assertRaises(RuntimeError):
            check_record_fail_closed(rec)
        with self.assertRaises(RuntimeError):
            write_judge_record(self.tmp / "j.jsonl", rec)


class TestConsumersTolerateRawText(TempDirTest):
    """panel.py and the judge-file analysis reader accept such an ERROR record."""

    def _files(self):
        run_dir = write_run_dir(
            self.tmp / "run",
            [("I1", "base", [("u", "m")]), ("I2", "base", [("u1", "m1"), ("u2", "m2")])],
        )
        plans = {
            "J1": ("lg", [VALID_1T, VALID_1T, VALID_2T]),
            # J2 copies the example on I2 depth 2 -> ERROR carrying raw_text
            "J2": ("qwen", [VALID_1T, VALID_1T, copied_output(n_turns=2),
                            copied_output(n_turns=2)]),
            "J3": ("gemma", [VALID_1T, VALID_1T, VALID_2T]),
        }
        files = []
        for jid, (fam, outputs) in plans.items():
            out = self.tmp / ("judge_%s.jsonl" % jid)
            judge_run(run_dir, FakeJudgeProvider(outputs), jid, fam, out, manual_text="")
            files.append(str(out))
        return files

    def test_panel_loads_and_aggregates_the_error_record(self):
        files = self._files()
        rows = load_judge_file(files[1])
        error_rows = [r for r in rows if r["status"] == "ERROR"]
        self.assertEqual(len(error_rows), 1)
        self.assertIn("raw_text", error_rows[0])
        recs = aggregate(files, {"J1": "lg", "J2": "qwen", "J3": "gemma"}, "kanana")
        self.assertEqual(
            [(r["item_id"], r["depth"], r["status"]) for r in recs],
            [("I1", 1, "ok"), ("I2", 1, "ok"), ("I2", 2, "ok")],
        )
        self.assertEqual(recs[2]["judges_used"], ["J1", "J3"])
        self.assertEqual(recs[2]["judges_error"], ["J2"])

    def test_reliability_reader_ignores_the_error_record(self):
        df = n3_reliability.long_from_judge_files(self._files())
        self.assertEqual(len(df), 8)  # 9 views - 1 ERROR
        self.assertNotIn("raw_text", df.columns)


# -- provenance ---------------------------------------------------------------


class TestTemplateProvenance(TempDirTest):
    def test_meta_names_the_template_file_and_its_hash(self):
        run_dir = write_run_dir(self.tmp / "run", [("I1", "base", [("u", "m")])])
        out = self.tmp / "judge_JM.jsonl"
        judge_run(run_dir, FakeJudgeProvider([VALID_1T]), "JM", "lg", out)
        meta = json.loads(meta_path_for(out).read_text(encoding="utf-8"))
        self.assertEqual(meta["prompt_template_path"], str(PROMPT_PATH))
        self.assertEqual(meta["prompt_template_sha256"], sha256_file(PROMPT_PATH))

    def test_an_inline_template_claims_no_path(self):
        run_dir = write_run_dir(self.tmp / "run2", [("I1", "base", [("u", "m")])])
        out = self.tmp / "judge_JI.jsonl"
        tpl = PROMPT_PATH.read_text(encoding="utf-8")
        judge_run(
            run_dir, FakeJudgeProvider([VALID_1T]), "JI", "lg", out,
            manual_text="", template=tpl,
        )
        meta = json.loads(meta_path_for(out).read_text(encoding="utf-8"))
        self.assertIsNone(meta["prompt_template_path"])
        self.assertEqual(meta["prompt_template_sha256"], sha256_file(PROMPT_PATH))

    def test_cli_prints_the_template_file(self):
        run_dir = write_run_dir(self.tmp / "run3", [("I1", "base", [("u", "m")])])
        fake = self.tmp / "fake.json"
        fake.write_text(json.dumps([VALID_1T]), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = judge_main(
                ["--run-dir", str(run_dir), "--provider", "fake", "--judge-id", "JV",
                 "--family", "lg", "--fake-outputs", str(fake), "--no-items"]
            )
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("prompt_template=%s" % PROMPT_PATH, buf.getvalue())
        self.assertIn("prompt_template_sha256=%s" % sha256_file(PROMPT_PATH), buf.getvalue())


# -- per-view-type retry reminder ---------------------------------------------


class TestRetryReminder(unittest.TestCase):
    """The re-ask must not tell a control view that the schema has five keys."""

    def test_control_reminder_names_seven_keys_and_both_control_keys(self):
        text = retry_reminder(2, is_control=True)
        self.assertIn("일곱", text)
        self.assertIn("over_refusal", text)
        self.assertIn("helpfulness", text)
        self.assertNotIn("다섯", text)

    def test_risk_reminder_names_five_keys_and_neither_control_key(self):
        text = retry_reminder(2, is_control=False)
        self.assertIn("다섯", text)
        self.assertNotIn("over_refusal", text)
        self.assertNotIn("helpfulness", text)
        self.assertNotIn("일곱", text)

    def test_reminder_states_the_number_of_a_objects(self):
        for n_turns in (1, 2, 6):
            for is_control in (False, True):
                with self.subTest(n_turns=n_turns, is_control=is_control):
                    self.assertIn(
                        "A는 정확히 %d개의 객체" % n_turns,
                        retry_reminder(n_turns, is_control=is_control),
                    )

    def test_reminder_without_a_depth_states_no_number(self):
        text = retry_reminder(None)
        self.assertIn("턴 수만큼", text)
        self.assertNotIn("정확히", text)

    def test_reminder_keeps_the_json_only_instruction(self):
        for is_control in (False, True):
            text = retry_reminder(1, is_control=is_control)
            self.assertIn("설명 없이 JSON 객체 하나만 출력하십시오", text)
            self.assertIn("D는 D1~D6, A의 각 원소는 A1~A4", text)


class TestRetryReminderInBothPaths(TempDirTest):
    """Sequential (batch_size=1) and batched runs re-ask with the same text."""

    def _retry_message(self, batch_size: int, is_control: bool, n_turns: int) -> str:
        judge_id = "JB%d%d" % (batch_size, int(is_control))
        run_dir = write_run_dir(
            self.tmp / ("run_%s" % judge_id),
            [("CTRL1" if is_control else "R1", "base",
              [("u%d" % i, "m%d" % i) for i in range(n_turns)])],
        )
        # A conversation of n_turns turns is n_turns prefix views: every view
        # before the last parses at once, the deepest view fails once and then
        # parses, so the last call is that view's re-ask.
        good = VALID_2T if n_turns == 2 else (CONTROL_1T if is_control else VALID_1T)
        shallow = CONTROL_1T if is_control else VALID_1T
        outputs = [shallow] * (n_turns - 1) + ["not json at all", good]
        provider = FakeJudgeProvider(outputs)
        judge_run(
            run_dir, provider, judge_id, "lg", self.tmp / ("judge_%s.jsonl" % judge_id),
            manual_text="", batch_size=batch_size,
            control_item_ids={"CTRL1"} if is_control else set(),
        )
        self.assertEqual(provider.n_calls, len(outputs))
        return provider.calls[-1][-1]["content"]

    def test_control_view_retry_message_in_both_paths(self):
        for batch_size in (1, 64):
            with self.subTest(batch_size=batch_size):
                text = self._retry_message(batch_size, True, 1)
                self.assertEqual(text, retry_reminder(1, is_control=True))
                self.assertIn("일곱", text)
                self.assertIn("over_refusal", text)
                self.assertIn("helpfulness", text)
                self.assertIn("A는 정확히 1개의 객체", text)

    def test_risk_view_retry_message_in_both_paths(self):
        for batch_size in (1, 64):
            with self.subTest(batch_size=batch_size):
                text = self._retry_message(batch_size, False, 2)
                self.assertEqual(text, retry_reminder(2, is_control=False))
                self.assertIn("다섯", text)
                self.assertNotIn("over_refusal", text)
                self.assertNotIn("helpfulness", text)
                self.assertIn("A는 정확히 2개의 객체", text)


# -- fail-closed manual loading -----------------------------------------------


class TestManualIsMandatory(TempDirTest):
    def test_default_manual_loads_and_is_not_empty(self):
        text = load_manual_text()
        self.assertTrue(text.strip())
        self.assertTrue(DEFAULT_MANUAL_PATH.is_file())

    def test_missing_manual_raises_naming_the_path(self):
        missing = self.tmp / "no_such_manual.md"
        with self.assertRaises(FileNotFoundError) as ctx:
            load_manual_text(missing)
        self.assertIn(str(missing), str(ctx.exception))

    def test_empty_manual_raises_naming_the_path(self):
        empty = self.tmp / "empty_manual.md"
        empty.write_text("   \n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            load_manual_text(empty)
        self.assertIn(str(empty), str(ctx.exception))

    def test_judge_run_without_inline_text_needs_the_manual_file(self):
        # judge_run(manual_text=None) reads the file; the tests' inline
        # manual_text="" path stays available and is unaffected.
        run_dir = write_run_dir(self.tmp / "run", [("I1", "base", [("u", "m")])])
        with mock.patch("kyra.judge.DEFAULT_MANUAL_PATH", self.tmp / "gone.md"):
            with self.assertRaises(FileNotFoundError):
                judge_run(
                    run_dir, FakeJudgeProvider([VALID_1T]), "JZ", "lg",
                    self.tmp / "judge_JZ.jsonl",
                )
        self.assertFalse((self.tmp / "judge_JZ.jsonl").exists())

    def test_cli_exits_4_before_any_provider_is_built(self):
        run_dir = write_run_dir(self.tmp / "run_cli", [("I1", "base", [("u", "m")])])
        missing = self.tmp / "no_such_manual.md"

        def boom(args):  # a provider must not be constructed at all
            raise AssertionError("provider was built before the manual was checked")

        buf = io.StringIO()
        with mock.patch("kyra.judge._make_provider", boom):
            with redirect_stdout(buf), redirect_stderr(buf):
                rc = judge_main(
                    ["--run-dir", str(run_dir), "--provider", "fake", "--judge-id", "JY",
                     "--family", "lg", "--no-items", "--manual", str(missing)]
                )
        self.assertEqual(rc, 4)
        self.assertIn("annotation manual not found", buf.getvalue())
        self.assertIn(str(missing), buf.getvalue())
        self.assertFalse((run_dir / "judge_JY.jsonl").exists())

    def test_cli_with_the_real_manual_still_runs(self):
        run_dir = write_run_dir(self.tmp / "run_ok", [("I1", "base", [("u", "m")])])
        fake = self.tmp / "fake.json"
        fake.write_text(json.dumps([VALID_1T]), encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = judge_main(
                ["--run-dir", str(run_dir), "--provider", "fake", "--judge-id", "JW",
                 "--family", "lg", "--fake-outputs", str(fake), "--no-items"]
            )
        self.assertEqual(rc, 0, buf.getvalue())
        self.assertIn("manual=%s" % DEFAULT_MANUAL_PATH, buf.getvalue())


if __name__ == "__main__":
    unittest.main()
