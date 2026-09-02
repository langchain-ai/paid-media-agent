"""Model capability registry and model-aware tool selection middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from enum import StrEnum
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    LLMToolSelectorMiddleware,
    ProviderToolSearchMiddleware,
)
from langchain.agents.middleware.types import ModelRequest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict

from paid_media_agent.config import ModelConfig


class SelectionStrategy(StrEnum):
    PROVIDER_NATIVE = "provider_native"
    PORTABLE_SELECTOR = "portable_selector"
    NONE = "none"


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_calling: bool
    structured_output: bool
    native_tool_search: bool
    streaming_tool_calls: bool
    integration_package: str
    notes: str = ""
    verified: bool = False
    """True only for entries checked against current provider documentation."""


_ANTHROPIC = ModelCapabilities(
    tool_calling=True,
    structured_output=True,
    native_tool_search=True,
    streaming_tool_calls=True,
    integration_package="langchain-anthropic",
    notes="Anthropic tool search (bm25/regex 2025-11-19) per current Claude docs.",
    verified=True,
)
_OPENAI = ModelCapabilities(
    tool_calling=True,
    structured_output=True,
    native_tool_search=True,
    streaming_tool_calls=True,
    integration_package="langchain-openai",
    notes="OpenAI Responses tool_search is documented for gpt-5.4 and later.",
    verified=True,
)
_GOOGLE = ModelCapabilities(
    tool_calling=True,
    structured_output=True,
    native_tool_search=False,
    streaming_tool_calls=True,
    integration_package="langchain-google-genai",
    notes="No provider-side deferred tool search; portable selector path.",
    verified=True,
)
_GATEWAY = ModelCapabilities(
    tool_calling=True,
    structured_output=True,
    native_tool_search=False,
    streaming_tool_calls=True,
    integration_package="langchain-openai",
    notes="LangSmith LLM Gateway (langsmith:provider/model). Standard endpoint; portable selector path.",
    verified=True,
)
_SCRIPTED = ModelCapabilities(
    tool_calling=True,
    structured_output=False,
    native_tool_search=False,
    streaming_tool_calls=False,
    integration_package="paid-media-agent",
    notes="Deterministic scripted model for offline demo and tests. Binds all tools directly.",
    verified=True,
)

CAPABILITY_REGISTRY: dict[str, ModelCapabilities] = {
    "anthropic:claude-sonnet-4-6": _ANTHROPIC,
    "anthropic:claude-opus-4-6": _ANTHROPIC,
    "anthropic:claude-opus-4-7": _ANTHROPIC,
    "anthropic:claude-opus-4-8": _ANTHROPIC,
    "anthropic:claude-opus-5": _ANTHROPIC,
    "anthropic:claude-fable-5": _ANTHROPIC,
    "anthropic:claude-fable-5-1": _ANTHROPIC,
    "anthropic:claude-haiku-4-5-20251001": _ANTHROPIC,
    "anthropic:claude-sonnet-4-5-20250929": _ANTHROPIC,
    "anthropic:claude-opus-4-5-20251101": _ANTHROPIC,
    "openai:gpt-5.4": _OPENAI,
    "openai:gpt-5.4-mini": _OPENAI,
    "openai:gpt-5.5": _OPENAI,
    "openai:gpt-5.5-mini": _OPENAI,
    "openai:gpt-5.6": _OPENAI,
    "google_genai:gemini-3-flash": _GOOGLE,
    "google_genai:gemini-3.6-flash": _GOOGLE,
    "scripted:demo": _SCRIPTED,
    "langsmith:anthropic/claude-sonnet-4-6": _GATEWAY,
    "langsmith:anthropic/claude-opus-5": _GATEWAY,
    "langsmith:openai/gpt-5.5": _GATEWAY,
    "langsmith:openai/gpt-5.4-mini": _GATEWAY,
    "langsmith:moonshotai/kimi-k3": _GATEWAY,
}

UNKNOWN_MODEL = ModelCapabilities(
    tool_calling=True,
    structured_output=False,
    native_tool_search=False,
    streaming_tool_calls=False,
    integration_package="",
    notes="Unknown model: portable selector path, no native search claims.",
    verified=False,
)

INTEGRATION_PACKAGES: dict[str, str] = {
    "anthropic": "langchain-anthropic",
    "openai": "langchain-openai",
    "google_genai": "langchain-google-genai",
    "langsmith": "langchain-openai",
}


def capabilities_for(config: ModelConfig) -> ModelCapabilities:
    """Exact registry lookup. No substring matching on provider or model names."""
    return CAPABILITY_REGISTRY.get(config.spec, UNKNOWN_MODEL)


class SelectionPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy: SelectionStrategy
    reason: str
    max_tools: int
    selector_model: str | None = None


def plan_selection(config: ModelConfig, *, max_tools: int) -> SelectionPlan:
    caps = capabilities_for(config)
    if config.provider == "langsmith" and not caps.verified:
        # Any gateway model is reachable; only the registered ones carry a verified note.
        caps = _GATEWAY
    if config.provider == "scripted":
        return SelectionPlan(
            strategy=SelectionStrategy.NONE,
            reason="scripted model binds all tools",
            max_tools=max_tools,
        )
    if caps.native_tool_search and config.base_url is None:
        return SelectionPlan(
            strategy=SelectionStrategy.PROVIDER_NATIVE,
            reason=f"{config.spec} is registered with verified provider tool search",
            max_tools=max_tools,
        )
    if caps.native_tool_search and config.base_url is not None:
        reason = "custom base URL: provider-native search is not assumed through a proxy"
    elif not caps.verified:
        reason = "model not in the capability registry; portable selector used"
    else:
        reason = f"{config.spec} has no provider-native tool search"
    return SelectionPlan(
        strategy=SelectionStrategy.PORTABLE_SELECTOR,
        reason=reason,
        max_tools=max_tools,
        selector_model=config.tool_selector_model,
    )


class PortableToolSelectorMiddleware(LLMToolSelectorMiddleware):
    """LLMToolSelectorMiddleware with a fail-closed fallback for hallucinated selections.

    The framework raises when the selector names a tool that is not bound. Instead of aborting
    the run, this turn proceeds with only the always-included core tools, so the model must
    discover again. Unknown names can never widen the surface.
    """

    name = "PaidMediaPortableToolSelector"

    def _core_only(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        keep = [
            t for t in request.tools if not isinstance(t, BaseTool) or t.name in self.always_include
        ]
        return request.override(tools=keep)

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Any],
    ) -> Any:
        try:
            return super().wrap_model_call(request, handler)
        except ValueError as exc:
            if "invalid tools" not in str(exc):
                raise
            return handler(self._core_only(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[Any]],
    ) -> Any:
        try:
            return await super().awrap_model_call(request, handler)
        except ValueError as exc:
            if "invalid tools" not in str(exc):
                raise
            return await handler(self._core_only(request))


class LenientStructuredOutputModel(BaseChatModel):
    """Delegate to a chat model but run structured output through function calling.

    `LLMToolSelectorMiddleware` asks the selector for a JSON object whose schema has no
    `additionalProperties: false`. OpenAI-format strict schemas (which the LangSmith Gateway
    applies to `langsmith:` models) reject that, so the selection call uses function calling,
    which every gateway provider translates.
    """

    inner: BaseChatModel

    @property
    def _llm_type(self) -> str:
        return f"lenient-{self.inner._llm_type}"

    def _get_ls_params(self, stop: list[str] | None = None, **kwargs: Any) -> Any:
        return self.inner._get_ls_params(stop=stop, **kwargs)

    def bind_tools(
        self, tools: Any, *, tool_choice: Any = None, **kwargs: Any
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self.inner.bind_tools(tools, tool_choice=tool_choice, **kwargs)

    def with_structured_output(
        self, schema: Any, **kwargs: Any
    ) -> Runnable[LanguageModelInput, Any]:
        kwargs.pop("method", None)
        kwargs.pop("strict", None)
        try:
            return self.inner.with_structured_output(schema, method="function_calling", **kwargs)
        except TypeError:
            return self.inner.with_structured_output(schema, **kwargs)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,  # noqa: ARG002 - base signature
        **kwargs: Any,
    ) -> ChatResult:
        message = self.inner.invoke(messages, stop=stop, **kwargs)
        return ChatResult(generations=[ChatGeneration(message=message)])


def lenient_selector(model: BaseChatModel, config: ModelConfig) -> BaseChatModel | None:
    """Selector model for the portable path, or None to let the middleware reuse the main model."""
    if config.provider == "langsmith":
        return LenientStructuredOutputModel(inner=model)
    return None


def build_selection_middleware(
    plan: SelectionPlan,
    *,
    searchable_tool_names: Sequence[str],
    always_include: Sequence[str],
    selector_model: BaseChatModel | None = None,
) -> tuple[AgentMiddleware[Any, Any, Any], ...]:
    if not searchable_tool_names or plan.strategy is SelectionStrategy.NONE:
        return ()
    if plan.strategy is SelectionStrategy.PROVIDER_NATIVE:
        return (ProviderToolSearchMiddleware(searchable_tools=list(searchable_tool_names)),)
    return (
        PortableToolSelectorMiddleware(
            model=selector_model if selector_model is not None else plan.selector_model,
            max_tools=plan.max_tools,
            always_include=list(always_include),
            on_parsing_failure="none",
        ),
    )
