"""Provider-shaped fake models for the tool-selection matrix. They never call a network."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool


class RecordingProviderModel(BaseChatModel):
    """Looks like a given provider to LangChain and records what it was asked to bind."""

    provider: str
    model_name: str
    responses: list[AIMessage]
    bound_batches: list[list[Any]] = []
    structured_selection: list[str] = []
    invocations: int = 0

    @property
    def _llm_type(self) -> str:
        return f"fake-{self.provider}"

    def _get_ls_params(self, stop: list[str] | None = None, **kwargs: Any) -> Any:  # noqa: ARG002
        return {
            "ls_provider": self.provider,
            "ls_model_name": self.model_name,
            "ls_model_type": "chat",
        }

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,  # noqa: ARG002 - provider signature
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        batch: list[Any] = []
        for tool in tools:
            if isinstance(tool, BaseTool):
                spec = convert_to_openai_tool(tool)
                if tool.extras and tool.extras.get("defer_loading"):
                    spec["defer_loading"] = True
                batch.append(spec)
            else:
                batch.append(tool)
        self.bound_batches.append(batch)
        return self.bind(tools=batch, **kwargs)

    def with_structured_output(
        self,
        schema: Any,  # noqa: ARG002 - the fake ignores the schema and returns the scripted selection
        **kwargs: Any,  # noqa: ARG002
    ) -> Runnable[LanguageModelInput, Any]:
        selection = list(self.structured_selection)
        return RunnableLambda(lambda _input: {"tools": selection})

    def _generate(
        self,
        messages: list[BaseMessage],  # noqa: ARG002 - fake returns scripted output
        stop: list[str] | None = None,  # noqa: ARG002 - provider signature
        run_manager: CallbackManagerForLLMRun | None = None,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> ChatResult:
        index = min(self.invocations, len(self.responses) - 1)
        self.invocations += 1
        return ChatResult(generations=[ChatGeneration(message=self.responses[index])])
