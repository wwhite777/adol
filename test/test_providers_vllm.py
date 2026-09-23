"""Unit tests for VLLMProvider. No GPU, no vllm install, no network.

The vllm (and transformers) modules are faked in sys.modules, so every test here
exercises our glue code only: chat-template application, the deterministic
sampling parameters we hand to the engine, error propagation, the manifest
fields, and get_provider wiring. Nothing loads a model.
"""

from __future__ import annotations

import hashlib
import os
import sys
import types
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from kyra.providers import (  # noqa: E402
    PROVIDERS,
    FailingProvider,
    MockProvider,
    Provider,
    ProviderError,
    VLLMProvider,
    get_provider,
)

FAKE_TEMPLATE = "{% for m in messages %}<|{{m['role']}}|>{{m['content']}}{% endfor %}"
FAKE_VERSION = "0.0.0-fake"


class FakeTokenizer:
    """Records apply_chat_template calls; renders a marker prompt."""

    def __init__(self, chat_template=FAKE_TEMPLATE):
        self.chat_template = chat_template
        self.calls = []

    def apply_chat_template(
        self, messages, tokenize=None, add_generation_prompt=None, **extra
    ):
        self.calls.append(
            {
                "messages": list(messages),
                "tokenize": tokenize,
                "add_generation_prompt": add_generation_prompt,
                "extra": dict(extra),
            }
        )
        body = "|".join("%s:%s" % (m["role"], m["content"]) for m in messages)
        return "TPL[%s]<gen>" % body


class FakeCompletion:
    def __init__(self, text):
        self.text = text


class FakeRequestOutput:
    def __init__(self, text):
        self.outputs = [FakeCompletion(text)]


class FakeSamplingParams:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeLLM:
    """Stand-in for vllm.LLM. Never touches a GPU."""

    constructions = []
    reply_text = "괜찮아, 지금 많이 힘들었겠다."
    raise_on_construct = None

    def __init__(self, **kwargs):
        if FakeLLM.raise_on_construct is not None:
            raise FakeLLM.raise_on_construct
        FakeLLM.constructions.append(kwargs)
        self.kwargs = kwargs
        self.generate_calls = []
        self._tokenizer = FakeTokenizer()

    def get_tokenizer(self):
        return self._tokenizer

    def generate(self, prompts, sampling_params):
        self.generate_calls.append((list(prompts), sampling_params))
        return [FakeRequestOutput(FakeLLM.reply_text) for _ in prompts]


def install_fake_vllm(test, llm_cls=FakeLLM, version=FAKE_VERSION):
    """Put a fake vllm module in sys.modules for the duration of one test."""
    mod = types.ModuleType("vllm")
    mod.LLM = llm_cls
    mod.SamplingParams = FakeSamplingParams
    mod.__version__ = version
    previous = sys.modules.get("vllm")
    sys.modules["vllm"] = mod

    def restore():
        if previous is None:
            sys.modules.pop("vllm", None)
        else:
            sys.modules["vllm"] = previous

    test.addCleanup(restore)
    return mod


class VLLMProviderBaseTest(unittest.TestCase):
    def setUp(self):
        FakeLLM.constructions = []
        FakeLLM.raise_on_construct = None
        FakeLLM.reply_text = "괜찮아, 지금 많이 힘들었겠다."


