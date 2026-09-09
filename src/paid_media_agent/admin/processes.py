"""Start and stop long-running local processes from fixed command templates only."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

PROCESS_TEMPLATES: dict[str, tuple[str, ...]] = {
    "mda-dev": (sys.executable, "-m", "managed_deepagents", "dev"),
    "mda-deploy": (sys.executable, "-m", "managed_deepagents", "deploy", "."),
}
CONFIRM_REQUIRED: frozenset[str] = frozenset({"mda-deploy"})
"""Outward-facing processes that need an explicit confirmation before they start."""


class ProcessView(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    command: str
    running: bool
    pid: int | None
    started_at: datetime | None
    returncode: int | None
    log_path: str
    log_tail: str = ""


class ProcessError(RuntimeError):
    pass


class ProcessManager:
    def __init__(self, root: Path, *, log_dir: Path | None = None) -> None:
        self._root = root
        self._log_dir = log_dir or root / "workspace" / "logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._procs: dict[str, subprocess.Popen[bytes]] = {}
        self._started: dict[str, datetime] = {}

    def command_for(self, name: str) -> tuple[str, ...]:
        try:
            return PROCESS_TEMPLATES[name]
        except KeyError:
            raise ProcessError(f"unknown process {name}") from None

    def display_command(self, name: str) -> str:
        friendly = {
            "serve": "uv run paid-media-agent serve",
            "slack": "uv run paid-media-agent slack",
            "mda-dev": "uv run mda dev",
            "mda-deploy": "uv run mda deploy .",
            "studio": "uv run langgraph dev",
        }
        return friendly.get(name, " ".join(self.command_for(name)))

    def _log_path(self, name: str) -> Path:
        return self._log_dir / f"{name}.log"

    def start(
        self, name: str, *, confirmed: bool = False, env: dict[str, str] | None = None
    ) -> ProcessView:
        command = self.command_for(name)
        if name in CONFIRM_REQUIRED and not confirmed:
            raise ProcessError(f"{name} requires explicit confirmation")
        existing = self._procs.get(name)
        if existing is not None and existing.poll() is None:
            raise ProcessError(f"{name} is already running")
        log = self._log_path(name)
        with log.open("ab") as handle:
            handle.write(
                f"\n--- {datetime.now(UTC).isoformat()} start: {' '.join(command)}\n".encode()
            )
            proc = subprocess.Popen(  # noqa: S603 - fixed template, no shell, no user arguments
                command,
                cwd=self._root,
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env={**os.environ, **(env or {})},
            )
        self._procs[name] = proc
        self._started[name] = datetime.now(UTC)
        return self.view(name)

    def stop(self, name: str) -> ProcessView:
        proc = self._procs.get(name)
        if proc is None or proc.poll() is not None:
            return self.view(name)
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
        except ProcessLookupError:
            pass
        return self.view(name)

    def stop_all(self) -> None:
        for name in list(self._procs):
            self.stop(name)

    def tail(self, name: str, lines: int = 60) -> str:
        path = self._log_path(name)
        if not path.exists():
            return ""
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        # Child processes write terminal colors; the page shows plain text.
        return "\n".join(_ANSI_RE.sub("", line) for line in content[-lines:])

    def view(self, name: str) -> ProcessView:
        proc = self._procs.get(name)
        running = proc is not None and proc.poll() is None
        return ProcessView(
            name=name,
            command=self.display_command(name),
            running=running,
            pid=proc.pid if running and proc is not None else None,
            started_at=self._started.get(name) if proc is not None else None,
            returncode=proc.returncode if proc is not None and not running else None,
            log_path=str(self._log_path(name).relative_to(self._root))
            if self._log_path(name).is_relative_to(self._root)
            else str(self._log_path(name)),
            log_tail=self.tail(name, 40),
        )

    def views(self) -> list[ProcessView]:
        return [self.view(name) for name in PROCESS_TEMPLATES]
