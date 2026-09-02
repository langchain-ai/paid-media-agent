"""Command-line entry: fixture demo, doctor, self-hosted serve, and the rich Slack adapter."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

import click
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from paid_media_agent.config import Settings
from paid_media_agent.domain.presentation import ProposalView


def project_root() -> Path:
    """The checkout root: instructions.md and skills/ live here."""
    here = Path.cwd()
    for candidate in (here, *here.parents):
        if (candidate / "instructions.md").exists() and (candidate / "skills").is_dir():
            return candidate
    return here


def _configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.paid_media_log_level.upper(), format="%(levelname)s %(name)s: %(message)s"
    )


@click.group()
def main() -> None:
    """Paid Media Agent."""


@main.command()
@click.option(
    "--with-proposal",
    is_flag=True,
    help="Also run the governed fake-write flow after the analysis.",
)
@click.option(
    "--json", "as_json", is_flag=True, help="Print the final message and tool audit as JSON."
)
def demo(with_proposal: bool, as_json: bool) -> None:
    """Run the fixture-backed demo through the real graph with no network or secrets."""
    settings = Settings(paid_media_model="scripted:demo", paid_media_allow_self_approval=True)
    _configure_logging(settings)
    result = asyncio.run(run_demo(settings, with_proposal=with_proposal))
    if as_json:
        click.echo(json.dumps(result, indent=2, default=str))
        return
    click.echo(result["answer"])
    if with_proposal:
        click.echo("")
        click.echo("Proposal review (from the persisted ChangeSet):")
        click.echo(json.dumps(result["proposal"], indent=2, default=str))
        click.echo("")
        click.echo(result["receipt_message"])
    click.echo("")
    click.echo(
        f"Tool audit: {len(result['audit'])} host-side reads; catalog revision {result['catalog_revision']}."
    )


async def run_demo(settings: Settings, *, with_proposal: bool) -> dict[str, Any]:
    from paid_media_agent.runtime.local import build_local_runtime  # noqa: PLC0415
    from paid_media_agent.testing.demo_script import (  # noqa: PLC0415
        DEMO_QUESTION,
        build_demo_model,
        demo_steps,
        write_demo_steps,
    )

    root = project_root()
    steps = demo_steps() + (write_demo_steps() if with_proposal else [])
    model = build_demo_model(steps)
    runtime = build_local_runtime(settings, project_root=root, model=model)
    config = RunnableConfig(configurable={"thread_id": "demo-thread", "caller_ref": "local-user"})
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": DEMO_QUESTION}]}, config=config
    )
    answer = state["messages"][-1].content
    result: dict[str, Any] = {
        "answer": answer,
        "audit": runtime.components.read_dispatcher.audit,
        "catalog_revision": runtime.catalog.revision,
        "selection": runtime.components.metadata.selection.strategy.value,
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
        result["receipt_message"] = state["messages"][-1].content
        result["proposal"] = None
        return result
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
    result["receipt"] = receipt.model_dump(mode="json") if receipt else None
    return result


@main.command()
@click.option(
    "--snapshot", is_flag=True, help="Run the sandbox snapshot compatibility contract instead."
)
def doctor(snapshot: bool) -> None:
    """Diagnose configuration without printing secret values."""
    from paid_media_agent.doctor import (  # noqa: PLC0415
        format_checks,
        run_doctor,
        run_snapshot_checks,
    )

    settings = Settings()
    checks = (
        run_snapshot_checks(project_root())
        if snapshot
        else run_doctor(settings, project_root=project_root())
    )
    click.echo(format_checks(checks))
    if any(not c.ok for c in checks):
        sys.exit(1)


@main.command()
def serve() -> None:
    """Serve the self-hosted API (requires the self-host extra and DATABASE_URL for durable state)."""
    settings = Settings()
    _configure_logging(settings)
    try:
        import uvicorn  # noqa: PLC0415
    except ImportError:
        click.echo("uvicorn is not installed; run `uv sync --extra self-host`.", err=True)
        sys.exit(2)
    from paid_media_agent.runtime.self_hosted import build_self_hosted_runtime  # noqa: PLC0415
    from paid_media_agent.surfaces.api.app import create_app  # noqa: PLC0415

    runtime = asyncio.run(build_self_hosted_runtime(settings, project_root=project_root()))
    app = create_app(runtime)
    uvicorn.run(app, host=settings.paid_media_api_host, port=settings.paid_media_api_port)


@main.command()
def slack() -> None:
    """Run the rich Slack adapter in Socket Mode against the local or self-hosted runtime."""
    settings = Settings()
    _configure_logging(settings)
    from paid_media_agent.runtime.self_hosted import build_self_hosted_runtime  # noqa: PLC0415
    from paid_media_agent.surfaces.slack.socket_mode import run_socket_mode  # noqa: PLC0415

    runtime = asyncio.run(build_self_hosted_runtime(settings, project_root=project_root()))
    run_socket_mode(settings, runtime)


if __name__ == "__main__":
    main()