class TestVLLMProviderFields(VLLMProviderBaseTest):
    """model_id / provider_name / api_version are what the manifest copies."""

    def test_is_a_provider_subclass(self):
        self.assertTrue(issubclass(VLLMProvider, Provider))

    def test_provider_name_is_vllm(self):
        p = VLLMProvider(model_path="LGAI-EXAONE/EXAONE-4.0-1.2B")
        self.assertEqual(p.provider_name, "vllm")

    def test_model_id_is_repo_id_when_not_a_local_dir(self):
        p = VLLMProvider(model_path="LGAI-EXAONE/EXAONE-4.0-1.2B")
        self.assertEqual(p.model_id, "LGAI-EXAONE/EXAONE-4.0-1.2B")

    def test_model_id_is_basename_for_a_local_dir(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "EXAONE-4.0-1.2B")
            os.mkdir(sub)
            self.assertEqual(VLLMProvider(model_path=sub).model_id, "EXAONE-4.0-1.2B")
            self.assertEqual(
                VLLMProvider(model_path=sub + os.sep).model_id, "EXAONE-4.0-1.2B"
            )

    def test_api_version_is_the_vllm_version_string(self):
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y")
        self.assertEqual(p.api_version, FAKE_VERSION)

    def test_api_version_marks_missing_vllm_without_raising(self):
        previous = sys.modules.get("vllm")
        sys.modules["vllm"] = None  # import vllm -> ImportError

        def restore():
            if previous is None:
                sys.modules.pop("vllm", None)
            else:
                sys.modules["vllm"] = previous

        self.addCleanup(restore)
        p = VLLMProvider(model_path="x/y")
        self.assertIn("vllm-unavailable", p.api_version)

    def test_defaults_match_the_preregistered_generation_settings(self):
        p = VLLMProvider(model_path="x/y")
        self.assertEqual(p.max_new_tokens, 350)
        self.assertEqual(p.temperature, 0.0)
        self.assertEqual(p.seed, 20260922)
        self.assertEqual(p.gpu_memory_utilization, 0.85)

    def test_empty_model_path_is_rejected(self):
        with self.assertRaises(ValueError):
            VLLMProvider(model_path="")


class TestVLLMProviderLaziness(VLLMProviderBaseTest):
    def test_constructing_the_provider_builds_no_engine(self):
        install_fake_vllm(self)
        VLLMProvider(model_path="x/y")
        self.assertEqual(FakeLLM.constructions, [])

    def test_importing_the_module_does_not_import_vllm(self):
        # kyra.providers is already imported at module scope above; if it had
        # imported vllm eagerly, the real (absent) package would be in sys.modules.
        import kyra.providers as prov

        self.assertTrue(hasattr(prov, "VLLMProvider"))
        self.assertNotIn("vllm", getattr(prov, "__dict__", {}))

    def test_engine_is_built_once_and_reused(self):
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y")
        p.generate([{"role": "user", "content": "안녕"}])
        p.generate([{"role": "user", "content": "또 안녕"}])
        self.assertEqual(len(FakeLLM.constructions), 1)


class TestVLLMProviderChatTemplate(VLLMProviderBaseTest):
    def test_prompt_is_built_with_the_models_chat_template(self):
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y")
        messages = [
            {"role": "user", "content": "너무 힘들어"},
            {"role": "assistant", "content": "그랬구나"},
            {"role": "user", "content": "어떻게 해야 해?"},
        ]
        p.generate(messages)
        tok = p._tokenizer
        self.assertEqual(len(tok.calls), 1)
        call = tok.calls[0]
        self.assertEqual(call["messages"], messages)
        self.assertFalse(call["tokenize"])
        self.assertTrue(call["add_generation_prompt"])
        prompt = p._llm.generate_calls[0][0][0]
        self.assertTrue(prompt.startswith("TPL["))
        self.assertIn("user:너무 힘들어", prompt)
        self.assertIn("assistant:그랬구나", prompt)

    def test_chat_template_provenance_is_recorded(self):
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y")
        self.assertIsNone(p.chat_template_sha256)
        p.generate([{"role": "user", "content": "안녕"}])
        self.assertEqual(p.chat_template_source, "tokenizer.chat_template")
        self.assertEqual(
            p.chat_template_sha256,
            hashlib.sha256(FAKE_TEMPLATE.encode("utf-8")).hexdigest(),
        )

    def test_missing_chat_template_is_an_error_not_a_hand_rolled_prompt(self):
        class NoTemplateLLM(FakeLLM):
            def get_tokenizer(self):
                return FakeTokenizer(chat_template=None)

        install_fake_vllm(self, llm_cls=NoTemplateLLM)
        p = VLLMProvider(model_path="x/y")
        with self.assertRaises(ProviderError) as ctx:
            p.generate([{"role": "user", "content": "안녕"}])
        self.assertIn("chat template", str(ctx.exception))

    def test_falls_back_to_transformers_tokenizer_when_engine_has_none(self):
        class NoGetTokenizerLLM(FakeLLM):
            get_tokenizer = None

        install_fake_vllm(self, llm_cls=NoGetTokenizerLLM)
        tok = FakeTokenizer()
        tf = types.ModuleType("transformers")

        class AutoTokenizer:
            @staticmethod
            def from_pretrained(path, trust_remote_code=None):
                tok.path = path
                return tok

        tf.AutoTokenizer = AutoTokenizer
        previous = sys.modules.get("transformers")
        sys.modules["transformers"] = tf
        self.addCleanup(
            lambda: sys.modules.pop("transformers", None)
            if previous is None
            else sys.modules.__setitem__("transformers", previous)
        )
        p = VLLMProvider(model_path="x/y")
        p.generate([{"role": "user", "content": "안녕"}])
        self.assertEqual(tok.path, "x/y")
        self.assertEqual(len(tok.calls), 1)


