"""Where the model's files live: the repository (local) or a LangSmith sandbox (sandbox).

Both worlds expose the same paths. Skills sit at `/skills`, the business wiki at
`/docs/business-context`, and everything host tools produce lands under `/workspace`. In sandbox
mode those project files are uploaded when the sandbox opens, host-written artifacts are mirrored
as they are written, and PDF rendering runs inside the container, where the native libraries are
baked in. The model never gets a shell in either world; `execute` stays host-driven.
"""

from __future__ import annotations

import atexit
import re
import secrets
import shlex
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from deepagents.backends import FilesystemBackend

from paid_media_agent.config import BackendName, Settings
from paid_media_agent.reports.render import HostPdfEngine, PdfEngine
from paid_media_agent.tools.artifacts import FileSink

if TYPE_CHECKING:
    from deepagents.backends.protocol import BackendProtocol, SandboxBackendProtocol

WORKSPACE = "/workspace"
WORKSPACE_DIRS = ("in", "out", "analysis")
MOUNTED_DIRS = ("skills", "docs/business-context")
"""Project directories the model reads. Same absolute paths in the repository and the sandbox."""
_PROBE_HTML = "<html><body><h1>Paid Media Agent sandbox probe</h1></body></html>"
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def snapshot_reference(value: str | None) -> dict[str, str]:
    """`snapshot_id=` for an immutable id, `snapshot_name=` otherwise, nothing for the default.

    Snapshots built from a Dockerfile resolve reliably by id only; `sandbox publish` stores the
    id, and a hand-picked name still works where the platform tags it.
    """
    if not value:
        return {}
    return {"snapshot_id": value} if _UUID_RE.match(value.lower()) else {"snapshot_name": value}


class SandboxError(Exception):
    pass


class Sandbox:
    """One LangSmith sandbox and the operations host code needs on it."""

    def __init__(
        self, backend: SandboxBackendProtocol, *, name: str, close: Callable[[], None]
    ) -> None:
        self.backend = backend
        self.name = name
        self._close = close

    def put(self, path: str, data: bytes) -> None:
        for response in self.backend.upload_files([(path, data)]):
            if response.error:
                raise SandboxError(f"upload {path}: {response.error}")

    def get(self, path: str) -> bytes:
        response = self.backend.download_files([path])[0]
        if response.error or response.content is None:
            raise SandboxError(f"download {path}: {response.error or 'empty'}")
        return response.content

    def run(self, command: str, *, timeout: int = 120) -> str:
        """Run a shell command and return its output. Non-zero exit raises."""
        response = self.backend.execute(command, timeout=timeout)
        if response.exit_code != 0:
            raise SandboxError(f"`{command}` exited {response.exit_code}: {response.output[:400]}")
        return response.output

    def mount_project(self, project_root: Path) -> int:
        """Upload skills and wiki pages and create the workspace layout. Returns the file count."""
        self.run("mkdir -p " + " ".join(f"{WORKSPACE}/{d}" for d in WORKSPACE_DIRS))
        files: list[tuple[str, bytes]] = []
        for directory in MOUNTED_DIRS:
            for path in sorted((project_root / directory).rglob("*")):
                if path.is_file():
                    files.append(
                        (f"/{path.relative_to(project_root).as_posix()}", path.read_bytes())
                    )
        for response in self.backend.upload_files(files):
            if response.error:
                raise SandboxError(f"upload {response.path}: {response.error}")
        return len(files)

    def close(self) -> None:
        self._close()


class WorkspaceMirror:
    """Copies host-written workspace files into the sandbox so the model can read them."""

    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    def put(self, relative_path: str, data: bytes) -> None:
        self._sandbox.put(f"{WORKSPACE}/{relative_path}", data)


class SandboxPdfEngine:
    """Renders PDFs with the WeasyPrint baked into the sandbox image."""

    def __init__(self, sandbox: Sandbox) -> None:
        self._sandbox = sandbox

    def available(self) -> tuple[bool, str]:
        try:
            self._sandbox.run("python -c 'import weasyprint'", timeout=60)
        except SandboxError as exc:
            return False, f"sandbox has no WeasyPrint: {exc}"
        return True, "sandbox"

    def write_pdf(self, html: str, *, base_url: str, target: Path) -> None:
        del base_url  # the sandbox renders from its own copy of the page
        html_path = f"{WORKSPACE}/out/{target.stem}.html"
        pdf_path = f"{WORKSPACE}/out/{target.name}"
        self._sandbox.put(html_path, html.encode("utf-8"))
        script = (
            f"from weasyprint import HTML; HTML(filename={html_path!r}).write_pdf({pdf_path!r})"
        )
        self._sandbox.run(f"python -c {shlex.quote(script)}", timeout=300)
        target.write_bytes(self._sandbox.get(pdf_path))


