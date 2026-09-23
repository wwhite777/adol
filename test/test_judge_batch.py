"""Self-tests for batched judge decoding (kyra.judge --batch-size, 2026-09-23).

The claim under test: batching changes only how many provider calls are made,
never what is written. So every test here compares --batch-size 1 (the sequential
call sequence: one call per view, a retry immediately after the view that failed)
with a large batch size on the SAME per-view canned outputs, and requires the
judge JSONL to be byte-identical. The canned provider is keyed by (view, attempt
number) rather than by call order, because the two modes consume the outputs in a
different order by construction.

Runnable as `PYTHONPATH=src:test python -m unittest test_judge_batch`.
"""

from __future__ import annotations

import io
import json
import math
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

from kyra import campaign  # noqa: E402
from kyra.judge import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    retry_reminder,
    build_parser as judge_parser,
    judge_run,
    main as judge_main,
    meta_path_for,
)
from kyra.providers import Provider, ProviderError, VLLMProvider  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MALFORMED = (FIXTURES / "judge_fake_malformed.json").read_text(encoding="utf-8")

META_FIELDS = {
    "judge_id",
    "family",
    "provider",
    "model_id",
    "model_path",
    "provider_effective_params",
    "decode_mode",
    "batch_size",
    "max_retries",
    "views",
    # judge prompt v0.3 (2026-09-23): which prompt template produced this file
    "prompt_template_path",
    "prompt_template_sha256",
    "run_dir",
    "out_path",
    "n_views",
    "n_ok",
    "n_parse_errors_first_pass",
    "n_retried",
    "n_error_final",
    "items_path",
    "items_sha256",
    "anchors_path",
    "anchors_sha256",
    "started_utc",
    "finished_utc",
}

# 4 conversations -> 7 prefix views. Every model_text is unique, so the last
# "[턴 k] AI: <text>" line of a prompt names the view it belongs to.
CONVERSATIONS = [
    ("I1", "base", [("I1u1", "I1m1")]),
    ("I2", "base", [("I2u1", "I2m1"), ("I2u2", "I2m2"), ("I2u3", "I2m3")]),
    ("I3", "base", [("I3u1", "I3m1"), ("I3u2", "I3m2")]),
    ("I4", "base", [("I4u1", "I4m1")]),
]
VIEW_KEYS = ["I1m1", "I2m1", "I2m2", "I2m3", "I3m1", "I3m2", "I4m1"]
VIEW_DEPTH = {"I1m1": 1, "I2m1": 1, "I2m2": 2, "I2m3": 3, "I3m1": 1, "I3m2": 2, "I4m1": 1}


def valid_output(depth: int) -> str:
    """A judge reply that parses for a view of `depth` turns."""
    return json.dumps(
        {
            "D": {"D1": 2, "D2": 1, "D3": 2, "D4": 1, "D5": 2, "D6": 2},
            "A": [{"A1": 0, "A2": 1, "A3": 0, "A4": 0} for _ in range(depth)],
            "critical_failure": False,
            "cf_codes": [],
            "rationale": "canned reply for a %d-turn view" % depth,
        },
        ensure_ascii=False,
    )


def write_run_dir(run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "responses.jsonl").open("w", encoding="utf-8") as fh:
        for item_id, condition, turns in CONVERSATIONS:
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


def view_key(messages) -> str:
    """The view a judge prompt belongs to = the last AI line of its transcript."""
    user = messages[1]["content"]
    marker = "] AI: "
    return user[user.rindex(marker) + len(marker):].split("\n", 1)[0].strip()


