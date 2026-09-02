"""Command-line entry: setup console, fixture demo, doctor, tests, accounts, and runtimes.

Every console action has a subcommand with `--json`, so coding agents and humans share one path.
"""

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

from paid_media_agent.admin import actions
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


def _emit(result: actions.ActionResult, as_json: bool) -> None:
    if as_json:
        click.echo(actions.as_json(result))
    else:
        click.echo(f"{result.status.upper():<5} {result.action}: {result.summary}")
        for key, value in result.detail.items():
            if isinstance(value, str | int | float | bool):
                click.echo(f"      {key}: {value}")
    if result.status == "fail":
        sys.exit(1)


@click.group()
def main() -> None:
    """Paid Media Agent."""


# ---------------------------------------------------------------- setup console


@main.command()
@click.option("--port", default=8765, show_default=True, help="Local port for the console.")
@click.option("--no-open", is_flag=True, help="Do not open the browser automatically.")
def setup(port: int, no_open: bool) -> None:
    """Start the local setup console and open it in the browser."""
    from paid_media_agent.admin.server import run_console  # noqa: PLC0415

    run_console(project_root(), port=port, open_browser=not no_open)


# ---------------------------------------------------------------- demo and doctor


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


async def run_demo(
    settings: Settings, *, with_proposal: bool, root: Path | None = None
) -> dict[str, Any]:
    from paid_media_agent.runtime.local import build_local_runtime  # noqa: PLC0415
    from paid_media_agent.testing.demo_script import (  # noqa: PLC0415
        DEMO_QUESTION,
        build_demo_model,
        demo_steps,
        write_demo_steps,
    )

    root = root or project_root()
    steps = demo_steps() + (write_demo_steps() if with_proposal else [])
    model = build_demo_model(steps)
    runtime = build_local_runtime(settings, project_root=root, model=model)
    config: RunnableConfig = {
        "configurable": {"thread_id": "demo-thread", "caller_ref": "local-user"}
    }
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
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def doctor(snapshot: bool, as_json: bool) -> None:
    """Diagnose configuration without printing secret values."""
    from paid_media_agent.doctor import (  # noqa: PLC0415
        format_checks,
        run_doctor,
        run_snapshot_checks,
    )

    root = project_root()
    if as_json:
        _emit(actions.snapshot_check(root) if snapshot else actions.status(root), True)
        return
    settings = actions.load_settings(root)
    checks = run_snapshot_checks(root) if snapshot else run_doctor(settings, project_root=root)
    click.echo(format_checks(checks))
    if any(not c.ok for c in checks):
        sys.exit(1)


# ---------------------------------------------------------------- config


@main.group()
def config() -> None:
    """Show or change local `.env` settings without printing secrets."""


@config.command("show")
@click.option("--json", "as_json", is_flag=True)
def config_show(as_json: bool) -> None:
    result = actions.config_view(project_root())
    if as_json:
        _emit(result, True)
        return
    for key in result.detail["keys"]:
        mark = "set" if key["is_set"] else "unset"
        shown = key["value"] if key["is_set"] else ""
        click.echo(f"{key['name']:<40} {mark:<6} {shown}")


@config.command("set")
@click.argument("pairs", nargs=-1, required=True)
@click.option("--json", "as_json", is_flag=True)
def config_set(pairs: tuple[str, ...], as_json: bool) -> None:
    """Set KEY=VALUE pairs in .env. Keys are validated against the settings schema."""
    updates: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise click.UsageError(f"expected KEY=VALUE, got {pair}")
        updates[key.strip()] = value
    _emit(actions.config_set(project_root(), updates), as_json)


@config.command("generate")
@click.argument("keys", nargs=-1, required=True)
@click.option("--json", "as_json", is_flag=True)
def config_generate(keys: tuple[str, ...], as_json: bool) -> None:
    """Generate strong values for host-owned secrets (signing key, API token)."""
    for key in keys:
        result = actions.generate_secret(project_root(), key)
        _emit(result, as_json)
        if not as_json and result.detail.get("show_once"):
            click.echo(f"      API token (shown once): {result.detail['show_once']}")


# ---------------------------------------------------------------- accounts


@main.group()
def accounts() -> None:
    """Discover provider accounts and map public aliases."""


@accounts.command("discover")
@click.option("--json", "as_json", is_flag=True)
def accounts_discover(as_json: bool) -> None:
    result = actions.accounts_discover(project_root())
    if as_json:
        _emit(result, True)
        return
    click.echo(f"{result.status.upper()} {result.summary}")
    for row in result.detail.get("accounts", []):
        click.echo(
            f"  {row['platform']:<12} {row['provider_account_id']:<24} {row['name']}  {row.get('currency', '')} {row.get('timezone', '')}"
        )
    click.echo(
        "Map one with: paid-media-agent accounts add <alias> --platform <platform> --id <provider-id> --currency USD --timezone America/New_York"
    )


@accounts.command("list")
@click.option("--json", "as_json", is_flag=True)
def accounts_list(as_json: bool) -> None:
    _emit(actions.accounts_list(project_root()), as_json)


@accounts.command("add")
@click.argument("alias")
@click.option(
    "--platform", required=True, type=click.Choice(["google_ads", "meta_ads", "reddit_ads"])
)
@click.option(
    "--id",
    "provider_account_id",
    required=True,
    help="Provider account id from `accounts discover`.",
)
@click.option("--currency", default="USD", show_default=True)
@click.option("--timezone", default="UTC", show_default=True)
@click.option("--json", "as_json", is_flag=True)
def accounts_add(
    alias: str, platform: str, provider_account_id: str, currency: str, timezone: str, as_json: bool
) -> None:
    _emit(
        actions.accounts_add(
            project_root(),
            alias=alias,
            platform=platform,
            provider_account_id=provider_account_id,
            currency=currency,
            timezone=timezone,
        ),
        as_json,
    )


