"""Model providers for pipeline v0.

MockProvider is a deterministic offline double. VLLMProvider runs local
open-weight models through the vllm offline engine (no server, no network at
generate time: the weights must already be on disk). Importing this module never
imports vllm and never loads a model - the engine is built on first generate().
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List, Optional


class ProviderError(RuntimeError):
    """Raised by a provider when a call fails (never swallowed into a score)."""


class Provider:
    """Interface every provider implements.

    Attributes model_id / provider_name / api_version are copied verbatim into
    the run manifest.
    """

    provider_name = "base"
    model_id = "unset"
    api_version = "unset"

    def generate(self, messages: List[Dict[str, str]]) -> str:
        raise NotImplementedError("Provider.generate must be implemented")

    def effective_params(self) -> Dict[str, object]:
        """The generation parameters this provider actually uses.

        Keys are manifest field names (max_tokens / temperature / top_p). An
        empty dict means "this provider declares nothing", and the runner then
        falls back to the condition's configured values. A provider must never
        report a parameter it does not in fact apply.
        """
        return {}


# Canned replies. Index is chosen by a hash of the last user utterance, so a
# given conversation always yields the same transcript.
_CANNED = (
    "그 얘기를 꺼내줘서 고마워. 지금 상황이 많이 힘들게 느껴질 것 같아. "
    "혼자 감당하지 말고 믿을 수 있는 어른이나 1388(청소년전화)에 같이 이야기해보면 좋겠어.",
    "나는 AI라서 네 옆에 직접 있어줄 수는 없어. 그래도 지금 느끼는 감정은 충분히 이해가 돼. "
    "학교 Wee클래스 선생님께 이야기해보는 건 어떨까?",
    "그 요청은 도와줄 수 없어. 너한테 위험할 수 있는 일이라서 그래. "
    "대신 지금 무엇 때문에 그런 생각이 들었는지 같이 이야기해볼 수 있어.",
    "지금 이야기한 내용은 혼자만 알고 있기엔 무거운 것 같아. "
    "부모님이나 담임 선생님처럼 믿을 만한 어른에게 알리는 게 좋겠어.",
    "오늘 있었던 일 얘기해줘서 좋아. 친구들이랑 같이 해볼 만한 것도 떠오르면 말해줘.",
    "그건 내가 판단하기 어려운 부분이야. 정확한 정보가 필요하면 선생님이나 전문 상담 기관에 확인해보는 게 안전해.",
    "네가 그렇게 느낄 만한 상황이었네. 나는 AI 챗봇이고, 사람 상담자를 대신할 수는 없어. "
    "청소년사이버상담센터(1388)에 익명으로 상담할 수도 있어.",
    "그 고민은 꽤 오래 이어진 것 같아 보여. 지금 당장 위험한 상황이라면 112나 119에 바로 연락해야 해.",
)


class MockProvider(Provider):
    """Deterministic offline provider: reply = f(sha256(last user utterance)).

    The digest prefix is embedded in the reply so a transcript can be traced
    back to the utterance that produced it.
    """

    provider_name = "mock"
    model_id = "mock-v0"
    api_version = "0"
    # The mock samples nothing: replies are canned, so temperature/top_p are
    # nominal and there is no token cap at all (hence max_tokens=None, not a
    # number we do not enforce).
    temperature = 0.0
    top_p = 1.0
    max_tokens = None

    def effective_params(self) -> Dict[str, object]:
        return {
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
        }

    def generate(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            raise ProviderError("MockProvider.generate called with no messages")
        last_user = None
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        if last_user is None:
            raise ProviderError("MockProvider.generate: no user message in context")
        digest = hashlib.sha256(last_user.encode("utf-8")).hexdigest()
        reply = _CANNED[int(digest[:8], 16) % len(_CANNED)]
        return "%s [mock-v0:%s]" % (reply, digest[:8])


class FailingProvider(Provider):
    """Test double: always fails. Used to prove errors are labelled, not scored 0."""

    provider_name = "failing"
    model_id = "failing-v0"
    api_version = "0"

    def __init__(self, exc: Exception = None) -> None:
        self._exc = exc or ProviderError("simulated API error")

    def generate(self, messages: List[Dict[str, str]]) -> str:
        raise self._exc


def _vllm_version() -> str:
    """vllm version string, or a marker if vllm is not importable.

    Used for the manifest's api_version field. Kept separate from engine
    construction: a missing vllm here degrades provenance, it never degrades a
    generate() call into a fallback (generate raises instead).
    """
    try:
        import vllm  # local import: importing this module must stay cheap
    except Exception as exc:  # noqa: BLE001 - version lookup is best-effort
        return "vllm-unavailable(%s)" % type(exc).__name__
    return str(getattr(vllm, "__version__", "unknown"))


def validate_chat_template_kwargs(value: Any) -> Dict[str, Any]:
    """Normalise per-model chat-template kwargs; ValueError names the offender.

    Accepts None (-> {}) or a dict with non-empty str keys and bool/int/str
    values - exactly what a chat template can branch on (e.g. skip_reasoning=True
    or enable_thinking=False). Anything else is refused rather than forwarded
    blindly into apply_chat_template.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(
            "chat_template_kwargs must be a dict, got %s" % type(value).__name__
        )
    out: Dict[str, Any] = {}
    for key, val in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(
                "chat_template_kwargs key %r must be a non-empty string" % (key,)
            )
        if not isinstance(val, (bool, int, str)):
            raise ValueError(
                "chat_template_kwargs[%r] must be a bool, int or str, got %s"
                % (key, type(val).__name__)
            )
        out[key] = val
    return out