class RecordingProvider(Provider):
    """Canned judge outputs keyed by (view, attempt), recording every call.

    replies maps a view key to the list of replies for its 1st, 2nd, ... attempt
    (a str is returned, an Exception is raised). Keying by view instead of by call
    order is what makes the sequential and the batched run comparable at all.
    `calls` is the flat sequence of view keys asked, in order; `batches` is one
    list of view keys per provider call, so a test can count and size the calls.
    """

    provider_name = "recording"
    model_id = "recording-judge-v0"
    api_version = "0"

    def __init__(self, replies):
        self.replies = dict(replies)
        self.calls = []
        self.batches = []
        self.attempts = {}

    def effective_params(self):
        return {"max_tokens": 700, "temperature": 0.0, "top_p": 1.0}

    def _reply(self, messages):
        key = view_key(messages)
        self.calls.append(key)
        i = self.attempts.get(key, 0)
        self.attempts[key] = i + 1
        if key not in self.replies:
            raise ProviderError("no canned reply for view %r" % key)
        replies = self.replies[key]
        if i >= len(replies):
            raise ProviderError("view %r asked %d time(s), %d canned" % (key, i + 1, len(replies)))
        out = replies[i]
        if isinstance(out, BaseException):
            raise out
        return out

    def generate(self, messages):
        self.batches.append([view_key(messages)])
        return self._reply(messages)

    def generate_many(self, conversations):
        self.batches.append([view_key(m) for m in conversations])
        return [self._reply(m) for m in conversations]


def all_valid_replies():
    return {k: [valid_output(VIEW_DEPTH[k])] for k in VIEW_KEYS}


def retry_replies():
    """views 2 and 5 fail once then parse; view 7 never parses."""
    replies = {k: [valid_output(VIEW_DEPTH[k])] for k in VIEW_KEYS}
    replies["I2m1"] = [MALFORMED, valid_output(1)]   # view 2
    replies["I3m1"] = [MALFORMED, valid_output(1)]   # view 5
    replies["I4m1"] = [MALFORMED, MALFORMED]         # view 7
    return replies


class BatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kyra_judge_batch_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.run_dir = write_run_dir(self.tmp / "run")

    def judge(self, replies, batch_size, name, **kwargs):
        provider = RecordingProvider(replies)
        out = self.tmp / ("judge_%s.jsonl" % name)
        counts = judge_run(
            self.run_dir, provider, name, "lg", out, manual_text="",
            batch_size=batch_size, **kwargs
        )
        return provider, out, counts


# -- call sequences -----------------------------------------------------------


class TestCallSequence(BatchTest):
    def test_batch_size_1_is_the_sequential_per_view_sequence(self):
        provider, _, counts = self.judge(retry_replies(), 1, "S1")
        # exactly what the pre-batch loop did: view by view, the re-ask issued
        # immediately after the view that failed to parse
        self.assertEqual(
            provider.calls,
            ["I1m1", "I2m1", "I2m1", "I2m2", "I2m3", "I3m1", "I3m1", "I3m2", "I4m1", "I4m1"],
        )
        self.assertEqual(len(provider.batches), 10)
        self.assertTrue(all(len(b) == 1 for b in provider.batches))
        self.assertEqual(counts["decode_mode"], "sequential")
        self.assertEqual(counts["total"], 7)

    def test_batch_size_64_makes_ceil_n_over_64_calls_when_nothing_is_retried(self):
        provider, _, counts = self.judge(all_valid_replies(), 64, "S2")
        n = 7
        self.assertEqual(len(provider.batches), math.ceil(n / 64))
        self.assertEqual(provider.batches[0], VIEW_KEYS)
        self.assertEqual(counts["decode_mode"], "batched")
        self.assertEqual(counts["ok"], 7)

    def test_chunking_is_consecutive_and_sized(self):
        provider, _, _ = self.judge(all_valid_replies(), 3, "S3")
        self.assertEqual(
            provider.batches, [VIEW_KEYS[0:3], VIEW_KEYS[3:6], VIEW_KEYS[6:7]]
        )

    def test_the_retry_pass_carries_only_the_failed_views(self):
        provider, _, _ = self.judge(retry_replies(), 64, "S4")
        self.assertEqual(len(provider.batches), 2)
        self.assertEqual(provider.batches[0], VIEW_KEYS)
        self.assertEqual(provider.batches[1], ["I2m1", "I3m1", "I4m1"])

    def test_the_retry_prompt_is_the_same_re_ask_as_the_sequential_path(self):
        class Capture(RecordingProvider):
            def __init__(self, replies):
                super().__init__(replies)
                self.messages = []

            def generate_many(self, conversations):
                self.messages.extend([list(m) for m in conversations])
                return super().generate_many(conversations)

        provider = Capture(retry_replies())
        judge_run(
            self.run_dir, provider, "S5", "lg", self.tmp / "judge_S5.jsonl",
            manual_text="", batch_size=64,
        )
        retry_msgs = provider.messages[7]  # first message of the second pass
        # v0.3: rendered for the view being re-asked (I2m1 = depth 1, risk item).
        self.assertEqual(retry_msgs[-1]["content"], retry_reminder(1, is_control=False))
        self.assertEqual(retry_msgs[-2]["role"], "assistant")
        self.assertEqual(retry_msgs[-2]["content"], MALFORMED)
        self.assertEqual(len(retry_msgs), 4)


