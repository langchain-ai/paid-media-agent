"""One shared agent assembly. Runtime adapters compose these components; they never fork them."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deepagents.backends.protocol import BackendProtocol
from langchain.agents.middleware import (
    AgentMiddleware,
    InterruptOnConfig,
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from paid_media_agent.config import ModelConfig, Settings
from paid_media_agent.middleware.authorization import (
    HIDDEN_BUILTIN_TOOLS,
    InvocationGuardMiddleware,
    ToolSurfacePolicy,
)
from paid_media_agent.middleware.current_date import CurrentDateMiddleware
from paid_media_agent.middleware.offload import ResultOffloadMiddleware
from paid_media_agent.middleware.redaction import RedactionMiddleware
from paid_media_agent.middleware.timeout import ModelTimeoutMiddleware
from paid_media_agent.middleware.tool_selection import (
    SelectionPlan,
    build_selection_middleware,
    lenient_selector,
    plan_selection,
)
from paid_media_agent.runtime.profiles import RuntimeProfile
from paid_media_agent.tools.analysis import COMPARE_PERIODS_TOOL, build_compare_periods_tool
from paid_media_agent.tools.catalog import AuthorizedToolCatalog
from paid_media_agent.tools.discovery import (
    DISCOVER_TOOLS_TOOL,
    LIST_ACCOUNTS_TOOL,
    build_discover_tools_tool,
    build_list_accounts_tool,
)
from paid_media_agent.tools.reads import ReadDispatcher, build_platform_read_tools
from paid_media_agent.tools.reports import RENDER_REPORT_TOOL, build_render_report_tool
from paid_media_agent.tools.summary import SUMMARIZE_WINDOW_TOOL, build_summarize_window_tool
from paid_media_agent.tools.writes import (
    DISCOVER_WRITE_OPERATIONS_TOOL,
    EXECUTE_CHANGE_TOOL,
    GET_PROPOSAL_TOOL,
    PROPOSE_CHANGE_TOOL,
    ProposalService,
    WriteExecutor,
    build_execute_interrupt,
    build_write_tools,
)

# Deep Agents filesystem tools the model keeps for skills, wiki pages, and workspace notes.
FILESYSTEM_TOOLS: tuple[str, ...] = ("ls", "read_file", "write_file", "edit_file", "glob", "grep")
CORE_TOOLS: tuple[str, ...] = (
    LIST_ACCOUNTS_TOOL,
    DISCOVER_TOOLS_TOOL,
    COMPARE_PERIODS_TOOL,
    SUMMARIZE_WINDOW_TOOL,
    RENDER_REPORT_TOOL,
)
WRITE_TOOLS: tuple[str, ...] = (
    DISCOVER_WRITE_OPERATIONS_TOOL,
    PROPOSE_CHANGE_TOOL,
    EXECUTE_CHANGE_TOOL,
    GET_PROPOSAL_TOOL,
)
MODEL_RETRY_ATTEMPTS = 2


@dataclass(frozen=True)
class AssemblyMetadata:
    model_spec: str
    selection: SelectionPlan
    catalog_revision: str
    catalog_source: str
    read_tool_count: int
    mutation_entry_count: int
    denied_entry_count: int
    tool_names: tuple[str, ...]
    run_mode: str
    write_gate: str
    write_policy_issues: tuple[str, ...]


@dataclass(frozen=True)
class AgentComponents:
    model: BaseChatModel
    tools: tuple[BaseTool, ...]
    middleware: tuple[AgentMiddleware[Any, Any, Any], ...]
    interrupt_on: Mapping[str, InterruptOnConfig]
    response_format: type[BaseModel] | None
    system_prompt: str
    skills: tuple[str, ...]
    backend: BackendProtocol | None
    """The model's filesystem; None means the repository (see runtime.sandbox)."""
    metadata: AssemblyMetadata
    proposal_service: ProposalService
    write_executor: WriteExecutor
    read_dispatcher: ReadDispatcher


@dataclass(frozen=True)
class AssemblyServices:
    """Host services created once per assembly so surfaces can reuse the same objects."""

    dispatcher: ReadDispatcher
    proposal_service: ProposalService
    executor: WriteExecutor


def _build_services(settings: Settings, runtime: RuntimeProfile) -> AssemblyServices:
    dispatcher = ReadDispatcher(
        catalog_provider=runtime.catalog_provider,
        accounts=runtime.accounts,
        provider=runtime.read_provider,
        artifacts=runtime.artifacts,
    )
    service = ProposalService(
        catalog_provider=runtime.catalog_provider,
        accounts=runtime.accounts,
        write_policy=runtime.write_policy,
        approval_policy=runtime.approval_policy,
        signer=runtime.signer,
        proposals=runtime.proposals,
        approvals=runtime.approvals,
        read_provider=runtime.read_provider,
    )
    executor = WriteExecutor(
        service=service,
        catalog_provider=runtime.catalog_provider,
        write_policy=runtime.write_policy,
        accounts=runtime.accounts,
        signer=runtime.signer,
        approvals=runtime.approvals,
        receipts=runtime.receipts,
        provider=runtime.write_provider,
        read_provider=runtime.read_provider,
        gate=runtime.write_gate(settings),
    )
    return AssemblyServices(dispatcher=dispatcher, proposal_service=service, executor=executor)


