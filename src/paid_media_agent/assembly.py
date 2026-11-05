"""One shared agent assembly. Runtime adapters compose these components; they never fork them."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    InterruptOnConfig,
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from paid_media_agent.config import ModelConfig, Settings, template_marker
from paid_media_agent.middleware.authorization import (
    HIDDEN_BUILTIN_TOOLS,
    InvocationGuardMiddleware,
    ToolSurfacePolicy,
)
from paid_media_agent.middleware.current_date import CurrentDateMiddleware
from paid_media_agent.middleware.footer import RunFooterMiddleware
from paid_media_agent.middleware.housekeeping import HousekeepingMiddleware
from paid_media_agent.middleware.meter import Meter, MeterMiddleware
from paid_media_agent.middleware.offload import ResultOffloadMiddleware
from paid_media_agent.middleware.redaction import RedactionMiddleware
from paid_media_agent.middleware.timeout import ModelTimeoutMiddleware
from paid_media_agent.middleware.tool_selection import (
    SelectionPlan,
    SelectionStrategy,
    build_selection_middleware,
    lenient_selector,
    plan_selection,
)
from paid_media_agent.runtime.profiles import RuntimeProfile
from paid_media_agent.subagents import ASYNC_TASK_TOOLS, HELPER_FILESYSTEM_TOOLS, helper_specs
from paid_media_agent.tools.catalog import AuthorizedToolCatalog
from paid_media_agent.tools.check_ins import build_check_in_tools
from paid_media_agent.tools.compare_periods import COMPARE_PERIODS_TOOL, build_compare_periods_tool
from paid_media_agent.tools.discovery import (
    DISCOVER_TOOLS_TOOL,
    LIST_ACCOUNTS_TOOL,
    build_discover_tools_tool,
    build_list_accounts_tool,
)
from paid_media_agent.tools.reads import ReadDispatcher, build_platform_read_tools
from paid_media_agent.tools.reports import RENDER_REPORT_TOOL, build_render_report_tool
from paid_media_agent.tools.summary import SUMMARIZE_WINDOW_TOOL, build_summarize_window_tool
from paid_media_agent.tools.write_tools import build_execute_interrupt, build_write_tools
from paid_media_agent.tools.writes import (
    DISCOVER_WRITE_OPERATIONS_TOOL,
    EXECUTE_CHANGE_TOOL,
    GET_PROPOSAL_TOOL,
    PROPOSE_CHANGE_TOOL,
    ProposalService,
    WriteExecutor,
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
#: Providers whose LangChain chat model takes `reasoning_effort` (the gateway is ChatOpenAI).
EFFORT_PROVIDERS = frozenset({"anthropic", "openai", "langsmith"})


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
    write_gate: str
    write_policy_issues: tuple[str, ...]


@dataclass(frozen=True)
class AgentComponents:
    model: BaseChatModel
    tools: tuple[BaseTool, ...]
    middleware: tuple[AgentMiddleware[Any, Any, Any], ...]
    interrupt_on: Mapping[str, InterruptOnConfig]
    system_prompt: str
    skills: tuple[str, ...]
    metadata: AssemblyMetadata
    run_metadata: Mapping[str, str]
    """Root-run trace metadata: the template marker, or empty when the operator turned it off."""
    proposal_service: ProposalService
    write_executor: WriteExecutor
    read_dispatcher: ReadDispatcher
    meter: Meter
    helpers: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    """Background helper specs (`subagents.py`), keyed by name. Empty off Managed Deep Agents."""

    def helper(self, name: str) -> dict[str, Any]:
        """One helper's spec for `agent.py`, which adds the literal `name` and `"async"`."""
        return dict(self.helpers[name])


@dataclass(frozen=True)
class AssemblyServices:
    """Host services created once per assembly so surfaces can reuse the same objects."""

    read_dispatcher: ReadDispatcher
    proposal_service: ProposalService
    write_executor: WriteExecutor


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
    return AssemblyServices(
        read_dispatcher=dispatcher, proposal_service=service, write_executor=executor
    )


