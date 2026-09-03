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
        if any(part in {".venv", ".git", ".mda", "workspace"} for part in path.parts):
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
        "serve",
        "slack",
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
    } <= documented
    runner = CliRunner()
    for command in documented:
        result = runner.invoke(main, [command, "--help"])
        assert result.exit_code == 0, f"{command}: {result.output}"


def test_skills_have_valid_frontmatter(project_root: Path) -> None:
    for skill in (project_root / "skills").glob("*/SKILL.md"):
        text = skill.read_text(encoding="utf-8")
        assert text.startswith("---\nname: "), skill
        header = text.split("---")[1]
        keys = {line.split(":")[0] for line in header.strip().splitlines()}
        assert keys == {"name", "description"}, skill
