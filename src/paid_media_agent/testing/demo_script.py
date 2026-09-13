"""Scripted demo: a deterministic investigation through the real graph without a model API."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from paid_media_agent.config import Settings, project_root
from paid_media_agent.domain.presentation import ProposalView
from paid_media_agent.testing.scripted_model import (
    ScriptedChatModel,
    Step,
    all_tool_results,
    last_tool_results,
    tool_call_message,
)
from paid_media_agent.tools.fixtures import fixture_anchor

DEMO_QUESTION = (
    "Compare the last two complete weeks of sample data with the prior two weeks "
    "across all connected accounts and tell me what needs attention."
)


def _discover(_: Sequence[BaseMessage]) -> AIMessage:
    return tool_call_message(
        "discover_tools", {"query": "campaign performance daily spend conversions"}
    )


def _list_accounts(_: Sequence[BaseMessage]) -> AIMessage:
    return tool_call_message("list_accounts", {})


def _read_all(messages: Sequence[BaseMessage], *, anchor: date) -> AIMessage:
    accounts: dict[str, Any] = next(
        (r for r in last_tool_results(messages) if "accounts" in r), {"accounts": []}
    )
    calls = []
    for account in accounts["accounts"]:
        calls.append(
            {
                "name": f"{account['platform']}__get_campaign_performance",
                "args": {
                    "account_alias": account["alias"],
                    "start_date": (anchor - timedelta(days=27)).isoformat(),
                    "end_date": anchor.isoformat(),
                },
                "id": f"call_read_{account['alias']}",
                "type": "tool_call",
            }
        )
    return AIMessage(
        content="Reading each connected account for the union window.", tool_calls=calls
    )


def _compare(messages: Sequence[BaseMessage], *, anchor: date) -> AIMessage:
    reads = [r for r in last_tool_results(messages) if r.get("kind") == "read_result"]
    unavailable = [
        r.get("_tool_name", "unknown")
        for r in last_tool_results(messages)
        if r.get("denied") or r.get("error")
    ]
    return tool_call_message(
        "compare_periods",
        {
            "artifact_ids": [r["artifact_id"] for r in reads],
            "current_start": (anchor - timedelta(days=13)).isoformat(),
            "current_end": anchor.isoformat(),
            "previous_start": (anchor - timedelta(days=27)).isoformat(),
            "previous_end": (anchor - timedelta(days=14)).isoformat(),
            "unavailable_sources": unavailable,
        },
    )


def compose_answer(summary: dict[str, Any], reads: Sequence[dict[str, Any]]) -> str:
    """Deterministic prose assembled from structured results. Every number is quoted, not derived."""
    lines = [
        f"Comparison window: {summary['current_window']} vs {summary['previous_window']}.",
        f"Analysis artifact: {summary['artifact_id']} ({summary['schema_version']}, {summary['analysis_version']}); "
        f"reconciled={'yes' if summary['reconciled'] else 'NO'}.",
    ]
    if summary.get("cross_platform_total"):
        lines.append(
            f"Cross-platform spend (compatible sources only): {summary['cross_platform_total']}."
        )
    else:
        lines.append(
            f"No cross-platform total: {summary.get('total_suppressed_reason') or 'suppressed'}."
        )
    for platform in summary["platforms"]:
        lines.append("")
        lines.append(
            f"{platform['platform']} ({platform['account_ref']}): spend {platform['spend_current']} vs "
            f"{platform['spend_previous']} ({platform['spend_change']}); conversions {platform['conversions_current']} vs "
            f"{platform['conversions_previous']}; CPA {platform['cpa_current']} vs {platform['cpa_previous']}; "
            f"ROAS {platform['roas_current']} vs {platform['roas_previous']}."
        )
        if platform["missing_fields"]:
            lines.append(
                f"  Missing fields (unavailable, not zero): {', '.join(platform['missing_fields'])}."
            )
        if platform["quality_flags"]:
            lines.append(f"  Quality flags: {', '.join(platform['quality_flags'])}.")
        for item in platform["attention"]:
            lines.append(f"  Attention: {item}")
    if summary["unavailable_sources"]:
        lines.append("")
        lines.append(f"Unavailable sources: {', '.join(summary['unavailable_sources'])}.")
    lines.append("")
    lines.append(
        "Evidence: "
        + ", ".join(f"{r['tool']} -> {r['artifact_id']} ({r['actual_window']})" for r in reads)
        + "."
    )
    lines.append(
        "Interpretation: spend shifts above are platform-attributed delivery facts, not incrementality. "
        "Any budget change should be proposed as a typed change and approved before execution."
    )
    return "\n".join(lines)


def _answer(messages: Sequence[BaseMessage]) -> AIMessage:
    results = all_tool_results(messages)
    summary = next((r for r in reversed(results) if r.get("kind") == "analysis_summary"), None)
    reads = [r for r in results if r.get("kind") == "read_result"]
    if summary is None:
        failures = [r for r in results if r.get("error") or r.get("denied")]
        detail = failures[-1] if failures else {}
        return AIMessage(content=f"The deterministic comparison did not complete: {detail}")
    return AIMessage(content=compose_answer(summary, reads))


def demo_steps(anchor: date | None = None) -> list[Step]:
    end = fixture_anchor(anchor)
    return [
        _discover,
        _list_accounts,
        partial(_read_all, anchor=end),
        partial(_compare, anchor=end),
        _answer,
    ]


def build_demo_model(steps: list[Step] | None = None) -> ScriptedChatModel:
    return ScriptedChatModel(steps=steps or demo_steps())


def _propose(messages: Sequence[BaseMessage]) -> AIMessage:  # noqa: ARG001
    return tool_call_message(
        "propose_change",
        {
            "account_alias": "demo-google",
            "tool_name": "google_ads__update_campaign_budget",
            "target_ref": "g-103",
            "changes": {"daily_budget": 240},
            "reason": "Performance Max spend fell while CPA rose; reduce daily budget by a reversible step.",
            "measurement_plan": "Compare CPA and conversions after 7 complete days at the new budget.",
            "reversal_plan": "Restore the previous daily budget through a new proposal.",
        },
    )


def _execute(messages: Sequence[BaseMessage]) -> AIMessage:
    proposal = next((r for r in last_tool_results(messages) if "proposal" in r), None)
    if proposal is None:
        return AIMessage(content="The proposal could not be staged.")
    return tool_call_message(
        "execute_change", {"proposal_id": proposal["proposal"]["proposal_id"], "revision": 1}
    )


def _report_receipt(messages: Sequence[BaseMessage]) -> AIMessage:
    results = last_tool_results(messages)
    receipt = next((r for r in results if "receipt" in r), None)
    if receipt is None:
        return AIMessage(
            content=f"No receipt was returned: {results[-1] if results else 'no tool result'}"
        )
    view = receipt["receipt"]
    verified = ", ".join(f"{fv['field']}={fv['value']}" for fv in view["verified_state"])
    return AIMessage(
        content=(
            f"Receipt for proposal {view['proposal_id']} revision {view['revision']}: status={view['status']}, "
            f"mutation_attempted={view['mutation_attempted']}, readback_attempts={view['readback_attempts']}, "
            f"verified_state=[{verified}], reason={view['reason']}"
        )
    )


def write_demo_steps() -> list[Step]:
    return [_propose, _execute, _report_receipt]


async def run_demo(
    settings: Settings, *, with_proposal: bool, root: Path | None = None
) -> dict[str, Any]:
    from langsmith import tracing_context

    with tracing_context(enabled=False):
        return await _run_demo(settings, with_proposal=with_proposal, root=root)


async def _run_demo(
    settings: Settings, *, with_proposal: bool, root: Path | None = None
) -> dict[str, Any]:
    from paid_media_agent.runtime.local import build_local_runtime

    root = root or project_root()
    settings = settings.model_copy(
        update={
            "paid_media_model": "scripted:demo",
            "paid_media_model_base_url": None,
            "paid_media_approver_ids": "local-user",
            "paid_media_allow_self_approval": True,
            "paid_media_data_mode": "sample",
            "paid_media_account_config_path": Path("config/accounts.example.toml"),
            "paid_media_fixture_anchor": fixture_anchor(settings.paid_media_fixture_anchor),
        }
    )
    steps = demo_steps(settings.paid_media_fixture_anchor) + (
        write_demo_steps() if with_proposal else []
    )
    model = build_demo_model(steps)
    runtime = build_local_runtime(settings, project_root=root, model=model)
    config: RunnableConfig = {
        "configurable": {"thread_id": "demo-thread", "caller_ref": "local-user"}
    }
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": DEMO_QUESTION}]}, config=config
    )
    answer = state["messages"][-1].content
    analysis = next(
        (r for r in all_tool_results(state["messages"]) if r.get("kind") == "analysis_summary"),
        None,
    )
    if not analysis or not analysis.get("reconciled"):
        raise ValueError(str(answer))
    result: dict[str, Any] = {
        "answer": answer,
        "audit": runtime.components.read_dispatcher.audit,
        "catalog_revision": runtime.catalog.revision,
        "selection": runtime.components.metadata.selection.strategy.value,
        "analysis": analysis,
    }
    if not with_proposal:
        return result
    state = await runtime.graph.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Reduce the Performance Max daily budget to 240 and execute it.",
                }
            ]
        },
        config=config,
    )
    snapshot = runtime.graph.get_state(config)
    if not snapshot.interrupts:
        raise ValueError(str(state["messages"][-1].content))
    service = runtime.components.proposal_service
    records = service.proposals.list_for_thread("demo-thread")
    record = records[-1]
    view = ProposalView.from_record(record)
    result["proposal"] = view.model_dump(mode="json")
    # The demo operator approves through the host service, which creates the signed claim.
    service.approve(record.changeset.proposal_id, approver_ref="local-user")
    state = await runtime.graph.ainvoke(
        Command(resume={"decisions": [{"type": "approve"}]}), config=config
    )
    result["receipt_message"] = state["messages"][-1].content
    receipt = runtime.profile.receipts.get(record.changeset.proposal_id)
    if receipt is None or receipt.status != "verified":
        raise ValueError(str(result["receipt_message"]))
    result["receipt"] = receipt.model_dump(mode="json") if receipt else None
    return result
