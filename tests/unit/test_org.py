"""Organization context: one profile, rendered pages, shared links and files, and the tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from paid_media_agent.admin import actions
from paid_media_agent.org import (
    QUESTIONS,
    OrgProfile,
    SourceError,
    add_file,
    add_link,
    fetch_text,
    load_profile,
    org_summary,
    save_profile,
)
from paid_media_agent.tools.org import build_org_tools


def test_profile_round_trips_and_renders_pages(tmp_path: Path) -> None:
    profile = OrgProfile(
        business="We sell project tools to engineering teams.", targets="CPA under 120 USD"
    )
    written = save_profile(tmp_path, profile)

    assert {w.name for w in written} == {"profile.json", "goals.md", "conventions.md", "sources.md"}
    loaded = load_profile(tmp_path)
    assert loaded.business == profile.business and loaded.updated_at is not None
    goals = (tmp_path / "docs/org/goals.md").read_text()
    assert (
        "CPA under 120 USD" in goals and "Not provided" in goals
    )  # empty fields stay visibly empty
    assert org_summary(tmp_path)["answered"] == 2 and org_summary(tmp_path)["configured"] is True


def test_shared_file_and_link_land_on_the_sources_page(tmp_path: Path) -> None:
    brief = tmp_path / "brief.md"
    brief.write_text("# Q4 plan\n\nDouble LinkedIn in October.")
    stored = add_file(tmp_path, brief, note="Q4 plan")
    linked = add_link(
        tmp_path,
        "https://example.com/plans/h2",
        fetch=lambda _url: "H2 plan. Grow trials.",
    )

    sources = (tmp_path / "docs/org/sources.md").read_text()
    assert "[brief.md](/docs/org/sources/brief.md): Q4 plan" in sources
    assert f"[example.com/plans/h2](/docs/org/sources/{linked.name})" in sources
    assert stored.read_text().startswith("# Q4 plan")
    with pytest.raises(SourceError):
        add_file(tmp_path, tmp_path / "missing.md")


def test_only_public_https_links_are_fetched() -> None:
    for url in (
        "http://example.com",
        "https://localhost/x",
        "https://127.0.0.1/x",
        "https://10.0.0.4/x",
    ):
        with pytest.raises(SourceError):
            fetch_text(url)


def test_tools_merge_answers_and_return_the_context_without_the_filesystem(tmp_path: Path) -> None:
    tools = {t.name: t for t in build_org_tools(tmp_path)}
    save_profile(tmp_path, OrgProfile(business="B2B software"))
    add_file(tmp_path, _brief(tmp_path), note="Q4 plan")

    result = json.loads(tools["update_org_profile"].invoke({"targets": "directional for now"}))
    context = json.loads(tools["get_org_context"].invoke({}))
    brief = json.loads(tools["get_org_context"].invoke({"source": "brief.md"}))

    assert result["saved"] == ["targets"] and result["answered"] == 2
    assert load_profile(tmp_path).business == "B2B software", "untouched fields keep their value"
    assert "directional for now" in context["goals"] and "Not provided" in context["conventions"]
    assert context["sources"] == ["brief.md"] and brief["text"].startswith("# Q4 plan")
    assert json.loads(tools["get_org_context"].invoke({"source": "nope.md"}))["error"] is True
    assert json.loads(tools["update_org_profile"].invoke({}))["error"] is True


def _brief(tmp_path: Path) -> Path:
    brief = tmp_path / "brief.md"
    brief.write_text("# Q4 plan\n\nDouble LinkedIn in October.")
    return brief


def test_console_actions_validate_fields(tmp_path: Path) -> None:
    bad = actions.org_set(tmp_path, {"colour": "blue"})
    assert bad.status == "fail" and "colour" in bad.summary
    good = actions.org_set(tmp_path, {"approvers": "the growth lead"})
    assert good.ok and f"1 of {len(QUESTIONS)}" in good.summary
    assert actions.org_show(tmp_path).detail["summary"]["answered"] == 1