def resolve_model(
    config: ModelConfig,
    override: BaseChatModel | None = None,
    *,
    api_key_env: str | None = None,
    timeout_seconds: int = 120,
) -> BaseChatModel:
    """Initialize the configured provider model directly. No gateway, no proxy assumptions.

    `api_key_env` names the environment variable holding the key when the provider does not read
    its default one (for example an OpenAI-compatible endpoint with its own key). Every request
    gets a timeout and two SDK retries; the retry middleware handles what remains.
    """
    if override is not None:
        return override
    import os  # noqa: PLC0415

    from langchain.chat_models import init_chat_model  # noqa: PLC0415 - optional provider packages

    kwargs: dict[str, Any] = {"timeout": timeout_seconds, "max_retries": 2}
    if config.base_url is not None:
        kwargs["base_url"] = str(config.base_url)
    if api_key_env and os.environ.get(api_key_env):
        kwargs["api_key"] = os.environ[api_key_env]
    resolved: BaseChatModel = init_chat_model(config.spec, **kwargs)
    return resolved


def load_system_prompt(project_root: Path) -> str:
    return (project_root / "instructions.md").read_text(encoding="utf-8")


def build_agent_components(
    *,
    settings: Settings,
    runtime: RuntimeProfile,
    catalog: AuthorizedToolCatalog,
    model: BaseChatModel | None = None,
    selector_model: BaseChatModel | None = None,
    system_prompt: str | None = None,
) -> AgentComponents:
    """Compose model, tools, middleware, and interrupt policy. No network, no global state."""
    model_config = settings.model_settings()
    resolved_model = resolve_model(
        model_config,
        model,
        api_key_env=settings.paid_media_model_api_key_env,
        timeout_seconds=settings.paid_media_model_timeout_seconds,
    )
    services = _build_services(settings, runtime)

    platform_tools = build_platform_read_tools(catalog, services.dispatcher)
    core_tools: list[BaseTool] = [
        build_list_accounts_tool(runtime.accounts),
        build_discover_tools_tool(runtime.catalog_provider),
        build_compare_periods_tool(runtime.artifacts),
        build_summarize_window_tool(runtime.artifacts),
        build_render_report_tool(runtime.artifacts, pdf_engine=runtime.pdf_engine),
    ]
    write_tools: list[BaseTool] = []
    if runtime.run_mode == "conversation":
        write_tools = build_write_tools(services.proposal_service, services.executor)
    tools: tuple[BaseTool, ...] = (*core_tools, *write_tools, *platform_tools)

    allowed = frozenset({*FILESYSTEM_TOOLS, *(t.name for t in tools)})
    surface = ToolSurfacePolicy(
        allowed_tool_names=allowed, hidden_tool_names=HIDDEN_BUILTIN_TOOLS, mode=runtime.run_mode
    )
    plan = plan_selection(model_config, max_tools=settings.paid_media_max_selected_tools)
    selection = build_selection_middleware(
        plan,
        searchable_tool_names=[t.name for t in platform_tools],
        always_include=[
            *FILESYSTEM_TOOLS,
            *(t.name for t in core_tools),
            *(t.name for t in write_tools),
        ],
        selector_model=selector_model or lenient_selector(resolved_model, model_config),
    )
    secrets = tuple(s for s in _secret_values(settings) if s)
    retry: tuple[AgentMiddleware[Any, Any, Any], ...] = ()
    if model_config.provider != "scripted":
        # Transient model failures should not kill a run; bounded, and tool effects never repeat.
        # A run also ends after a fixed number of model calls instead of looping on tools.
        retry = (
            ModelRetryMiddleware(max_retries=MODEL_RETRY_ATTEMPTS, on_failure="continue"),
            ModelTimeoutMiddleware(settings.paid_media_model_timeout_seconds),
            ModelCallLimitMiddleware(
                run_limit=settings.paid_media_max_model_calls, exit_behavior="end"
            ),
        )
    middleware: tuple[AgentMiddleware[Any, Any, Any], ...] = (
        *retry,
        CurrentDateMiddleware(),
        *selection,
        InvocationGuardMiddleware(surface=surface, catalog_provider=runtime.catalog_provider),
        ResultOffloadMiddleware(
            runtime.artifacts, max_chars=settings.paid_media_result_offload_chars
        ),
        RedactionMiddleware(secrets=(*secrets, *runtime.extra_secrets)),
    )
    interrupt_on: dict[str, InterruptOnConfig] = {}
    if write_tools:
        interrupt_on[EXECUTE_CHANGE_TOOL] = build_execute_interrupt(services.proposal_service)

    prompt = system_prompt
    if prompt is None:
        root = runtime.skills_root or Path.cwd()
        prompt = load_system_prompt(root) if (root / "instructions.md").exists() else ""
    metadata = AssemblyMetadata(
        model_spec=model_config.spec,
        selection=plan,
        catalog_revision=catalog.revision,
        catalog_source=catalog.source,
        read_tool_count=len(platform_tools),
        mutation_entry_count=len(catalog.mutation_entries()),
        denied_entry_count=len(catalog.denied_entries()),
        tool_names=tuple(t.name for t in tools),
        run_mode=runtime.run_mode,
        write_gate=services.executor.gate.describe(),
        write_policy_issues=tuple(
            f"{i.tool_name}: {i.reason}" for i in runtime.write_policy_issues
        ),
    )
    return AgentComponents(
        model=resolved_model,
        tools=tools,
        middleware=middleware,
        interrupt_on=interrupt_on,
        response_format=None,
        system_prompt=prompt,
        skills=("/skills/",),
        backend=runtime.backend.model_fs if runtime.backend is not None else None,
        metadata=metadata,
        proposal_service=services.proposal_service,
        write_executor=services.executor,
        read_dispatcher=services.dispatcher,
    )


def _secret_values(settings: Settings) -> tuple[str, ...]:
    values: list[str] = []
    for secret in (
        settings.pipeboard_api_token,
        settings.paid_media_approval_signing_key,
        settings.slack_bot_token,
        settings.slack_app_token,
        settings.slack_signing_secret,
        settings.database_url,
        settings.paid_media_api_tokens,
    ):
        if secret is not None:
            values.append(secret.get_secret_value())
    return tuple(values)
