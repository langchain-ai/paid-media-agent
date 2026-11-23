"""Managed Deep Agents entry. Thin: it only hands the shared components to `define_deep_agent`.

The background helpers are async subagents (`src/paid_media_agent/subagents.py`): `worker` runs
every task the lead starts, on the model the lead picks, and `general-purpose` is declared read-only
so MDA adds no default copy with the lead's tools. Each is written as a dict whose literal `name`
and `"async": True` come after the spread, so `mda build` finds them without running this file.
"""

from __future__ import annotations

from pathlib import Path

from managed_deepagents import define_deep_agent

from paid_media_agent.config import Settings
from paid_media_agent.runtime.mda import build_mda_components

_settings = Settings()
_components = build_mda_components(_settings, project_root=Path(__file__).parent)

agent = define_deep_agent(
    name="paid-media-agent",
    model=_components.model,
    tools=list(_components.tools),
    middleware=list(_components.middleware),
    subagents=[
        {**_components.helper("worker"), "name": "worker", "async": True},
        {**_components.helper("general-purpose"), "name": "general-purpose", "async": True},
    ],
    interrupt_on=dict(_components.interrupt_on) or None,
    metadata=dict(_components.run_metadata) or None,
)
