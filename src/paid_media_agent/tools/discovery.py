"""Model-facing discovery tools: accounts and authorized catalog search."""

from __future__ import annotations

import json

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from paid_media_agent.config import AccountRegistry
from paid_media_agent.domain.common import Platform
from paid_media_agent.tools.catalog import CatalogProvider

LIST_ACCOUNTS_TOOL = "list_accounts"
DISCOVER_TOOLS_TOOL = "discover_tools"


class _DiscoverArgs(BaseModel):
    query: str = Field(description="Keywords describing the data or capability you need.")
    platform: Platform | None = Field(default=None, description="Optional platform filter.")


class _NoArgs(BaseModel):
    pass


def build_list_accounts_tool(accounts: AccountRegistry) -> BaseTool:
    def _list() -> str:
        return json.dumps(
            {
                "accounts": [
                    {
                        "alias": b.alias,
                        "platform": b.platform.value,
                        "currency": b.currency,
                        "timezone": b.timezone,
                    }
                    for b in accounts.bindings
                ]
            }
        )

    return StructuredTool.from_function(
        func=_list,
        name=LIST_ACCOUNTS_TOOL,
        description="List configured account aliases with platform, currency, and timezone. Use aliases in every read.",
        args_schema=_NoArgs,
    )


def build_discover_tools_tool(catalog_provider: CatalogProvider) -> BaseTool:
    def _discover(query: str, platform: Platform | None = None) -> str:
        catalog = catalog_provider.current()
        entries = catalog.search(query, platform=platform)
        return json.dumps(
            {
                "catalog_revision": catalog.revision,
                "tools": [
                    {
                        "name": e.qualified_name,
                        "platform": e.platform.value,
                        "description": e.description[:240],
                        "arguments": sorted(
                            k for k in e.input_schema.get("properties", {}) if k != e.account_arg
                        ),
                    }
                    for e in entries
                ],
                "note": "Only authorized read tools are listed. Changes go through propose_change.",
            }
        )

    return StructuredTool.from_function(
        func=_discover,
        name=DISCOVER_TOOLS_TOOL,
        description="Search the current authorized read-tool catalog by keywords. Call this before assuming a tool exists.",
        args_schema=_DiscoverArgs,
    )
