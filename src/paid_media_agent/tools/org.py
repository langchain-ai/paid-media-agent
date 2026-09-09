"""Model-facing tools for the organization's own context: read it, save answers, store links.

The pages live under `docs/org/` on the host. The model reaches them through `get_org_context`
rather than the filesystem, so the same call works locally and inside the sandbox Managed Deep
Agents gives each thread. No approval step: this is the user's own context, and every write is
echoed back to them.
"""

from __future__ import annotations

import json
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
    org_dir,
    render_conventions,
    render_goals,
    save_profile,
)

GET_ORG_CONTEXT_TOOL = "get_org_context"
UPDATE_ORG_PROFILE_TOOL = "update_org_profile"
ADD_ORG_SOURCE_TOOL = "add_org_source"
ORG_TOOLS: tuple[str, ...] = (GET_ORG_CONTEXT_TOOL, UPDATE_ORG_PROFILE_TOOL, ADD_ORG_SOURCE_TOOL)
SOURCE_TEXT_CHARS = 12_000
"""A shared brief is returned in one piece up to this size; longer ones are cut with a note."""


class OrgContextArgs(BaseModel):
    source: str | None = Field(
        default=None,
        description="Name of a shared source (from the sources list) to read in full.",
    )


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


def _sources(root: Path) -> list[str]:
    directory = org_dir(root) / "sources"
    return sorted(p.name for p in directory.iterdir() if p.is_file()) if directory.exists() else []


def build_org_tools(root: Path) -> list[BaseTool]:
    def _context(**kwargs: Any) -> str:
        args = OrgContextArgs.model_validate(kwargs)
        names = _sources(root)
        if args.source:
            if args.source not in names:
                return json.dumps({"error": True, "detail": "unknown source", "sources": names})
            text = (org_dir(root) / "sources" / args.source).read_text(encoding="utf-8")
            cut = len(text) > SOURCE_TEXT_CHARS
            return json.dumps(
                {"source": args.source, "text": text[:SOURCE_TEXT_CHARS], "truncated": cut}
            )
        profile = load_profile(root)
        return json.dumps(
            {
                "answered": profile.answered(),
                "of": len(QUESTIONS),
                "goals": render_goals(profile),
                "conventions": render_conventions(profile),
                "sources": names,
            }
        )

    def _update(**kwargs: Any) -> str:
        update = OrgProfileUpdate.model_validate(kwargs)
        changes = {k: v.strip() for k, v in update.model_dump().items() if v is not None}
        if not changes:
            return json.dumps({"error": True, "detail": "nothing to update"})
        profile = load_profile(root).model_copy(update=changes)
        save_profile(root, profile)
        return json.dumps(
            {"saved": sorted(changes), "answered": profile.answered(), "of": len(QUESTIONS)}
        )

    def _add_source(**kwargs: Any) -> str:
        args = OrgSourceArgs.model_validate(kwargs)
        try:
            stored = add_link(root, args.url, args.note)
        except SourceError as exc:
            return json.dumps({"error": True, "detail": str(exc)})
        except Exception as exc:
            return json.dumps({"error": True, "detail": sanitize_exception(exc)})
        preview = stored.read_text(encoding="utf-8")[:400]
        return json.dumps({"stored": stored.name, "preview": preview})

    return [
        StructuredTool(
            name=GET_ORG_CONTEXT_TOOL,
            description=(
                "This organization's own context: goals, the conversion that counts, targets, "
                "budget, markets, seasonality, naming, approvers, and the names of shared sources. "
                "Call it before an analysis; it overrides the generic wiki. Pass `source` to read "
                "one shared brief or export in full."
            ),
            args_schema=OrgContextArgs,
            func=_context,
        ),
        StructuredTool(
            name=UPDATE_ORG_PROFILE_TOOL,
            description=(
                "Save answers from the organization onboarding interview (business, conversion that "
                "counts, targets, budget, markets, seasonality, naming, approvers). Pass only the "
                "fields just answered; get_org_context returns the result."
            ),
            args_schema=OrgProfileUpdate,
            func=_update,
        ),
        StructuredTool(
            name=ADD_ORG_SOURCE_TOOL,
            description=(
                "Store the text of a public https link the user shared (a brief, a plan, a dashboard "
                "export) so get_org_context can return it later."
            ),
            args_schema=OrgSourceArgs,
            func=_add_source,
        ),
    ]
