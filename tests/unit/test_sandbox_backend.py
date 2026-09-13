"""The snapshot probe, exercised against an in-memory stand-in for a LangSmith sandbox."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)

from paid_media_agent.admin import actions
from paid_media_agent.admin.envfile import read_env
from paid_media_agent.runtime.sandbox import (
    WORKSPACE,
    Sandbox,
    SandboxPdfEngine,
    probe_sandbox,
    snapshot_reference,
)


class FakeSandboxBackend:
    """In-memory stand-in for a LangSmith sandbox: files plus the few commands the host runs."""

    def __init__(self, *, weasyprint: bool = True) -> None:
        self.files: dict[str, bytes] = {}
        self.commands: list[str] = []
        self._weasyprint = weasyprint

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        self.files.update(dict(files))
        return [FileUploadResponse(path=p) for p, _ in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [FileDownloadResponse(path=p, content=self.files.get(p)) for p in paths]

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        del timeout
        self.commands.append(command)
        if "import weasyprint" in command:
            return ExecuteResponse(output="", exit_code=0 if self._weasyprint else 1)
        if "write_pdf" in command:
            self.files[f"{WORKSPACE}/out/probe.pdf"] = b"%PDF-1.7 fake"
            for path in [p for p in self.files if p.endswith(".html")]:
                self.files[path[:-5] + ".pdf"] = b"%PDF-1.7 fake"
            return ExecuteResponse(output="", exit_code=0)
        if command.startswith("ls /skills"):
            names = {p.split("/")[2] for p in self.files if p.startswith("/skills/")}
            return ExecuteResponse(output="\n".join(sorted(names)), exit_code=0)
        if command.startswith("ls /skills/paid-media-wiki"):
            return ExecuteResponse(output="9", exit_code=0)
        if command.startswith("env |"):
            return ExecuteResponse(output="0", exit_code=0)
        return ExecuteResponse(output="ok", exit_code=0)


def _sandbox(backend: FakeSandboxBackend) -> Sandbox:
    return Sandbox(backend, name="fake", close=lambda: None)  # type: ignore[arg-type]


def test_mount_uses_the_same_absolute_paths_as_the_repository(tmp_path: Path) -> None:
    (tmp_path / "workspace" / "skills" / "paid-media-analysis").mkdir(parents=True)
    (tmp_path / "skills").symlink_to("workspace/skills", target_is_directory=True)
    (tmp_path / "skills" / "paid-media-analysis" / "SKILL.md").write_text("# skill")
    (tmp_path / "skills" / "paid-media-wiki").mkdir(parents=True)
    (tmp_path / "skills" / "paid-media-wiki" / "goals.md").write_text("# goals")
    local_skill = tmp_path / ".agents" / "skills" / "paid-media-onboarding" / "SKILL.md"
    local_skill.parent.mkdir(parents=True)
    local_skill.write_text("# Local setup only")
    backend = FakeSandboxBackend()

    count = _sandbox(backend).mount_project(tmp_path)

    assert count == 2
    assert backend.files["/skills/paid-media-analysis/SKILL.md"] == b"# skill"
    assert backend.files["/skills/paid-media-wiki/goals.md"] == b"# goals"
    assert backend.commands[0].startswith("mkdir -p /workspace/in")


def test_pdf_renders_inside_the_sandbox_and_lands_on_the_host(tmp_path: Path) -> None:
    backend = FakeSandboxBackend()
    engine = SandboxPdfEngine(_sandbox(backend))
    target = tmp_path / "rpt_1.pdf"

    assert engine.available() == (True, "sandbox")
    engine.write_pdf("<html/>", base_url="", target=target)

    assert target.read_bytes().startswith(b"%PDF-")
    assert backend.files[f"{WORKSPACE}/out/rpt_1.html"] == b"<html/>"


def test_probe_reports_a_missing_pdf_renderer(tmp_path: Path) -> None:
    for directory in ("skills/paid-media-wiki", "workspace/out"):
        (tmp_path / directory).mkdir(parents=True)
    checks = {
        c.name: c for c in probe_sandbox(_sandbox(FakeSandboxBackend(weasyprint=False)), tmp_path)
    }

    assert checks["mount"].status == "ok"
    assert checks["pdf"].status == "fail"
    assert "WeasyPrint" in checks["pdf"].detail
    assert checks["secrets_absent"].status == "ok"


def test_snapshot_reference_prefers_immutable_ids() -> None:
    assert snapshot_reference("00000000-0000-4000-8000-000000000001") == {
        "snapshot_id": "00000000-0000-4000-8000-000000000001"
    }
    assert snapshot_reference("paid-media-agent-sandbox") == {
        "snapshot_name": "paid-media-agent-sandbox"
    }
    assert snapshot_reference(None) == {}


def test_publish_packages_the_shared_recipe_without_project_secrets(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import langsmith.sandbox

    snapshot_id = "00000000-0000-4000-8000-000000000001"
    directory = tmp_path / "sandbox"
    directory.mkdir()
    for name in ("Dockerfile", "setup.sh"):
        (directory / name).write_bytes((project_root / "sandbox" / name).read_bytes())
    (tmp_path / ".env").write_text("# private configuration\n")
    (directory / "private.txt").write_text("not part of the build")

    class Client:
        def create_snapshot_from_dockerfile(self, name, dockerfile, **kwargs):
            context = Path(kwargs["context"])
            assert {path.name for path in context.iterdir()} == {"Dockerfile", "setup.sh"}
            assert (context / "setup.sh").read_bytes() == (directory / "setup.sh").read_bytes()
            return SimpleNamespace(id=snapshot_id)

        def wait_for_snapshot(self, current_id, **kwargs):
            assert current_id == snapshot_id
            return SimpleNamespace(id=current_id, status="ready")

    monkeypatch.setattr(langsmith.sandbox, "SandboxClient", lambda **_kwargs: Client())
    result = actions.sandbox_publish(tmp_path, name="test-recipe")

    assert result.ok
    assert read_env(tmp_path)["PAID_MEDIA_SANDBOX_SNAPSHOT"] == snapshot_id
    assert snapshot_id in (directory / "__init__.py").read_text()


def test_publish_rejects_a_missing_recipe_before_starting_a_cloud_build(tmp_path: Path) -> None:
    (tmp_path / "sandbox").mkdir()
    (tmp_path / "sandbox" / "Dockerfile").write_text("FROM python:3.13-slim\n")

    result = actions.sandbox_publish(tmp_path, name="missing-recipe")

    assert result.status == "fail"
    assert "setup.sh is missing" in result.summary
    assert not (tmp_path / ".env").exists()
