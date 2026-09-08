"""Model-facing tools that save what the organization tells the agent during onboarding.

Both write host-side under `docs/org/` and mirror the result into the sandbox when one is active,
so the model can read back exactly what it saved. No approval step: this is the user's own context,
and every write is echoed to them.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from paid_media_agent.middleware.redaction import sanitize_exception
from paid_media_agent.org import (
    QUESTIONS,
    SourceError,
    add_link,
    load_profile,
    save_profile,
)

UPDATE_ORG_PROFILE_TOOL = "update_org_profile"
ADD_ORG_SOURCE_TOOL = "add_org_source"
ORG_TOOLS: tuple[str, ...] = (UPDATE_ORG_PROFILE_TOOL, ADD_ORG_SOURCE_TOOL)

Publish = Callable[[Path], None]


class OrgProfileUpdate(BaseModel):
    """Only the fields the user just answered; omitted fields keep their current value."""

    business: str | None = Field(default=None, description=QUESTIONS[0].question)
    primary_conversion: str | None = Field(default=None, description=QUESTIONS[1].question)
    targets: str | None = Field(default=None, description=QUESTIONS[2].question)
    monthly_budget: str | None = Field(default=None, description=QUESTIONS[3].question)
    markets: str | None = Field(default=None, description=QUESTIONS[4].question)
    seasonality: str | None = Field(default=None, description=QUESTIONS[5].question)
    naming: str | None = Field(default=None, description=QUESTIONS[6].question)
    approvers: str | None = Field(default=None, description=QUESTIONS[7].question)
    notes: str | None = Field(default=None, description="Anything else worth remembering.")


class OrgSourceArgs(BaseModel):
    url: str = Field(
        description="A public https link the user shared (docs, a dashboard export, a brief)."
    )
    note: str = Field(
        default="", max_length=200, description="One line on what it is, in the user's words."
    )


def build_org_tools(root: Path, publish: Publish | None = None) -> list[BaseTool]:
    def _publish(paths: list[Path]) -> None:
        if publish is not None:
            for path in paths:
                publish(path)

    def _update(**kwargs: Any) -> str:
        update = OrgProfileUpdate.model_validate(kwargs)
        changes = {k: v.strip() for k, v in update.model_dump().items() if v is not None}
        if not changes:
            return json.dumps({"error": True, "detail": "nothing to update"})
        profile = load_profile(root).model_copy(update=changes)
        written = save_profile(root, profile)
        _publish(written)
        return json.dumps(
            {
                "saved": sorted(changes),
                "answered": profile.answered(),
                "of": len(QUESTIONS),
                "pages": ["/docs/org/goals.md", "/docs/org/conventions.md"],
            }
        )

    def _add_source(**kwargs: Any) -> str:
        args = OrgSourceArgs.model_validate(kwargs)
        try:
            stored = add_link(root, args.url, args.note)
        except SourceError as exc:
            return json.dumps({"error": True, "detail": str(exc)})
        except Exception as exc:
            return json.dumps({"error": True, "detail": sanitize_exception(exc)})
        _publish([stored, stored.parent.parent / "sources.md"])
        preview = stored.read_text(encoding="utf-8")[:400]
        return json.dumps({"stored": f"/docs/org/sources/{stored.name}", "preview": preview})

    return [
        StructuredTool(
            name=UPDATE_ORG_PROFILE_TOOL,
            description=(
                "Save answers from the organization onboarding interview (business, conversion that "
                "counts, targets, budget, markets, seasonality, naming, approvers). Pass only the "
                "fields just answered. The pages under /docs/org are re-rendered."
            ),
            args_schema=OrgProfileUpdate,
            func=_update,
        ),
        StructuredTool(
            name=ADD_ORG_SOURCE_TOOL,
            description=(
                "Store the text of a public https link the user shared (a brief, a plan, a dashboard "
                "export) under /docs/org/sources and list it on /docs/org/sources.md."
            ),
            args_schema=OrgSourceArgs,
            func=_add_source,
        ),
    ]