class TestVLLMProviderDeterminism(VLLMProviderBaseTest):
    def test_sampling_params_carry_the_deterministic_settings(self):
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y", max_new_tokens=350, seed=20260922)
        p.generate([{"role": "user", "content": "안녕"}])
        params = p._llm.generate_calls[0][1]
        self.assertIsInstance(params, FakeSamplingParams)
        self.assertEqual(params.kwargs["temperature"], 0.0)
        self.assertEqual(params.kwargs["top_p"], 1.0)
        self.assertEqual(params.kwargs["max_tokens"], 350)
        self.assertEqual(params.kwargs["seed"], 20260922)

    def test_overrides_reach_the_sampling_params(self):
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y", max_new_tokens=64, temperature=0.7, seed=7)
        p.generate([{"role": "user", "content": "안녕"}])
        params = p._llm.generate_calls[0][1]
        self.assertEqual(params.kwargs["max_tokens"], 64)
        self.assertEqual(params.kwargs["temperature"], 0.7)
        self.assertEqual(params.kwargs["seed"], 7)

    def test_engine_gets_seed_and_memory_utilisation(self):
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y", gpu_memory_utilization=0.5)
        p.generate([{"role": "user", "content": "안녕"}])
        kw = FakeLLM.constructions[0]
        self.assertEqual(kw["model"], "x/y")
        self.assertEqual(kw["seed"], 20260922)
        self.assertEqual(kw["gpu_memory_utilization"], 0.5)

    def test_returns_the_stripped_completion_text(self):
        install_fake_vllm(self)
        FakeLLM.reply_text = "  힘들었겠다.  "
        p = VLLMProvider(model_path="x/y")
        self.assertEqual(p.generate([{"role": "user", "content": "안녕"}]), "힘들었겠다.")