# -- identical records --------------------------------------------------------


class TestRecordsAreIdentical(BatchTest):
    def both(self, replies, **kwargs):
        p1, out1, c1 = self.judge(replies, 1, "B1", **kwargs)
        p64, out64, c64 = self.judge(replies, 64, "B64", **kwargs)
        return (p1, out1, c1), (p64, out64, c64)

    def strip_ids(self, path, judge_id):
        """The judge_id is part of every record and differs by construction here."""
        return path.read_bytes().replace(
            b'"judge_id": "%s"' % judge_id.encode(), b'"judge_id": "J"'
        )

    def test_all_ok_files_are_byte_identical(self):
        (_, out1, c1), (_, out64, c64) = self.both(all_valid_replies())
        self.assertEqual(self.strip_ids(out1, "B1"), self.strip_ids(out64, "B64"))
        self.assertEqual(c1["total"], c64["total"])
        self.assertEqual(c1["ok"], c64["ok"])

    def test_retry_run_files_are_byte_identical(self):
        (_, out1, c1), (_, out64, c64) = self.both(retry_replies())
        self.assertEqual(self.strip_ids(out1, "B1"), self.strip_ids(out64, "B64"))
        rows1 = [json.loads(l) for l in out1.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows64 = [json.loads(l) for l in out64.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual([r["status"] for r in rows1], [r["status"] for r in rows64])
        self.assertEqual([r["attempts"] for r in rows1], [r["attempts"] for r in rows64])
        # views 2 and 5 took two attempts and ended ok; view 7 took two and ERRORed
        self.assertEqual([r["attempts"] for r in rows1], [1, 2, 1, 1, 2, 1, 2])
        self.assertEqual(
            [r["status"] for r in rows1],
            ["ok", "ok", "ok", "ok", "ok", "ok", "ERROR"],
        )
        self.assertTrue(rows1[6]["error"].startswith("JudgeParseError"))
        for c in (c1, c64):
            self.assertEqual(c["parse_error"], 1)
            self.assertEqual(c["n_parse_errors_first_pass"], 3)
            self.assertEqual(c["n_retried"], 3)
            self.assertEqual(c["n_error_final"], 1)

    def test_no_retry_budget_is_identical_too(self):
        (_, out1, c1), (_, out64, c64) = self.both(retry_replies(), max_retries=0)
        self.assertEqual(self.strip_ids(out1, "B1"), self.strip_ids(out64, "B64"))
        self.assertEqual(c1["error"], 3)
        self.assertEqual(c64["error"], 3)
        self.assertEqual(c64["n_parse_errors_first_pass"], 3)
        self.assertEqual(c64["n_retried"], 0)

    def test_a_provider_failure_inside_a_batch_is_attributed_to_its_own_view(self):
        """A batched call fails as a whole, so the judge re-issues that chunk one
        view at a time and the failure lands on the view that caused it - the same
        record the sequential path writes. Each view answers the same way however
        often it is asked, so the two modes are comparable."""
        replies = {k: [valid_output(VIEW_DEPTH[k])] * 2 for k in VIEW_KEYS}
        replies["I2m2"] = [TimeoutError("simulated judge timeout")] * 2
        (p1, out1, c1), (p64, out64, c64) = self.both(replies)
        self.assertEqual(self.strip_ids(out1, "B1"), self.strip_ids(out64, "B64"))
        rows = [json.loads(l) for l in out64.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual([r["status"] for r in rows],
                         ["ok", "ok", "ERROR", "ok", "ok", "ok", "ok"])
        self.assertIn("TimeoutError", rows[2]["error"])
        self.assertEqual(c1["provider_error"], 1)
        self.assertEqual(c64["provider_error"], 1)
        # batch-size 1 never falls back (a chunk of one cannot be split)
        self.assertEqual(len(p1.batches), 7)
        self.assertTrue(all(len(b) == 1 for b in p1.batches))
        # batched: the failed chunk of 7, then the 7 single re-issues
        self.assertEqual(len(p64.batches), 8)
        self.assertEqual(p64.batches[0], VIEW_KEYS)
        self.assertTrue(all(len(b) == 1 for b in p64.batches[1:]))

    def test_batch_size_must_be_a_positive_int(self):
        for bad in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                judge_run(
                    self.run_dir, RecordingProvider(all_valid_replies()), "BX", "lg",
                    self.tmp / ("judge_bad_%s.jsonl" % bad), manual_text="", batch_size=bad,
                )


# -- provenance sidecar -------------------------------------------------------


class TestMetaSidecar(BatchTest):
    def test_sidecar_is_written_next_to_the_judge_file_with_the_declared_fields(self):
        _, out, counts = self.judge(retry_replies(), 64, "M1")
        meta_path = meta_path_for(out)
        self.assertEqual(meta_path.name, "judge_M1.meta.json")
        self.assertTrue(meta_path.is_file())
        self.assertEqual(counts["meta_path"], str(meta_path))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertEqual(set(meta), META_FIELDS)
        self.assertEqual(meta["decode_mode"], "batched")
        self.assertEqual(meta["batch_size"], 64)
        self.assertEqual(meta["n_views"], 7)
        self.assertEqual(meta["n_ok"], 6)
        self.assertEqual(meta["n_parse_errors_first_pass"], 3)
        self.assertEqual(meta["n_retried"], 3)
        self.assertEqual(meta["n_error_final"], 1)
        self.assertEqual(meta["judge_id"], "M1")
        self.assertEqual(meta["family"], "lg")
        self.assertEqual(meta["views"], "prefix")
        self.assertEqual(meta["max_retries"], 1)
        self.assertEqual(
            meta["provider_effective_params"],
            {"max_tokens": 700, "temperature": 0.0, "top_p": 1.0},
        )
        self.assertTrue(meta["started_utc"].endswith("Z"))
        self.assertTrue(meta["finished_utc"].endswith("Z"))
        self.assertEqual(meta["out_path"], str(out))

    def test_sequential_sidecar_says_sequential(self):
        _, out, _ = self.judge(all_valid_replies(), 1, "M2")
        meta = json.loads(meta_path_for(out).read_text(encoding="utf-8"))
        self.assertEqual(meta["decode_mode"], "sequential")
        self.assertEqual(meta["batch_size"], 1)
        self.assertEqual(meta["n_views"], 7)
        self.assertEqual(meta["n_error_final"], 0)

    def test_declared_provenance_reaches_the_sidecar(self):
        _, out, _ = self.judge(
            all_valid_replies(), 64, "M3",
            provenance={
                "model_path": "/models/judge-8b",
                "items_path": "items.jsonl",
                "items_sha256": "a" * 64,
                "anchors_path": "anchors.json",
                "anchors_sha256": "b" * 64,
            },
        )
        meta = json.loads(meta_path_for(out).read_text(encoding="utf-8"))
        self.assertEqual(meta["model_path"], "/models/judge-8b")
        self.assertEqual(meta["items_sha256"], "a" * 64)
        self.assertEqual(meta["anchors_sha256"], "b" * 64)

    def test_unknown_provenance_is_null_not_omitted(self):
        _, out, _ = self.judge(all_valid_replies(), 64, "M4")
        meta = json.loads(meta_path_for(out).read_text(encoding="utf-8"))
        for key in ("items_path", "items_sha256", "anchors_path", "anchors_sha256"):
            self.assertIsNone(meta[key])


# -- CLI ----------------------------------------------------------------------


class TestJudgeCLI(BatchTest):
    def test_default_batch_size_is_64(self):
        args = judge_parser().parse_args(
            ["--run-dir", "x", "--judge-id", "J", "--family", "lg"]
        )
        self.assertEqual(args.batch_size, DEFAULT_BATCH_SIZE)
        self.assertEqual(DEFAULT_BATCH_SIZE, 64)

    def test_cli_runs_batched_and_writes_the_sidecar(self):
        fake = self.tmp / "fake.json"
        fake.write_text(
            json.dumps([valid_output(VIEW_DEPTH[k]) for k in VIEW_KEYS]), encoding="utf-8"
        )
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = judge_main(
                ["--run-dir", str(self.run_dir), "--provider", "fake", "--judge-id", "JB",
                 "--family", "lg", "--fake-outputs", str(fake), "--no-items",
                 "--batch-size", "4"]
            )
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("decode_mode=batched batch_size=4", out)
        self.assertIn("total=7 ok=7", out)
        meta = json.loads(
            (self.run_dir / "judge_JB.meta.json").read_text(encoding="utf-8")
        )
        self.assertEqual(meta["batch_size"], 4)
        self.assertEqual(meta["n_views"], 7)
        self.assertEqual(meta["provider"], "fake")

    def test_cli_rejects_a_zero_batch_size(self):
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(buf):
            rc = judge_main(
                ["--run-dir", str(self.run_dir), "--provider", "fake", "--judge-id", "JZ",
                 "--family", "lg", "--no-items", "--batch-size", "0"]
            )
        self.assertEqual(rc, 4)
        self.assertIn("--batch-size", buf.getvalue())


# -- vllm provider ------------------------------------------------------------


class TestVLLMGenerateMany(unittest.TestCase):
    """Uses the fake vllm module from test_providers_vllm: no engine, no GPU."""

    def setUp(self):
        from test_providers_vllm import FakeLLM, install_fake_vllm

        FakeLLM.constructions = []
        FakeLLM.raise_on_construct = None
        FakeLLM.reply_text = "reply"
        install_fake_vllm(self)

    def conversations(self, n):
        return [
            [{"role": "system", "content": "sys"}, {"role": "user", "content": "u%d" % i}]
            for i in range(n)
        ]

    def test_one_engine_call_for_the_whole_list_in_input_order(self):
        class OrderedLLM:
            def __init__(self, **kwargs):
                from test_providers_vllm import FakeTokenizer

                self.generate_calls = []
                self._tokenizer = FakeTokenizer()

            def get_tokenizer(self):
                return self._tokenizer

            def generate(self, prompts, sampling_params):
                from test_providers_vllm import FakeRequestOutput

                self.generate_calls.append((list(prompts), sampling_params))
                return [FakeRequestOutput("out-%d" % i) for i, _ in enumerate(prompts)]

        from test_providers_vllm import install_fake_vllm

        install_fake_vllm(self, llm_cls=OrderedLLM)
        p = VLLMProvider(model_path="x/y", max_new_tokens=700)
        texts = p.generate_many(self.conversations(5))
        self.assertEqual(texts, ["out-0", "out-1", "out-2", "out-3", "out-4"])
        llm = p._llm
        self.assertEqual(len(llm.generate_calls), 1)
        prompts, params = llm.generate_calls[0]
        self.assertEqual(len(prompts), 5)
        self.assertIn("user:u0", prompts[0])
        self.assertIn("user:u4", prompts[4])
        self.assertEqual(params.kwargs["temperature"], 0.0)
        self.assertEqual(params.kwargs["max_tokens"], 700)
        self.assertEqual(params.kwargs["seed"], p.seed)

    def test_same_sampling_params_and_template_kwargs_as_the_single_call(self):
        p = VLLMProvider(
            model_path="x/y",
            chat_template_kwargs={"enable_thinking": False},
            stop_token_ids=[7, 8],
        )
        p.generate_many(self.conversations(2))
        single_prompt_calls = p._tokenizer.calls
        self.assertEqual(len(single_prompt_calls), 2)
        for call in single_prompt_calls:
            self.assertEqual(call["extra"], {"enable_thinking": False})
            self.assertTrue(call["add_generation_prompt"])
            self.assertFalse(call["tokenize"])
        _, params = p._llm.generate_calls[0]
        self.assertEqual(params.kwargs["stop_token_ids"], [7, 8])

    def test_empty_completion_in_a_batch_is_an_error(self):
        from test_providers_vllm import FakeLLM, install_fake_vllm

        FakeLLM.reply_text = "   "
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y")
        with self.assertRaises(ProviderError) as ctx:
            p.generate_many(self.conversations(3))
        self.assertIn("empty completion", str(ctx.exception))

    def test_a_short_output_list_is_an_error(self):
        class ShortLLM:
            def __init__(self, **kwargs):
                from test_providers_vllm import FakeTokenizer

                self._tokenizer = FakeTokenizer()

            def get_tokenizer(self):
                return self._tokenizer

            def generate(self, prompts, sampling_params):
                from test_providers_vllm import FakeRequestOutput

                return [FakeRequestOutput("only one")]

        from test_providers_vllm import install_fake_vllm

        install_fake_vllm(self, llm_cls=ShortLLM)
        p = VLLMProvider(model_path="x/y")
        with self.assertRaises(ProviderError) as ctx:
            p.generate_many(self.conversations(3))
        self.assertIn("1 output(s) for 3 prompt(s)", str(ctx.exception))

    def test_engine_failure_propagates_as_provider_error(self):
        class BoomLLM:
            def __init__(self, **kwargs):
                from test_providers_vllm import FakeTokenizer

                self._tokenizer = FakeTokenizer()

            def get_tokenizer(self):
                return self._tokenizer

            def generate(self, prompts, sampling_params):
                raise RuntimeError("CUDA out of memory")

        from test_providers_vllm import install_fake_vllm

        install_fake_vllm(self, llm_cls=BoomLLM)
        p = VLLMProvider(model_path="x/y")
        with self.assertRaises(ProviderError) as ctx:
            p.generate_many(self.conversations(2))
        self.assertIn("CUDA out of memory", str(ctx.exception))

    def test_no_conversations_is_an_error(self):
        p = VLLMProvider(model_path="x/y")
        with self.assertRaises(ProviderError):
            p.generate_many([])


class TestMockProviderGenerateMany(unittest.TestCase):
    def test_mock_maps_the_single_path(self):
        from kyra.providers import MockProvider

        p = MockProvider()
        convs = [
            [{"role": "user", "content": "안녕"}],
            [{"role": "user", "content": "요즘 힘들어"}],
        ]
        self.assertEqual(p.generate_many(convs), [p.generate(convs[0]), p.generate(convs[1])])


# -- campaign pass-through ----------------------------------------------------


class TestCampaignBatchSize(unittest.TestCase):
    def judge_entry(self, **extra):
        entry = {
            "judge_id": "J1",
            "model_id": "org/judge-8b",
            "model_path": "org/judge-8b",
            "family": "lg",
            "provider": "vllm",
            "gpu_memory_utilization": 0.5,
            "batch_size": None,
            "fake_outputs": None,
            "notes": "",
        }
        entry.update(extra)
        return entry

    def cmd(self, judge):
        return campaign.judge_command(
            judge, Path("/runs/r1"), Path("items.jsonl"), Path("/runs/r1/judge_J1.jsonl"), None
        )

    def test_declared_batch_size_is_passed_through(self):
        cmd = self.cmd(self.judge_entry(batch_size=16))
        self.assertIn("--batch-size", cmd)
        self.assertEqual(cmd[cmd.index("--batch-size") + 1], "16")

    def test_undeclared_batch_size_passes_no_flag(self):
        self.assertNotIn("--batch-size", self.cmd(self.judge_entry()))

    def test_load_judges_reads_and_validates_batch_size(self):
        tmp = Path(tempfile.mkdtemp(prefix="kyra_judges_json_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        path = tmp / "judges.json"
        path.write_text(
            json.dumps(
                {
                    "judges": [
                        {"judge_id": "J1", "family": "lg", "provider": "mock", "batch_size": 16},
                        {"judge_id": "J2", "family": "qwen", "provider": "mock"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        judges = campaign.load_judges(path)
        self.assertEqual(judges[0]["batch_size"], 16)
        self.assertIsNone(judges[1]["batch_size"])

        path.write_text(
            json.dumps(
                {"judges": [{"judge_id": "J1", "family": "lg", "provider": "mock",
                             "batch_size": 0}]}
            ),
            encoding="utf-8",
        )
        with self.assertRaises(campaign.CampaignError) as ctx:
            campaign.load_judges(path)
        self.assertIn("batch_size", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