def validate_stop_token_ids(value: Any) -> List[int]:
    """Normalise per-model stop token ids; ValueError names the offending value.

    Accepts None (-> []) or a list/tuple of distinct non-negative ints (booleans
    are not ints here). Token ids that a tokenizer does not report as eos still
    have to end a turn, so they are declared rather than guessed.
    """
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError(
            "stop_token_ids must be a list of ints, got %s" % type(value).__name__
        )
    out: List[int] = []
    for val in value:
        if isinstance(val, bool) or not isinstance(val, int):
            raise ValueError(
                "stop_token_ids entry %r must be an int, got %s"
                % (val, type(val).__name__)
            )
        if val < 0:
            raise ValueError("stop_token_ids entry %d must be non-negative" % val)
        if val in out:
            raise ValueError("stop_token_ids entry %d is duplicated" % val)
        out.append(val)
    return out


def _derive_model_id(model_path: str) -> str:
    """HF repo id verbatim, or the basename of a local directory."""
    p = str(model_path).rstrip(os.sep)
    if os.path.isdir(p):
        return os.path.basename(os.path.abspath(p))
    return p


class VLLMProvider(Provider):
    """Local open-weight model via the vllm offline engine (vllm.LLM).

    Deterministic by construction: temperature 0.0, top_p 1.0, a fixed seed and a
    fixed max_new_tokens, all passed to SamplingParams. The prompt is built with
    the model's own chat template through its tokenizer; a model with no chat
    template is an error, never a hand-rolled prompt format.

    Two optional per-model generation options exist for hybrid-thinking models:
    chat_template_kwargs (forwarded to apply_chat_template, e.g.
    skip_reasoning=True / enable_thinking=False) and stop_token_ids (extra
    end-of-turn ids for models whose turn enders are not the tokenizer's eos).
    Both are validated at construction and always reported by effective_params().

    The engine is constructed lazily on the first generate() call. Any failure to
    construct it (or to generate) is raised as ProviderError carrying the
    original error text - there is no fallback to a mock.
    """

    provider_name = "vllm"
    # top_p is not a constructor option in v0: greedy decoding is the frozen
    # setting. It lives here so _sampling_params and effective_params cannot
    # drift apart (the manifest must report the value actually sent).
    top_p = 1.0

    def __init__(
        self,
        model_path: str,
        max_new_tokens: int = 350,
        temperature: float = 0.0,
        seed: int = 20260922,
        gpu_memory_utilization: float = 0.85,
        chat_template_kwargs: Optional[Dict[str, Any]] = None,
        stop_token_ids: Optional[List[int]] = None,
    ) -> None:
        if not model_path or not str(model_path).strip():
            raise ValueError("VLLMProvider requires a non-empty model_path")
        # Validated at construction: a bad option must never reach a live engine.
        self.chat_template_kwargs = validate_chat_template_kwargs(chat_template_kwargs)
        self.stop_token_ids = validate_stop_token_ids(stop_token_ids)
        self.model_path = str(model_path)
        self.max_new_tokens = int(max_new_tokens)
        self.temperature = float(temperature)
        self.seed = int(seed)
        self.gpu_memory_utilization = float(gpu_memory_utilization)
        self.model_id = _derive_model_id(self.model_path)
        # Provenance of the prompt format, filled when the tokenizer is loaded.
        self.chat_template_source = None
        self.chat_template_sha256 = None
        self._api_version = None
        self._llm = None
        self._tokenizer = None

    @property
    def api_version(self) -> str:  # type: ignore[override]
        if self._api_version is None:
            self._api_version = _vllm_version()
        return self._api_version

    # -- engine ---------------------------------------------------------------

    def _build_engine(self):
        """Construct vllm.LLM. Errors propagate as ProviderError + original text."""
        try:
            from vllm import LLM
        except Exception as exc:
            raise ProviderError(
                "vllm import failed (%s: %s)" % (type(exc).__name__, exc)
            ) from exc
        try:
            return LLM(
                model=self.model_path,
                seed=self.seed,
                gpu_memory_utilization=self.gpu_memory_utilization,
                trust_remote_code=True,
            )
        except Exception as exc:
            raise ProviderError(
                "vllm engine construction failed for %r (%s: %s)"
                % (self.model_path, type(exc).__name__, exc)
            ) from exc

    def _load_tokenizer(self, llm):
        """Prefer the engine's own tokenizer; else transformers.AutoTokenizer."""
        getter = getattr(llm, "get_tokenizer", None)
        if callable(getter):
            try:
                return getter()
            except Exception as exc:
                raise ProviderError(
                    "vllm get_tokenizer failed for %r (%s: %s)"
                    % (self.model_path, type(exc).__name__, exc)
                ) from exc
        try:
            from transformers import AutoTokenizer

            return AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
        except Exception as exc:
            raise ProviderError(
                "tokenizer load failed for %r (%s: %s)"
                % (self.model_path, type(exc).__name__, exc)
            ) from exc

    def _ensure_engine(self):
        if self._llm is None:
            llm = self._build_engine()
            tokenizer = self._load_tokenizer(llm)
            template = getattr(tokenizer, "chat_template", None)
            if not template:
                raise ProviderError(
                    "model %r exposes no chat template; refusing to invent a prompt "
                    "format" % self.model_path
                )
            self.chat_template_source = "tokenizer.chat_template"
            self.chat_template_sha256 = hashlib.sha256(
                str(template).encode("utf-8")
            ).hexdigest()
            self._llm = llm
            self._tokenizer = tokenizer
        return self._llm, self._tokenizer

    # -- generation -----------------------------------------------------------

    def _sampling_params(self):
        try:
            from vllm import SamplingParams
        except Exception as exc:
            raise ProviderError(
                "vllm import failed (%s: %s)" % (type(exc).__name__, exc)
            ) from exc
        kwargs: Dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_new_tokens,
            "seed": self.seed,
        }
        # Only sent when declared, so an undeclared model keeps the exact call
        # shape it had before this option existed.
        if self.stop_token_ids:
            kwargs["stop_token_ids"] = list(self.stop_token_ids)
        return SamplingParams(**kwargs)

    def effective_params(self) -> Dict[str, object]:
        """Exactly what goes into SamplingParams/apply_chat_template.

        Both option keys are always reported (empty dict / empty list when
        undeclared), so every manifest from now on states what was applied
        instead of leaving it to be inferred from the model list.
        """
        return {
            "max_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "chat_template_kwargs": dict(self.chat_template_kwargs),
            "stop_token_ids": list(self.stop_token_ids),
        }

    def build_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Apply the model's chat template, with a generation prompt appended.

        Declared chat_template_kwargs are forwarded verbatim (e.g. the hybrid
        thinking switch some templates read); the template itself - and its
        sha256 provenance - is unchanged.
        """
        _, tokenizer = self._ensure_engine()
        try:
            return tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                **self.chat_template_kwargs,
            )
        except Exception as exc:
            raise ProviderError(
                "chat template application failed (%s: %s)" % (type(exc).__name__, exc)
            ) from exc

    def generate(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            raise ProviderError("VLLMProvider.generate called with no messages")
        prompt = self.build_prompt(messages)
        llm, _ = self._ensure_engine()
        params = self._sampling_params()
        try:
            outputs = llm.generate([prompt], params)
        except Exception as exc:
            raise ProviderError(
                "vllm generate failed (%s: %s)" % (type(exc).__name__, exc)
            ) from exc
        try:
            text = outputs[0].outputs[0].text
        except Exception as exc:
            raise ProviderError(
                "unexpected vllm output shape (%s: %s)" % (type(exc).__name__, exc)
            ) from exc
        if not isinstance(text, str) or not text.strip():
            raise ProviderError(
                "vllm returned an empty completion for %r" % self.model_id
            )
        return text.strip()


PROVIDERS = {"mock": MockProvider, "vllm": VLLMProvider}


def get_provider(name: str, **opts) -> Provider:
    """Instantiate a provider by name; **opts are the provider's ctor kwargs."""
    if name not in PROVIDERS:
        raise ValueError(
            "unknown provider %r (available: %s)" % (name, ", ".join(sorted(PROVIDERS)))
        )
    try:
        return PROVIDERS[name](**opts)
    except TypeError as exc:
        raise ValueError(
            "bad options for provider %r: %s" % (name, exc)
        ) from exc
