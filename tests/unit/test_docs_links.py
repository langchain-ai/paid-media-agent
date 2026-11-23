"""Documentation checks: relative links resolve and documented commands exist."""

from __future__ import annotations

import re
from pathlib import Path

from click.testing import CliRunner

from paid_media_agent.cli import main

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _markdown_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*.md"):
        if any(part in {".venv", ".git", ".mda"} for part in path.parts):
            continue
        if path.is_relative_to(root / "workspace") and not path.is_relative_to(
            root / "workspace" / "skills"
        ):
            continue
        files.append(path)
    return files


def test_relative_markdown_links_resolve(project_root: Path) -> None:
    broken: list[str] = []
    for path in _markdown_files(project_root):
        for target in LINK_RE.findall(path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            candidate = (path.parent / target.split("#")[0]).resolve()
            if not candidate.exists():
                broken.append(f"{path.relative_to(project_root)} -> {target}")
    assert not broken, broken


def test_documented_commands_exist(project_root: Path) -> None:
    documented = set()
    for name in ("README.md", "OPERATIONS.md"):
        for match in re.finditer(
            r"uv run paid-media-agent (\w[\w-]*)", (project_root / name).read_text()
        ):
            documented.add(match.group(1))
    assert {
        "demo",
        "doctor",
        "setup",
        "ask",
        "report",
        "test",
        "config",
        "accounts",
        "catalog",
        "policy",
        "writes",
        "mda",
        "sandbox",
        "serve",
        "slack",
    } <= documented
    runner = CliRunner()
    for command in documented:
        result = runner.invoke(main, [command, "--help"])
        assert result.exit_code == 0, f"{command}: {result.output}"


def test_skills_have_valid_frontmatter(project_root: Path) -> None:
    local_skills = list((project_root / ".agents" / "skills").glob("*/SKILL.md"))
    runtime_skills = list((project_root / "workspace" / "skills").glob("*/SKILL.md"))
    assert local_skills and runtime_skills, "Both coding-agent and runtime skills must exist"
    skills = local_skills + runtime_skills
    for skill in skills:
        text = skill.read_text(encoding="utf-8")
        assert text.startswith("---\nname: "), skill
        header = text.split("---")[1]
        keys = {line.split(":")[0] for line in header.strip().splitlines()}
        assert keys == {"name", "description"}, skill


def test_company_design_tokens_match_renderer(project_root: Path) -> None:
    from jinja2 import Environment, FileSystemLoader

    templates = project_root / "src/paid_media_agent/reports/templates"
    theme = (
        Environment(loader=FileSystemLoader(templates), autoescape=True)
        .get_template("tokens.j2")
        .module
    )
    design = (project_root / "workspace/skills/report-design/DESIGN.md").read_text()
    documented = {}
    for line in design.splitlines():
        cells = line.split("|")
        if len(cells) != 4:
            continue
        names = re.findall(r"`([^`]+)`", cells[1])
        values = re.findall(r"`([^`]+)`", cells[2])
        if names and values:
            documented.update(zip(names, values, strict=True))
    assert documented == theme.tokens


def _deploy_prompt(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"```text\n(Deploy LangChain's open-source paid media agent.*?)```", text, re.S
    )
    assert match, f"{path.name} has no one-paste deploy prompt"
    return match.group(1)


def test_the_one_paste_deploy_prompt_is_the_same_everywhere(project_root: Path) -> None:
    """The README and the deploy guide hand coding agents one prompt; it names real commands."""
    prompt = _deploy_prompt(project_root / "README.md")
    assert prompt == _deploy_prompt(project_root / "docs" / "deploy-mda.md")
    assert "never ask me to paste a key" in prompt
    for skill in re.findall(r"the `([a-z-]+)` skill", prompt):
        assert (project_root / ".agents" / "skills" / skill / "SKILL.md").is_file(), skill
    runner = CliRunner()
    for command in re.findall(r"`uv run paid-media-agent ([a-z ]+?)(?: --| <|`)", prompt):
        result = runner.invoke(main, [*command.split(), "--help"])
        assert result.exit_code == 0, (command, result.output)
