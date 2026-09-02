from __future__ import annotations

from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from paid_media_agent.config import ModelConfig
from paid_media_agent.middleware.tool_selection import (
    LenientStructuredOutputModel,
    lenient_selector,
)


class Recording(GenericFakeChatModel):
    calls: list[dict[str, Any]] = []

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return RunnableLambda(lambda _input: {"tools": ["google_ads__get_campaign_performance"]})


def test_lenient_selector_forces_function_calling_for_gateway_models() -> None:
    inner = Recording(messages=iter([AIMessage(content="ok")]))
    wrapped = lenient_selector(inner, ModelConfig.parse("langsmith:anthropic/claude-sonnet-4-6"))
    assert isinstance(wrapped, LenientStructuredOutputModel)
    selection = wrapped.with_structured_output(
        {"type": "object"}, method="json_schema", strict=True
    )
    assert selection.invoke("x") == {"tools": ["google_ads__get_campaign_performance"]}
    assert inner.calls == [{"method": "function_calling"}], (
        "strict json_schema never reaches the gateway"
    )
    assert wrapped.invoke("hello").content == "ok", "generation still delegates to the inner model"


def test_native_providers_keep_their_own_selector() -> None:
    inner = Recording(messages=iter([]))
    assert lenient_selector(inner, ModelConfig.parse("google_genai:gemini-3-flash")) is None