@dataclass(frozen=True)
class Backend:
    """What Deep Agents mounts, plus the host-side seams that keep both worlds in sync."""

    kind: BackendName
    model_fs: BackendProtocol
    mirror: FileSink | None
    pdf_engine: PdfEngine
    close: Callable[[], None]


def local_backend(project_root: Path) -> Backend:
    return Backend(
        kind="local",
        model_fs=FilesystemBackend(root_dir=project_root, virtual_mode=True),
        mirror=None,
        pdf_engine=HostPdfEngine(),
        close=lambda: None,
    )


SANDBOX_DELETE_AFTER_STOP_SECONDS = 300
"""A sandbox that idles out is deleted by the platform; `close()` is only the fast path."""


def open_sandbox(settings: Settings, *, name: str | None = None) -> Sandbox:
    """Create a sandbox from the configured snapshot.

    `close()` deletes it. Servers that die without running exit handlers leave it to the
    platform: it stops after the idle TTL and is deleted shortly after.
    """
    from deepagents.backends import LangSmithSandbox  # noqa: PLC0415 - optional dependency path
    from langsmith.sandbox import SandboxClient, SandboxClientError  # noqa: PLC0415

    resolved_name = name or f"paid-media-{secrets.token_hex(4)}"
    client = SandboxClient()
    try:
        reference = snapshot_reference(settings.paid_media_sandbox_snapshot)
        created = client.create_sandbox(
            reference.get("snapshot_id"),
            snapshot_name=reference.get("snapshot_name"),
            name=resolved_name,
            idle_ttl_seconds=settings.paid_media_sandbox_idle_ttl_seconds,
            delete_after_stop_seconds=SANDBOX_DELETE_AFTER_STOP_SECONDS,
        )
    except SandboxClientError as exc:
        raise SandboxError(f"could not create a sandbox: {exc}") from None
    return Sandbox(
        LangSmithSandbox(sandbox=created),
        name=resolved_name,
        close=lambda: client.delete_sandbox(resolved_name),
    )


def build_backend(settings: Settings, *, project_root: Path) -> Backend:
    """Resolve `PAID_MEDIA_BACKEND`. Sandbox mode opens one sandbox for the life of the process."""
    if settings.paid_media_backend == "local":
        return local_backend(project_root)
    sandbox = open_sandbox(settings)
    try:
        sandbox.mount_project(project_root)
    except SandboxError:
        sandbox.close()
        raise
    atexit.register(sandbox.close)
    return Backend(
        kind="sandbox",
        model_fs=sandbox.backend,
        mirror=WorkspaceMirror(sandbox),
        pdf_engine=SandboxPdfEngine(sandbox),
        close=sandbox.close,
    )


class ProbeCheck(NamedTuple):
    name: str
    status: str
    detail: str


def probe_sandbox(sandbox: Sandbox, project_root: Path) -> list[ProbeCheck]:
    """Prove a sandbox can host the agent: mounts, workspace, PDF rendering, and no secrets."""
    checks: list[ProbeCheck] = []

    def check(name: str, action: Callable[[], str]) -> None:
        try:
            checks.append(ProbeCheck(name, "ok", action()))
        except SandboxError as exc:
            checks.append(ProbeCheck(name, "fail", str(exc)[:300]))

    def render() -> str:
        engine = SandboxPdfEngine(sandbox)
        available, detail = engine.available()
        if not available:
            raise SandboxError(detail)
        target = project_root / "workspace" / "out" / "sandbox-probe.pdf"
        engine.write_pdf(_PROBE_HTML, base_url="", target=target)
        head = target.read_bytes()[:5]
        target.unlink()
        if head != b"%PDF-":
            raise SandboxError("rendered file is not a PDF")
        return "PDF rendered in the sandbox"

    def secrets_absent() -> str:
        count = sandbox.run("env | grep -ciE 'api_key|token|secret' || true").strip()
        if count != "0":
            raise SandboxError("key-like environment values are visible inside the sandbox")
        return "no key-like environment values"

    check("python", lambda: sandbox.run("python --version").strip())
    check("mount", lambda: f"{sandbox.mount_project(project_root)} files uploaded")
    check("skills", lambda: sandbox.run("ls /skills").strip().replace("\n", ", "))
    check("wiki", lambda: sandbox.run("ls /docs/business-context | wc -l").strip() + " pages")
    check("workspace", lambda: sandbox.run(f"ls {WORKSPACE}").strip().replace("\n", ", "))
    check("pdf", render)
    check("secrets_absent", secrets_absent)
    return checks
