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

SCHEMA = {
    "title": "ToolSelectionResponse",
    "type": "object",
    "properties": {"tools": {"type": "array", "items": {"type": "string"}}},
}


class Recording(GenericFakeChatModel):
    """Answers a bound call with `reply`, and records how the tools were bound."""

    bindings: list[dict[str, Any]] = []
    reply: AIMessage | None = None

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        self.bindings.append({"tools": tools, **kwargs})
        reply = self.reply
        return RunnableLambda(lambda _input: reply)


def _call(name: str, args: dict[str, Any]) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "c1"}])


def test_gateway_selector_offers_the_selection_without_forcing_it() -> None:
    picked = {"tools": ["google_ads__get_campaign_performance"]}
    inner = Recording(
        messages=iter([AIMessage(content="ok")]), reply=_call("ToolSelectionResponse", picked)
    )
    wrapped = lenient_selector(inner, ModelConfig.parse("langsmith:anthropic/claude-opus-5-5"))
    assert isinstance(wrapped, LenientStructuredOutputModel)
    selection = wrapped.with_structured_output(SCHEMA, method="json_schema", strict=True)
    assert selection.invoke("x") == picked
    binding = inner.bindings[-1]
    assert binding["tool_choice"] == "auto", "always-thinking models refuse a forced tool_choice"
    assert "strict" not in binding, "strict json_schema never reaches the gateway"
    assert wrapped.invoke("hello").content == "ok", "generation still delegates to the inner model"


def test_a_reply_without_the_call_is_a_parsing_failure_not_an_error() -> None:
    inner = Recording(messages=iter([]), reply=AIMessage(content="I would pick the Google tools."))
    wrapped = lenient_selector(inner, ModelConfig.parse("langsmith:anthropic/claude-opus-5-5"))
    assert wrapped is not None
    assert wrapped.with_structured_output(SCHEMA).invoke("x") is None


def test_native_providers_keep_their_own_selector() -> None:
    inner = Recording(messages=iter([]))
    assert lenient_selector(inner, ModelConfig.parse("google_genai:gemini-3-flash")) is None