def resolve_model(
    config: ModelConfig,
    override: BaseChatModel | None = None,
    *,
    api_key_env: str | None = None,
    timeout_seconds: int = 120,
    effort: str | None = None,
) -> BaseChatModel:
    """Initialize the configured provider model. No implicit gateway: `langsmith:` specs opt in.

    `api_key_env` names the environment variable holding the key when the provider does not read
    its default one (for example an OpenAI-compatible endpoint with its own key). Every request
    gets a timeout and two SDK retries; the retry middleware handles what remains. `effort` is
    the reasoning effort, for providers that take one (`EFFORT_PROVIDERS`).
    """
    if override is not None:
        return override
    import os

    from langchain.chat_models import init_chat_model

    kwargs: dict[str, Any] = {"timeout": timeout_seconds, "max_retries": 2}
    if config.base_url is not None:
        kwargs["base_url"] = str(config.base_url)
    if api_key_env and os.environ.get(api_key_env):
        kwargs["api_key"] = os.environ[api_key_env]
    if effort is not None:
        if config.provider not in EFFORT_PROVIDERS:
            raise ValueError(
                f"PAID_MEDIA_MODEL_EFFORT is not supported for {config.provider}; unset it"
            )
        kwargs["reasoning_effort"] = effort
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
    managed: bool = False,
) -> AgentComponents:
    """Compose model, tools, middleware, and interrupt policy. No network, no global state.

    `managed` is Managed Deep Agents: the lead also gets check-ins and background helpers, which
    need its runtime schedules and Agent Server. Every other path leaves both out.
    """
    model_config = settings.model_settings()
    resolved_model = resolve_model(
        model_config,
        model,
        api_key_env=settings.paid_media_model_api_key_env,
        timeout_seconds=settings.paid_media_model_timeout_seconds,
        effort=settings.paid_media_model_effort,
    )
    services = _build_services(settings, runtime)

    project_root = runtime.skills_root or Path.cwd()

    platform_tools = build_platform_read_tools(catalog, services.read_dispatcher)
    render_tool = build_render_report_tool(runtime.artifacts)
    analysis_tools: list[BaseTool] = [
        build_list_accounts_tool(runtime.accounts),
        build_discover_tools_tool(runtime.catalog_provider),
        build_compare_periods_tool(runtime.artifacts),
        build_summarize_window_tool(runtime.artifacts),
    ]
    core_tools: list[BaseTool] = [*analysis_tools, render_tool]
    if managed:
        core_tools += build_check_in_tools()
    write_tools = build_write_tools(services.proposal_service, services.write_executor)
    tools: tuple[BaseTool, ...] = (*core_tools, *write_tools, *platform_tools)

    plan = plan_selection(model_config, max_tools=settings.paid_media_max_selected_tools)
    selection_model = selector_model
    if selection_model is None and plan.strategy is SelectionStrategy.PORTABLE_SELECTOR:
        if plan.selector_model:
            selector_config = ModelConfig.parse(plan.selector_model)
            selected = resolve_model(
                selector_config, timeout_seconds=settings.paid_media_model_timeout_seconds
            )
            selection_model = lenient_selector(selected, selector_config) or selected
        else:
            selection_model = lenient_selector(resolved_model, model_config)
    secrets = tuple(s for s in (*_secret_values(settings), *runtime.extra_secrets) if s)
    platform_names = [t.name for t in platform_tools]

    def guards(
        visible: Sequence[str], always: Sequence[str]
    ) -> list[AgentMiddleware[Any, Any, Any]]:
        """The stack every agent runs with, lead or helper: bounded model calls, today's date, tool
        selection, the invocation guard, result offload, and redaction."""
        bounded: list[AgentMiddleware[Any, Any, Any]] = []
        if model_config.provider != "scripted":
            # Transient model failures should not kill a run; bounded, and tool effects never
            # repeat. A run also ends after a fixed number of model calls instead of looping.
            bounded = [
                ModelRetryMiddleware(max_retries=MODEL_RETRY_ATTEMPTS, on_failure="continue"),
                ModelTimeoutMiddleware(settings.paid_media_model_timeout_seconds),
                ModelCallLimitMiddleware(
                    run_limit=settings.paid_media_max_model_calls, exit_behavior="end"
                ),
            ]
        surface = ToolSurfacePolicy(
            allowed_tool_names=frozenset(visible), hidden_tool_names=HIDDEN_BUILTIN_TOOLS
        )
        return [
            *bounded,
            CurrentDateMiddleware(),
            *build_selection_middleware(
                plan,
                searchable_tool_names=platform_names,
                always_include=list(always),
                selector_model=selection_model,
            ),
            InvocationGuardMiddleware(surface=surface, catalog_provider=runtime.catalog_provider),
            ResultOffloadMiddleware(
                runtime.artifacts, max_chars=settings.paid_media_result_offload_chars
            ),
            RedactionMiddleware(secrets=secrets),
        ]

    background = ASYNC_TASK_TOOLS if managed else ()
    lead_always = [
        *FILESYSTEM_TOOLS,
        *(t.name for t in core_tools),
        *(t.name for t in write_tools),
        *background,
    ]
    meter = Meter(default_model=model_config.model)
    # Housekeeping first: its run ends in `before_agent`, before anything else does work.
    middleware: tuple[AgentMiddleware[Any, Any, Any], ...] = (
        HousekeepingMiddleware(),
        RunFooterMiddleware(meter),
        MeterMiddleware(meter),
        *guards([*lead_always, *platform_names], lead_always),
    )

    helpers: dict[str, dict[str, Any]] = {}
    if managed:

        def helper_middleware(
            helper_tools: Sequence[BaseTool],
        ) -> list[AgentMiddleware[Any, Any, Any]]:
            names = [t.name for t in helper_tools]
            always = [*HELPER_FILESYSTEM_TOOLS, *(n for n in names if n not in platform_names)]
            return [MeterMiddleware(meter), *guards([*HELPER_FILESYSTEM_TOOLS, *names], always)]

        helpers = helper_specs(
            analysis_tools=[*analysis_tools, *platform_tools],
            render_tool=render_tool,
            middleware=helper_middleware,
        )

    interrupt_on: dict[str, InterruptOnConfig] = {}
    if write_tools:
        interrupt_on[EXECUTE_CHANGE_TOOL] = build_execute_interrupt(services.proposal_service)

    prompt = system_prompt
    if prompt is None:
        prompt = (
            load_system_prompt(project_root) if (project_root / "instructions.md").exists() else ""
        )
    metadata = AssemblyMetadata(
        model_spec=model_config.spec,
        selection=plan,
        catalog_revision=catalog.revision,
        catalog_source=catalog.source,
        read_tool_count=len(platform_tools),
        mutation_entry_count=len(catalog.mutation_entries()),
        denied_entry_count=len(catalog.denied_entries()),
        tool_names=tuple(t.name for t in tools),
        write_gate=services.write_executor.gate.describe(),
        write_policy_issues=tuple(
            f"{i.tool_name}: {i.reason}" for i in runtime.write_policy_issues
        ),
    )
    return AgentComponents(
        model=resolved_model,
        tools=tools,
        middleware=middleware,
        interrupt_on=interrupt_on,
        system_prompt=prompt,
        skills=("/skills/",),
        metadata=metadata,
        run_metadata=template_marker() if settings.paid_media_template_telemetry else {},
        proposal_service=services.proposal_service,
        write_executor=services.write_executor,
        read_dispatcher=services.read_dispatcher,
        meter=meter,
        helpers=helpers,
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
