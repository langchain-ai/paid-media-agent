"""Graph factory for LangGraph Server and Studio (`uv run langgraph dev`).

The server owns persistence, so the graph is compiled without a checkpointer. Everything else is
the shared assembly: fixture catalog without a Pipeboard token, live catalog with one.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from paid_media_agent.config import Settings
from paid_media_agent.runtime.local import compile_graph
from paid_media_agent.runtime.mda import build_mda_components
from paid_media_agent.runtime.sandbox import build_backend

STUDIO_PORT = 2024
STUDIO_URL = f"https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:{STUDIO_PORT}"


def project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "instructions.md").exists() and (candidate / "skills").is_dir():
            return candidate
    return Path.cwd()


def _build() -> CompiledStateGraph[Any, Any, Any, Any]:
    root = project_root()
    settings = Settings(_env_file=str(root / ".env"))
    backend = build_backend(settings, project_root=root)
    components = build_mda_components(settings, project_root=root, backend=backend)
    return compile_graph(components, project_root=root, checkpointer=None)


_graph: CompiledStateGraph[Any, Any, Any, Any] | None = None


async def make_graph() -> CompiledStateGraph[Any, Any, Any, Any]:
    """Build the agent for a local LangGraph Server. Requires a configured model and key.

    The server calls this factory from its event loop and flags blocking calls (blockbuster), so
    the catalog and skill loading run in a worker thread. One process serves one configuration,
    so the compiled graph is built once and reused across runs.
    """
    global _graph  # noqa: PLW0603 - process-wide cache for a long-lived server
    if _graph is None:
        _graph = await asyncio.to_thread(_build)
    return _graph
