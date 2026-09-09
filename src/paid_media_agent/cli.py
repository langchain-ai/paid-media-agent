"""Command-line entry: setup console, fixture demo, doctor, tests, accounts, org, sandbox, MDA.

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

from paid_media_agent.admin import actions
from paid_media_agent.config import Settings, project_root
from paid_media_agent.domain.common import Platform
from paid_media_agent.testing.demo_script import run_demo


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
    """Paid Media Agent command line.

    Every command sees the project `.env` the same way `langgraph dev` and the managed build do:
    allowlisted values are exported into this process before the command runs, so provider SDKs
    that read their key from the environment work without a manual `export`.
    """
    from paid_media_agent.admin.envfile import apply_env_file

    apply_env_file(project_root())


# ---------------------------------------------------------------- setup console


@main.command()
@click.option("--port", default=8765, show_default=True, help="Local port for the console.")
@click.option("--no-open", is_flag=True, help="Do not open the browser automatically.")
def setup(port: int, no_open: bool) -> None:
    """Start the local setup console and open it in the browser."""
    from paid_media_agent.admin.server import run_console

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


@main.command()
@click.option(
    "--snapshot", is_flag=True, help="Run the sandbox snapshot compatibility contract instead."
)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
def doctor(snapshot: bool, as_json: bool) -> None:
    """Diagnose configuration without printing secret values."""
    from paid_media_agent.doctor import (
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
            if result.detail.get("usage"):
                click.echo(f"      Use as: {result.detail['usage']}")


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
@click.option("--platform", required=True, type=click.Choice([p.value for p in Platform]))
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
def org() -> None:
    """Your organization's context: the interview, links, and files the agent reads."""


@org.command("show")
@click.option("--json", "as_json", is_flag=True)
def org_show(as_json: bool) -> None:
    _emit(actions.org_show(project_root()), as_json)


@org.command("interview")
def org_interview() -> None:
    """Answer the eight questions in the terminal; Enter keeps the current answer."""
    from paid_media_agent.org import QUESTIONS, load_profile

    current = load_profile(project_root())
    answers: dict[str, str] = {}
    for question in QUESTIONS:
        click.echo(f"\n{question.question}\n  why: {question.why}\n  e.g. {question.example}")
        answer = click.prompt(
            "", default=getattr(current, question.field) or "", show_default=False
        )
        if answer.strip() and answer.strip() != getattr(current, question.field):
            answers[question.field] = answer.strip()
    _emit(
        actions.org_set(project_root(), answers) if answers else actions.org_show(project_root()),
        False,
    )


@org.command("set")
@click.argument("pairs", nargs=-1, required=True)
@click.option("--json", "as_json", is_flag=True)
def org_set(pairs: tuple[str, ...], as_json: bool) -> None:
    """Set answers as field=value pairs (business, primary_conversion, targets, ...)."""
    updates = dict(pair.split("=", 1) for pair in pairs if "=" in pair)
    _emit(actions.org_set(project_root(), updates), as_json)


@org.command("add-link")
@click.argument("url")
@click.option("--note", default="")
@click.option("--json", "as_json", is_flag=True)
def org_add_link(url: str, note: str, as_json: bool) -> None:
    _emit(actions.org_add_link(project_root(), url, note), as_json)


@org.command("add-file")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--note", default="")
@click.option("--json", "as_json", is_flag=True)
def org_add_file(path: Path, note: str, as_json: bool) -> None:
    _emit(actions.org_add_file(project_root(), path, note), as_json)


@main.group()
def sandbox() -> None:
    """Build, declare, and probe the LangSmith sandbox the model's files live in."""


@sandbox.command("publish")
@click.option("--name", default="paid-media-agent-sandbox", show_default=True)
@click.option("--fs-gib", type=int, default=actions.SNAPSHOT_FS_GIB, show_default=True)
@click.option("--json", "as_json", is_flag=True)
def sandbox_publish(name: str, fs_gib: int, as_json: bool) -> None:
    """Build sandbox/Dockerfile into a snapshot on LangSmith and declare it."""
    log = None if as_json else lambda line: click.echo(line.rstrip("\n"))
    _emit(actions.sandbox_publish(project_root(), name=name, fs_gib=fs_gib, log=log), as_json)


@sandbox.command("use")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
def sandbox_use(name: str, as_json: bool) -> None:
    """Declare an existing snapshot in .env and sandbox/__init__.py."""
    _emit(actions.sandbox_use(project_root(), name), as_json)


@sandbox.command("test")
@click.option("--json", "as_json", is_flag=True)
def sandbox_test(as_json: bool) -> None:
    """Open a sandbox from the snapshot, probe it, and delete it."""
    _emit(actions.sandbox_test(project_root()), as_json)


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
    """Rich Slack adapter credentials (self-hosted path)."""
    _emit(actions.slack_test(project_root()), as_json)


@test.command("db")
@click.option("--json", "as_json", is_flag=True)
def test_db(as_json: bool) -> None:
    """Postgres connection (self-hosted path)."""
    _emit(actions.database_test(project_root()), as_json)


@test.command("all")
@click.option("--json", "as_json", is_flag=True)
def test_all(as_json: bool) -> None:
    root = project_root()
    results = [actions.model_test(root), actions.pipeboard_test(root)]
    if actions.load_settings(root).paid_media_runtime == "self_hosted":
        results += [actions.slack_test(root), actions.database_test(root)]
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
    import subprocess

    from paid_media_agent.admin.processes import PROCESS_TEMPLATES

    raise SystemExit(subprocess.call(PROCESS_TEMPLATES["mda-dev"], cwd=project_root()))  # noqa: S603


