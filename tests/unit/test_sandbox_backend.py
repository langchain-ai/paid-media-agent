"""Sandbox mode keeps the model's world identical to production without a live sandbox here."""

from __future__ import annotations

from pathlib import Path

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)

from paid_media_agent.runtime.sandbox import (
    WORKSPACE,
    Sandbox,
    SandboxPdfEngine,
    WorkspaceMirror,
    probe_sandbox,
    snapshot_reference,
)
from paid_media_agent.tools.artifacts import ArtifactStore


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
        if command.startswith("ls /docs"):
            return ExecuteResponse(output="9", exit_code=0)
        if command.startswith("env |"):
            return ExecuteResponse(output="0", exit_code=0)
        return ExecuteResponse(output="ok", exit_code=0)


def _sandbox(backend: FakeSandboxBackend) -> Sandbox:
    return Sandbox(backend, name="fake", close=lambda: None)  # type: ignore[arg-type]


def test_mount_uses_the_same_absolute_paths_as_the_repository(tmp_path: Path) -> None:
    (tmp_path / "skills" / "paid-media-analysis").mkdir(parents=True)
    (tmp_path / "skills" / "paid-media-analysis" / "SKILL.md").write_text("# skill")
    (tmp_path / "docs" / "business-context").mkdir(parents=True)
    (tmp_path / "docs" / "business-context" / "goals.md").write_text("# goals")
    backend = FakeSandboxBackend()

    count = _sandbox(backend).mount_project(tmp_path)

    assert count == 2
    assert backend.files["/skills/paid-media-analysis/SKILL.md"] == b"# skill"
    assert backend.files["/docs/business-context/goals.md"] == b"# goals"
    assert backend.commands[0].startswith("mkdir -p /workspace/in")


def test_artifacts_written_by_host_tools_appear_in_the_sandbox(tmp_path: Path) -> None:
    backend = FakeSandboxBackend()
    store = ArtifactStore(tmp_path / "workspace", mirror=WorkspaceMirror(_sandbox(backend)))

    metadata = store.write_json("analysis", {"rows": 3}, schema_version="test/1")

    mirrored = backend.files[f"{WORKSPACE}/{metadata.path}"]
    assert mirrored == (tmp_path / "workspace" / metadata.path).read_bytes()


def test_pdf_renders_inside_the_sandbox_and_lands_on_the_host(tmp_path: Path) -> None:
    backend = FakeSandboxBackend()
    engine = SandboxPdfEngine(_sandbox(backend))
    target = tmp_path / "rpt_1.pdf"

    assert engine.available() == (True, "sandbox")
    engine.write_pdf("<html/>", base_url="", target=target)

    assert target.read_bytes().startswith(b"%PDF-")
    assert backend.files[f"{WORKSPACE}/out/rpt_1.html"] == b"<html/>"


def test_probe_reports_a_missing_pdf_renderer(tmp_path: Path) -> None:
    for directory in ("skills", "docs/business-context", "workspace/out"):
        (tmp_path / directory).mkdir(parents=True)
    checks = {
        c.name: c for c in probe_sandbox(_sandbox(FakeSandboxBackend(weasyprint=False)), tmp_path)
    }

    assert checks["mount"].status == "ok"
    assert checks["pdf"].status == "fail"
    assert "WeasyPrint" in checks["pdf"].detail
    assert checks["secrets_absent"].status == "ok"


def test_snapshot_reference_prefers_immutable_ids() -> None:
    assert snapshot_reference("4b6f76ed-4626-48d1-bdd1-d974623c438c") == {
        "snapshot_id": "4b6f76ed-4626-48d1-bdd1-d974623c438c"
    }
    assert snapshot_reference("paid-media-agent-sandbox") == {
        "snapshot_name": "paid-media-agent-sandbox"
    }
    assert snapshot_reference(None) == {}
