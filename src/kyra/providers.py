"""Model providers for pipeline v0.

Only a deterministic offline MockProvider is implemented. Real API providers are
added later by subclassing Provider; nothing in this module touches the network.
"""

from __future__ import annotations

import hashlib
from typing import Dict, List


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


PROVIDERS = {"mock": MockProvider}


def get_provider(name: str) -> Provider:
    if name not in PROVIDERS:
        raise ValueError(
            "unknown provider %r (available: %s)" % (name, ", ".join(sorted(PROVIDERS)))
        )
    return PROVIDERS[name]()