@accounts.command("remove")
@click.argument("alias")
@click.option("--json", "as_json", is_flag=True)
def accounts_remove(alias: str, as_json: bool) -> None:
    _emit(actions.accounts_remove(project_root(), alias), as_json)


# ---------------------------------------------------------------- catalog, policy, tests


@main.group()
def catalog() -> None:
    """Inspect the authorized tool catalog."""


@catalog.command("show")
@click.option(
    "--live", is_flag=True, help="Load the live Pipeboard catalog instead of the fixture."
)
@click.option("--json", "as_json", is_flag=True)
def catalog_show(live: bool, as_json: bool) -> None:
    result = actions.catalog_show(project_root(), live=live)
    if as_json:
        _emit(result, True)
        return
    click.echo(f"{result.summary}")
    for entry in result.detail.get("entries", []):
        click.echo(f"  {entry['class']:<9} {entry['name']:<48} {entry['reason']}")


@main.group()
def policy() -> None:
    """Validate the reviewed mutation set."""


@policy.command("validate")
@click.option("--live", is_flag=True, help="Validate against the live Pipeboard catalog.")
@click.option("--json", "as_json", is_flag=True)
def policy_validate(live: bool, as_json: bool) -> None:
    result = actions.policy_validate(project_root(), live=live)
    if as_json:
        _emit(result, True)
        return
    click.echo(f"{result.status.upper()} {result.summary}")
    for issue in result.detail.get("issues", []):
        click.echo(f"  {issue['tool']:<48} {issue['reason']}")


@main.group()
def test() -> None:
    """Connection tests that never print secret values."""


@test.command("model")
@click.option("--json", "as_json", is_flag=True)
def test_model(as_json: bool) -> None:
    _emit(actions.model_test(project_root()), as_json)


@test.command("pipeboard")
@click.option("--json", "as_json", is_flag=True)
def test_pipeboard(as_json: bool) -> None:
    _emit(actions.pipeboard_test(project_root()), as_json)


@test.command("slack")
@click.option("--json", "as_json", is_flag=True)
def test_slack(as_json: bool) -> None:
    _emit(actions.slack_test(project_root()), as_json)


@test.command("db")
@click.option("--json", "as_json", is_flag=True)
def test_db(as_json: bool) -> None:
    _emit(actions.database_test(project_root()), as_json)


@test.command("all")
@click.option("--json", "as_json", is_flag=True)
def test_all(as_json: bool) -> None:
    root = project_root()
    results = [
        actions.model_test(root),
        actions.pipeboard_test(root),
        actions.slack_test(root),
        actions.database_test(root),
        actions.mda_check(root),
    ]
    if as_json:
        click.echo(json.dumps([r.model_dump(mode="json") for r in results], indent=2, default=str))
    else:
        for result in results:
            click.echo(f"{result.status.upper():<5} {result.action}: {result.summary}")
    if any(r.status == "fail" for r in results):
        sys.exit(1)


# ---------------------------------------------------------------- mda and writes


@main.group()
def mda() -> None:
    """Managed Deep Agents preflight and deployment."""


@mda.command("check")
@click.option("--json", "as_json", is_flag=True)
def mda_check(as_json: bool) -> None:
    _emit(actions.mda_check(project_root()), as_json)


@mda.command("dev")
def mda_dev() -> None:
    """Run `mda dev` in the foreground."""
    import subprocess  # noqa: PLC0415

    from paid_media_agent.admin.processes import PROCESS_TEMPLATES  # noqa: PLC0415

    raise SystemExit(subprocess.call(PROCESS_TEMPLATES["mda-dev"], cwd=project_root()))  # noqa: S603


@mda.command("deploy")
@click.option(
    "--yes", is_flag=True, help="Confirm the deployment. Deploying is an outward-facing action."
)
def mda_deploy(yes: bool) -> None:
    """Run `mda deploy .` after preflight and explicit confirmation."""
    import subprocess  # noqa: PLC0415

    from paid_media_agent.admin.processes import PROCESS_TEMPLATES  # noqa: PLC0415

    root = project_root()
    check = actions.mda_check(root)
    click.echo(f"{check.status.upper()} preflight: {check.summary}")
    if check.status != "ok":
        sys.exit(1)
    if not yes:
        click.echo("Re-run with --yes to deploy.")
        sys.exit(2)
    raise SystemExit(subprocess.call(PROCESS_TEMPLATES["mda-deploy"], cwd=root))  # noqa: S603


@main.group()
def writes() -> None:
    """Write gates and the incident kill switch."""


@writes.command("kill-switch")
@click.argument("state", type=click.Choice(["on", "off"]))
@click.option("--yes", is_flag=True, help="Required to clear the kill switch.")
@click.option("--json", "as_json", is_flag=True)
def writes_kill_switch(state: str, yes: bool, as_json: bool) -> None:
    _emit(actions.kill_switch_set(project_root(), engaged=state == "on", confirmed=yes), as_json)


# ---------------------------------------------------------------- runtimes


@main.command()
def serve() -> None:
    """Serve the self-hosted API (Postgres when DATABASE_URL is set, else in-memory state)."""
    settings = Settings()
    _configure_logging(settings)
    import uvicorn  # noqa: PLC0415

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