@mda.command("deploy")
@click.option(
    "--yes", is_flag=True, help="Confirm the deployment. Deploying is an outward-facing action."
)
def mda_deploy(yes: bool) -> None:
    """Run `mda deploy .` after preflight and explicit confirmation."""
    import subprocess

    from paid_media_agent.admin.processes import PROCESS_TEMPLATES

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


# ---------------------------------------------------------------- ask


@main.command()
@click.argument("question")
@click.option("--json", "as_json", is_flag=True)
def ask(question: str, as_json: bool) -> None:
    """Run one question locally through the same profile the deployment runs."""
    result = actions.ask_question(project_root(), question)
    if as_json:
        _emit(result, True)
        return
    click.echo(result.detail.get("answer", result.summary))
    if result.status == "fail":
        sys.exit(1)


# ---------------------------------------------------------------- reports


@main.command()
@click.option(
    "--cadence", type=click.Choice(["weekly", "monthly"]), default="weekly", show_default=True
)
@click.option(
    "--end", "end_date", default=None, help="Last complete day (YYYY-MM-DD). Defaults to yesterday."
)
@click.option(
    "--alias",
    "aliases",
    multiple=True,
    help="Account alias to include. Repeatable; default is every alias.",
)
@click.option("--no-render", is_flag=True, help="Compare only; skip the HTML/PDF report.")
@click.option("--json", "as_json", is_flag=True)
def report(
    cadence: str, end_date: str | None, aliases: tuple[str, ...], no_render: bool, as_json: bool
) -> None:
    """Run the deterministic cross-platform report: reads, comparison, and rendering, no model."""
    from datetime import date, timedelta

    from paid_media_agent.reports.cadence import run_cadence_report
    from paid_media_agent.runtime.local import build_configured_runtime

    settings = Settings()
    _configure_logging(settings)
    root = project_root()
    end = date.fromisoformat(end_date) if end_date else date.today() - timedelta(days=1)

    async def _run() -> Any:
        runtime = await asyncio.to_thread(build_configured_runtime, settings, project_root=root)
        return await run_cadence_report(
            cadence=cadence,  # type: ignore[arg-type]
            end=end,
            accounts=runtime.profile.accounts,
            catalog=runtime.catalog,
            dispatcher=runtime.components.read_dispatcher,
            artifacts=runtime.profile.artifacts,
            aliases=aliases or None,
            render=not no_render,
        )

    try:
        run = asyncio.run(_run())
    except RuntimeError as exc:
        click.echo(f"FAIL report: {exc}", err=True)
        sys.exit(1)
    if as_json:
        click.echo(
            json.dumps(
                {
                    "cadence": run.cadence,
                    "current": run.windows.current.model_dump(mode="json"),
                    "previous": run.windows.previous.model_dump(mode="json"),
                    "reads": list(run.read_artifacts),
                    "unavailable": list(run.unavailable),
                    "analysis_artifact_id": run.analysis_artifact_id,
                    "summary": run.summary,
                    "report": run.report,
                    "reconciled": run.reconciled,
                },
                indent=2,
                default=str,
            )
        )
        return
    click.echo(
        f"{run.cadence} report · {run.windows.current.start} to {run.windows.current.end} vs {run.windows.previous.start} to {run.windows.previous.end}"
    )
    for platform in run.summary["platforms"]:
        click.echo(
            f"  {platform['platform']:<12} spend {platform['spend_current']} vs {platform['spend_previous']} ({platform['spend_change']}); CPA {platform['cpa_current']} vs {platform['cpa_previous']}"
        )
    if run.unavailable:
        click.echo("  unavailable: " + "; ".join(run.unavailable))
    click.echo(
        f"  analysis {run.analysis_artifact_id} · reconciled={'yes' if run.reconciled else 'NO'}"
    )
    if run.report:
        click.echo(
            "  files: "
            + ", ".join(f["path"] for f in run.report["files"])
            + f" · pdf {run.report['pdf']}"
        )
    if not run.reconciled:
        sys.exit(1)


# ---------------------------------------------------------------- self-hosted runtime


@main.command()
@click.option("--host", default=None, help="Bind address (default PAID_MEDIA_API_HOST).")
@click.option("--port", type=int, default=None, help="Port (default PAID_MEDIA_API_PORT).")
def serve(host: str | None, port: int | None) -> None:
    """Serve the self-hosted API (Postgres when DATABASE_URL is set, else in-memory state)."""
    settings = Settings()
    if host is not None:
        settings = settings.model_copy(update={"paid_media_api_host": host})
    if port is not None:
        settings = settings.model_copy(update={"paid_media_api_port": port})
    _configure_logging(settings)
    import uvicorn

    from paid_media_agent.runtime.self_hosted import build_self_hosted_runtime
    from paid_media_agent.surfaces.api.app import create_app

    async def _serve() -> None:
        # The Postgres checkpointer is async and bound to this loop, so build and serve in it.
        runtime = await build_self_hosted_runtime(settings, project_root=project_root())
        config = uvicorn.Config(
            create_app(runtime),
            host=settings.paid_media_api_host,
            port=settings.paid_media_api_port,
        )
        await uvicorn.Server(config).serve()

    asyncio.run(_serve())


@main.command()
def slack() -> None:
    """Run the rich Slack adapter in Socket Mode against the self-hosted runtime."""
    settings = Settings()
    _configure_logging(settings)
    from paid_media_agent.runtime.self_hosted import build_self_hosted_runtime
    from paid_media_agent.surfaces.slack.socket_mode import run_socket_mode

    async def _slack() -> None:
        runtime = await build_self_hosted_runtime(settings, project_root=project_root())
        await run_socket_mode(settings, runtime)

    asyncio.run(_slack())


if __name__ == "__main__":
    main()
