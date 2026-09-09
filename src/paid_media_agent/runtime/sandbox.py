"""Snapshot tooling for the sandbox Managed Deep Agents gives every thread.

MDA provisions and mounts the sandbox itself, one per durable thread, from the declaration in
`sandbox/__init__.py`. This module only helps produce and prove that declaration: build the
snapshot from `sandbox/Dockerfile` (`sandbox publish`), point at an existing one (`sandbox use`),
and open a throwaway sandbox to probe it (`sandbox test`). The model never gets a shell.
"""

from __future__ import annotations

import re
import secrets
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from paid_media_agent.config import Settings

if TYPE_CHECKING:
    from deepagents.backends.protocol import SandboxBackendProtocol

WORKSPACE = "/workspace"
WORKSPACE_DIRS = ("in", "out", "analysis")
MOUNTED_DIRS = ("skills",)
"""What the model reads: skills, including the wiki under `skills/paid-media-wiki`."""
_PROBE_HTML = "<html><body><h1>Paid Media Agent sandbox probe</h1></body></html>"
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
PROBE_IDLE_TTL_SECONDS = 300
PROBE_DELETE_AFTER_STOP_SECONDS = 300
"""A probe sandbox that outlives its process is stopped and deleted by the platform."""
SANDBOX_EGRESS = {"access_control": {"allow_list": ["localhost", "127.0.0.1"]}}
"""Provider and platform calls run host-side; the sandbox itself needs no outbound network."""


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
    """One LangSmith sandbox and the operations the probe needs on it."""

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
        """Upload the skills (wiki included) and create the workspace layout. Returns the file count."""
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


class SandboxPdfEngine:
    """Renders a PDF with the WeasyPrint baked into the snapshot; the probe's rendering check."""

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


def open_sandbox(settings: Settings, *, name: str | None = None) -> Sandbox:
    """Create a short-lived sandbox from the configured snapshot. `close()` deletes it."""
    from deepagents.backends import LangSmithSandbox
    from langsmith.sandbox import SandboxClient, SandboxClientError

    resolved_name = name or f"paid-media-probe-{secrets.token_hex(4)}"
    client = SandboxClient()
    try:
        reference = snapshot_reference(settings.paid_media_sandbox_snapshot)
        created = client.create_sandbox(
            reference.get("snapshot_id"),
            snapshot_name=reference.get("snapshot_name"),
            name=resolved_name,
            idle_ttl_seconds=PROBE_IDLE_TTL_SECONDS,
            delete_after_stop_seconds=PROBE_DELETE_AFTER_STOP_SECONDS,
            proxy_config=SANDBOX_EGRESS,
        )
    except SandboxClientError as exc:
        raise SandboxError(f"could not create a sandbox: {exc}") from None
    return Sandbox(
        LangSmithSandbox(sandbox=created),
        name=resolved_name,
        close=lambda: client.delete_sandbox(resolved_name),
    )


class ProbeCheck(NamedTuple):
    name: str
    status: str
    detail: str


def probe_sandbox(sandbox: Sandbox, project_root: Path) -> list[ProbeCheck]:
    """Prove a snapshot can host the agent: mounts, workspace, PDF rendering, and no secrets."""
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
    check("wiki", lambda: sandbox.run("ls /skills/paid-media-wiki | wc -l").strip() + " pages")
    check("workspace", lambda: sandbox.run(f"ls {WORKSPACE}").strip().replace("\n", ", "))
    check("pdf", render)
    check("secrets_absent", secrets_absent)
    return checks