class TestVLLMProviderErrors(VLLMProviderBaseTest):
    """Failures must surface with the original text, never become a mock reply."""

    def test_engine_construction_failure_propagates_original_text(self):
        FakeLLM.raise_on_construct = RuntimeError("CUDA out of memory on device 0")
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y")
        with self.assertRaises(ProviderError) as ctx:
            p.generate([{"role": "user", "content": "안녕"}])
        msg = str(ctx.exception)
        self.assertIn("CUDA out of memory on device 0", msg)
        self.assertIn("RuntimeError", msg)
        self.assertIsInstance(ctx.exception.__cause__, RuntimeError)

    def test_missing_vllm_raises_rather_than_falling_back(self):
        previous = sys.modules.get("vllm")
        sys.modules["vllm"] = None

        def restore():
            if previous is None:
                sys.modules.pop("vllm", None)
            else:
                sys.modules["vllm"] = previous

        self.addCleanup(restore)
        p = VLLMProvider(model_path="x/y")
        with self.assertRaises(ProviderError) as ctx:
            p.generate([{"role": "user", "content": "안녕"}])
        self.assertIn("vllm import failed", str(ctx.exception))

    def test_generate_failure_propagates_original_text(self):
        class BoomLLM(FakeLLM):
            def generate(self, prompts, sampling_params):
                raise ValueError("engine died mid-request")

        install_fake_vllm(self, llm_cls=BoomLLM)
        p = VLLMProvider(model_path="x/y")
        with self.assertRaises(ProviderError) as ctx:
            p.generate([{"role": "user", "content": "안녕"}])
        self.assertIn("engine died mid-request", str(ctx.exception))

    def test_empty_completion_is_an_error(self):
        install_fake_vllm(self)
        FakeLLM.reply_text = "   "
        p = VLLMProvider(model_path="x/y")
        with self.assertRaises(ProviderError):
            p.generate([{"role": "user", "content": "안녕"}])

    def test_no_messages_is_an_error(self):
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y")
        with self.assertRaises(ProviderError):
            p.generate([])

    def test_unexpected_output_shape_is_an_error(self):
        class EmptyOutLLM(FakeLLM):
            def generate(self, prompts, sampling_params):
                return []

        install_fake_vllm(self, llm_cls=EmptyOutLLM)
        p = VLLMProvider(model_path="x/y")
        with self.assertRaises(ProviderError) as ctx:
            p.generate([{"role": "user", "content": "안녕"}])
        self.assertIn("unexpected vllm output shape", str(ctx.exception))


class TestGetProviderWiring(unittest.TestCase):
    def test_vllm_is_registered(self):
        self.assertIs(PROVIDERS["vllm"], VLLMProvider)

    def test_get_provider_builds_a_vllm_provider_with_options(self):
        p = get_provider("vllm", model_path="x/y", max_new_tokens=350)
        self.assertIsInstance(p, VLLMProvider)
        self.assertEqual(p.model_path, "x/y")
        self.assertEqual(p.max_new_tokens, 350)

    def test_vllm_without_model_path_is_a_value_error(self):
        with self.assertRaises(ValueError):
            get_provider("vllm")

    def test_unknown_option_is_a_value_error(self):
        with self.assertRaises(ValueError):
            get_provider("vllm", model_path="x/y", nonsense=1)

    def test_mock_still_works_with_no_options(self):
        self.assertIsInstance(get_provider("mock"), MockProvider)

    def test_unknown_provider_still_raises_value_error(self):
        with self.assertRaises(ValueError):
            get_provider("openai")

    def test_failing_provider_untouched(self):
        with self.assertRaises(ProviderError):
            FailingProvider().generate([{"role": "user", "content": "x"}])


class TestVLLMEffectiveParams(VLLMProviderBaseTest):
    """effective_params() must be exactly what SamplingParams receives."""

    def test_effective_params_report_the_constructor_settings(self):
        p = VLLMProvider(model_path="x/y", max_new_tokens=350)
        self.assertEqual(
            p.effective_params(),
            {
                "max_tokens": 350,
                "temperature": 0.0,
                "top_p": 1.0,
                "chat_template_kwargs": {},
                "stop_token_ids": [],
            },
        )

    def test_effective_params_follow_an_override(self):
        p = VLLMProvider(model_path="x/y", max_new_tokens=64, temperature=0.7)
        self.assertEqual(
            p.effective_params(),
            {
                "max_tokens": 64,
                "temperature": 0.7,
                "top_p": 1.0,
                "chat_template_kwargs": {},
                "stop_token_ids": [],
            },
        )

    def test_effective_params_equal_the_sampling_params_actually_sent(self):
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y", max_new_tokens=350)
        p.generate([{"role": "user", "content": "안녕"}])
        sent = p._llm.generate_calls[0][1].kwargs
        eff = p.effective_params()
        self.assertEqual(eff["max_tokens"], sent["max_tokens"])
        self.assertEqual(eff["temperature"], sent["temperature"])
        self.assertEqual(eff["top_p"], sent["top_p"])

    def test_base_provider_declares_nothing(self):
        self.assertEqual(Provider().effective_params(), {})
        self.assertEqual(FailingProvider().effective_params(), {})


class TestVLLMGenerationOptions(VLLMProviderBaseTest):
    """Per-model chat_template_kwargs / stop_token_ids (hybrid-thinking models)."""

    def test_chat_template_kwargs_reach_apply_chat_template(self):
        install_fake_vllm(self)
        p = VLLMProvider(
            model_path="x/y", chat_template_kwargs={"skip_reasoning": True}
        )
        p.generate([{"role": "user", "content": "안녕"}])
        call = p._tokenizer.calls[0]
        self.assertEqual(call["extra"], {"skip_reasoning": True})
        self.assertFalse(call["tokenize"])
        self.assertTrue(call["add_generation_prompt"])

    def test_stop_token_ids_reach_the_sampling_params(self):
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y", stop_token_ids=[100273, 100275, 100274])
        p.generate([{"role": "user", "content": "안녕"}])
        params = p._llm.generate_calls[0][1]
        self.assertEqual(params.kwargs["stop_token_ids"], [100273, 100275, 100274])
        # the deterministic settings are untouched
        self.assertEqual(params.kwargs["temperature"], 0.0)
        self.assertEqual(params.kwargs["max_tokens"], 350)
        self.assertEqual(params.kwargs["seed"], 20260922)

    def test_effective_params_carry_both_keys_when_set(self):
        p = VLLMProvider(
            model_path="x/y",
            chat_template_kwargs={"skip_reasoning": True},
            stop_token_ids=[100273],
        )
        eff = p.effective_params()
        self.assertEqual(eff["chat_template_kwargs"], {"skip_reasoning": True})
        self.assertEqual(eff["stop_token_ids"], [100273])

    def test_effective_params_carry_both_keys_when_unset(self):
        eff = VLLMProvider(model_path="x/y").effective_params()
        self.assertIn("chat_template_kwargs", eff)
        self.assertIn("stop_token_ids", eff)
        self.assertEqual(eff["chat_template_kwargs"], {})
        self.assertEqual(eff["stop_token_ids"], [])

    def test_effective_params_are_copies_not_the_live_objects(self):
        p = VLLMProvider(
            model_path="x/y",
            chat_template_kwargs={"skip_reasoning": True},
            stop_token_ids=[1],
        )
        eff = p.effective_params()
        eff["chat_template_kwargs"]["skip_reasoning"] = False
        eff["stop_token_ids"].append(2)
        self.assertEqual(p.chat_template_kwargs, {"skip_reasoning": True})
        self.assertEqual(p.stop_token_ids, [1])

    def test_invalid_chat_template_kwargs_raise_value_error(self):
        for bad in ([("a", 1)], "skip_reasoning=True", 3):
            with self.assertRaises(ValueError):
                VLLMProvider(model_path="x/y", chat_template_kwargs=bad)
        with self.assertRaises(ValueError) as ctx:
            VLLMProvider(model_path="x/y", chat_template_kwargs={"opts": {"a": 1}})
        self.assertIn("opts", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            VLLMProvider(model_path="x/y", chat_template_kwargs={7: True})
        self.assertIn("7", str(ctx.exception))

    def test_invalid_stop_token_ids_raise_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            VLLMProvider(model_path="x/y", stop_token_ids="100273")
        self.assertIn("stop_token_ids", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            VLLMProvider(model_path="x/y", stop_token_ids=[100273, "100275"])
        self.assertIn("100275", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            VLLMProvider(model_path="x/y", stop_token_ids=[-1])
        self.assertIn("non-negative", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            VLLMProvider(model_path="x/y", stop_token_ids=[7, 7])
        self.assertIn("duplicated", str(ctx.exception))
        with self.assertRaises(ValueError):
            VLLMProvider(model_path="x/y", stop_token_ids=[True])

    def test_without_the_options_the_call_shapes_are_unchanged(self):
        install_fake_vllm(self)
        p = VLLMProvider(model_path="x/y")
        p.generate([{"role": "user", "content": "안녕"}])
        call = p._tokenizer.calls[0]
        self.assertEqual(call["extra"], {}, "no extra kwarg may reach the template")
        params = p._llm.generate_calls[0][1]
        self.assertEqual(
            sorted(params.kwargs),
            ["max_tokens", "seed", "temperature", "top_p"],
            "SamplingParams must keep its previous keys exactly",
        )

    def test_get_provider_passes_the_options_through(self):
        p = get_provider(
            "vllm",
            model_path="x/y",
            chat_template_kwargs={"enable_thinking": False},
            stop_token_ids=[100273],
        )
        self.assertEqual(p.chat_template_kwargs, {"enable_thinking": False})
        self.assertEqual(p.stop_token_ids, [100273])


class TestManifestProvenance(VLLMProviderBaseTest):
    """The manifest must record what the provider used, not the condition table."""

    def setUp(self):
        super().setUp()
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix="kyra_prov_")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def _items(self):
        from kyra.schema import Item

        return [
            Item(
                item_id="PROV-1",
                risk_group="R1",
                turn_type="single",
                turns=["너무 힘들어"],
                age_band="12-14",
                explicitness="explicit",
                localization="localized",
            )
        ]

    def _run(self, provider):
        import json
        import os as _os

        from kyra.runner import execute_run

        run_dir = _os.path.join(self.tmp, "run")
        ok, reasons = execute_run(self._items(), provider, ["base"], run_dir)
        self.assertTrue(ok, reasons)
        with open(_os.path.join(run_dir, "manifest.jsonl"), encoding="utf-8") as fh:
            records = [json.loads(l) for l in fh if l.strip()]
        self.assertEqual(len(records), 1)
        return records[0]

    def test_manifest_max_tokens_comes_from_the_provider_not_the_condition(self):
        from kyra.runner import CONDITIONS

        install_fake_vllm(self)
        rec = self._run(VLLMProvider(model_path="x/y", max_new_tokens=350))
        self.assertEqual(rec["max_tokens"], 350)
        self.assertNotEqual(rec["max_tokens"], CONDITIONS["base"]["max_tokens"])
        self.assertEqual(rec["temperature"], 0.0)
        self.assertEqual(rec["top_p"], 1.0)

    def test_manifest_follows_a_non_default_generation_cap(self):
        install_fake_vllm(self)
        rec = self._run(VLLMProvider(model_path="x/y", max_new_tokens=64))
        self.assertEqual(rec["max_tokens"], 64)

    def test_manifest_carries_the_chat_template_sha256(self):
        install_fake_vllm(self)
        rec = self._run(VLLMProvider(model_path="x/y"))
        self.assertEqual(rec["chat_template_source"], "tokenizer.chat_template")
        self.assertEqual(
            rec["chat_template_sha256"],
            hashlib.sha256(FAKE_TEMPLATE.encode("utf-8")).hexdigest(),
        )

    def test_manifest_records_the_vllm_model_id_and_api_version(self):
        install_fake_vllm(self)
        rec = self._run(VLLMProvider(model_path="LGAI-EXAONE/EXAONE-4.0-1.2B"))
        self.assertEqual(rec["model_id"], "LGAI-EXAONE/EXAONE-4.0-1.2B")
        self.assertEqual(rec["provider"], "vllm")
        self.assertEqual(rec["api_version"], FAKE_VERSION)

    def test_manifest_carries_the_generation_options(self):
        install_fake_vllm(self)
        rec = self._run(
            VLLMProvider(
                model_path="x/y",
                chat_template_kwargs={"skip_reasoning": True},
                stop_token_ids=[100273, 100275],
            )
        )
        self.assertEqual(rec["chat_template_kwargs"], {"skip_reasoning": True})
        self.assertEqual(rec["stop_token_ids"], [100273, 100275])

    def test_manifest_carries_the_generation_options_when_unset(self):
        install_fake_vllm(self)
        rec = self._run(VLLMProvider(model_path="x/y"))
        self.assertEqual(rec["chat_template_kwargs"], {})
        self.assertEqual(rec["stop_token_ids"], [])

    def test_template_provenance_is_absent_for_a_provider_without_it(self):
        rec = self._run(MockProvider())
        self.assertNotIn("chat_template_sha256", rec)
        self.assertNotIn("chat_template_source", rec)

    def test_provider_cannot_inject_arbitrary_manifest_fields(self):
        from kyra.runner import provider_effective_params

        class Sneaky(MockProvider):
            def effective_params(self):
                return {"max_tokens": 11, "status": "ok", "junk": 1}

        self.assertEqual(provider_effective_params(Sneaky()), {"max_tokens": 11})
        rec = self._run(Sneaky())
        self.assertEqual(rec["max_tokens"], 11)
        self.assertNotIn("junk", rec)


class TestRunnerWiring(unittest.TestCase):
    def test_model_path_and_max_new_tokens_flags_parse(self):
        from kyra.runner import build_parser, provider_opts_from_args

        args = build_parser().parse_args(
            [
                "--items", "i.jsonl",
                "--provider", "vllm",
                "--model-path", "models/EXAONE",
                "--max-new-tokens", "350",
            ]
        )
        self.assertEqual(
            provider_opts_from_args(args),
            {"model_path": "models/EXAONE", "max_new_tokens": 350},
        )

    def test_generation_option_flags_parse_into_provider_options(self):
        from kyra.runner import build_parser, provider_opts_from_args

        args = build_parser().parse_args(
            [
                "--items", "i.jsonl",
                "--provider", "vllm",
                "--model-path", "models/HCX",
                "--chat-template-kwargs", '{"skip_reasoning": true}',
                "--stop-token-ids", "100273, 100275",
            ]
        )
        self.assertEqual(
            provider_opts_from_args(args),
            {
                "model_path": "models/HCX",
                "chat_template_kwargs": {"skip_reasoning": True},
                "stop_token_ids": [100273, 100275],
            },
        )

    def test_bad_generation_option_flags_are_value_errors(self):
        from kyra.runner import build_parser, provider_opts_from_args

        bad_json = build_parser().parse_args(
            ["--items", "i.jsonl", "--chat-template-kwargs", "{not json"]
        )
        with self.assertRaises(ValueError):
            provider_opts_from_args(bad_json)
        not_object = build_parser().parse_args(
            ["--items", "i.jsonl", "--chat-template-kwargs", "[1, 2]"]
        )
        with self.assertRaises(ValueError):
            provider_opts_from_args(not_object)
        bad_ids = build_parser().parse_args(
            ["--items", "i.jsonl", "--stop-token-ids", "100273,abc"]
        )
        with self.assertRaises(ValueError):
            provider_opts_from_args(bad_ids)

    def test_no_new_flags_means_no_options_so_defaults_stand(self):
        from kyra.runner import build_parser, provider_opts_from_args, resolve_conditions

        args = build_parser().parse_args(["--items", "i.jsonl"])
        self.assertEqual(provider_opts_from_args(args), {})
        self.assertEqual(args.provider, "mock")
        # --conditions/--condition both default to None; the runner resolves that to the frozen base condition
        self.assertIsNone(args.condition)
        self.assertEqual(resolve_conditions(args), ["base"])
        self.assertEqual(args.out_root, "result/raw")


if __name__ == "__main__":
    unittest.main()
