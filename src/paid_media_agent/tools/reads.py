"""Host-side read dispatch: re-resolve, validate, scope, execute, normalize, offload."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from datetime import date
from typing import Any

import jsonschema
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict

from paid_media_agent.config import AccountRegistry
from paid_media_agent.domain.common import DataQualityFlag, EntityType, JsonValue
from paid_media_agent.middleware.redaction import sanitize_exception
from paid_media_agent.tools.artifacts import ArtifactStore
from paid_media_agent.tools.catalog import (
    AuthorizedToolCatalog,
    CatalogEntry,
    CatalogProvider,
    ToolClass,
)
from paid_media_agent.tools.normalize import (
    ROWS_SCHEMA_VERSION,
    NormalizationError,
    normalize_rows,
    rows_to_payload,
)
from paid_media_agent.tools.providers import (
    ProviderError,
    ProviderResult,
    ProviderTimeout,
    ReadProvider,
)

logger = logging.getLogger(__name__)

ACCOUNT_ALIAS_ARG = "account_alias"
PROVIDER_RESULT_SCHEMA_VERSION = "provider-result/1"
DEFAULT_READ_TIMEOUT_SECONDS = 60.0


class ReadDenied(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason if not detail else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


class ReadResult(BaseModel):
    """Compact typed summary returned to the model. Raw rows stay in the artifact."""

    model_config = ConfigDict(frozen=True)

    kind: str = "read_result"
    tool: str
    platform: str
    account_alias: str
    catalog_revision: str
    artifact_id: str
    artifact_kind: str
    schema_version: str
    row_count: int | None
    requested_window: str | None
    actual_window: str | None
    data_complete_through: str | None
    columns: tuple[str, ...]
    missing_fields: tuple[str, ...]
    quality_flags: tuple[DataQualityFlag, ...]
    preview: dict[str, JsonValue]
    note: str = "Rows are stored in the artifact. Use compare_periods for numbers; do not compute from previews."


def model_facing_schema(entry: CatalogEntry, aliases: Sequence[str]) -> dict[str, JsonValue]:
    """Replace the provider account-id argument with a host-resolved alias argument."""
    schema = json.loads(json.dumps(entry.input_schema))
    properties = dict(schema.get("properties", {}))
    required = [r for r in schema.get("required", []) if r != entry.account_arg]
    if entry.account_arg:
        properties.pop(entry.account_arg, None)
    alias_schema: dict[str, JsonValue] = {
        "type": "string",
        "description": "Configured account alias from list_accounts. Never a raw provider id.",
    }
    if 0 < len(aliases) <= 20:
        alias_schema["enum"] = list(aliases)
    properties = {ACCOUNT_ALIAS_ARG: alias_schema, **properties}
    schema["properties"] = properties
    schema["required"] = [ACCOUNT_ALIAS_ARG, *required]
    schema["additionalProperties"] = False
    return dict(schema)


class ReadDispatcher:
    """The only path from the model to a provider read."""

    def __init__(
        self,
        *,
        catalog_provider: CatalogProvider,
        accounts: AccountRegistry,
        provider: ReadProvider,
        artifacts: ArtifactStore,
        timeout_seconds: float = DEFAULT_READ_TIMEOUT_SECONDS,
    ) -> None:
        self._catalog_provider = catalog_provider
        self._accounts = accounts
        self._provider = provider
        self._artifacts = artifacts
        self._timeout = timeout_seconds
        self.audit: list[dict[str, JsonValue]] = []

    @property
    def accounts(self) -> AccountRegistry:
        return self._accounts

    def resolve(
        self, qualified_name: str, *, selection_schema_hash: str | None = None
    ) -> tuple[AuthorizedToolCatalog, CatalogEntry]:
        catalog = self._catalog_provider.current()
        entry = catalog.get(qualified_name)
        if entry is None:
            raise ReadDenied(
                "unknown_tool", "not in the current authorized catalog; discover again"
            )
        if entry.tool_class is not ToolClass.READ:
            raise ReadDenied("not_a_read_tool", entry.policy.reason)
        if selection_schema_hash is not None and selection_schema_hash != entry.schema_hash:
            raise ReadDenied(
                "stale_selection", "tool schema changed since selection; discover again"
            )
        return catalog, entry

    def scope_arguments(
        self, entry: CatalogEntry, arguments: dict[str, JsonValue]
    ) -> tuple[str, dict[str, JsonValue]]:
        args = dict(arguments)
        alias = args.pop(ACCOUNT_ALIAS_ARG, None)
        if not isinstance(alias, str):
            raise ReadDenied("missing_account_alias", "pass account_alias from list_accounts")
        binding = self._accounts.resolve(alias)
        if binding is None:
            raise ReadDenied("unknown_account_alias", alias)
        if binding.platform is not entry.platform:
            raise ReadDenied(
                "platform_scope", f"alias {alias} is not a {entry.platform.value} account"
            )
        if entry.account_arg is None:
            raise ReadDenied("no_account_scope", "tool has no account argument")
        if entry.account_arg in args:
            raise ReadDenied("raw_account_id_rejected", "the host injects the provider account id")
        for value in args.values():
            if isinstance(value, str) and value in self._accounts.provider_ids():
                raise ReadDenied("raw_account_id_rejected", "provider account ids are host-owned")
        args[entry.account_arg] = binding.provider_account_id
        try:
            jsonschema.validate(instance=args, schema=entry.input_schema)
        except jsonschema.ValidationError as exc:
            raise ReadDenied("schema_validation_failed", sanitize_exception(exc)[:200]) from None
        return alias, args

    async def execute(
        self,
        qualified_name: str,
        arguments: dict[str, JsonValue],
        *,
        selection_schema_hash: str | None = None,
    ) -> ReadResult:
        catalog, entry = self.resolve(qualified_name, selection_schema_hash=selection_schema_hash)
        alias, scoped = self.scope_arguments(entry, arguments)
        try:
            result = await asyncio.wait_for(
                self._provider.call_read(entry, scoped), timeout=self._timeout
            )
        except TimeoutError as exc:
            raise ProviderTimeout("provider read timed out") from exc
        # Normalization plus the artifact write (disk, and the sandbox mirror) stay off the loop.
        summary = await asyncio.to_thread(self._store, entry, catalog, alias, scoped, result)
        self.audit.append(
            {
                "tool": entry.qualified_name,
                "account_alias": alias,
                "catalog_revision": catalog.revision,
                "policy": entry.policy.reason,
                "artifact_id": summary.artifact_id,
            }
        )
        return summary

    def _store(
        self,
        entry: CatalogEntry,
        catalog: AuthorizedToolCatalog,
        alias: str,
        scoped: dict[str, JsonValue],
        result: ProviderResult,
    ) -> ReadResult:
        binding = self._accounts.resolve(alias)
        assert binding is not None  # noqa: S101 - resolved by scope_arguments
        requested_window = None
        if isinstance(scoped.get("start_date"), str) and isinstance(scoped.get("end_date"), str):
            requested_window = f"{scoped['start_date']}..{scoped['end_date']}"
        complete_through = (
            date.fromisoformat(result.data_complete_through)
            if result.data_complete_through
            else None
        )
        rows = result.payload.get("rows")
        if isinstance(rows, list) and rows:
            try:
                normalized, missing = normalize_rows(
                    platform=entry.platform,
                    account_ref=alias,
                    currency=result.currency or binding.currency,
                    timezone=result.timezone or binding.timezone,
                    rows=[r for r in rows if isinstance(r, dict)],
                    entity_type=EntityType.CAMPAIGN,
                    entity_names={
                        str(k): str(v)
                        for k, v in (result.payload.get("entity_names") or {}).items()
                    },
                    data_complete_through=complete_through,
                )
            except NormalizationError as exc:
                raise ReadDenied("normalization_failed", sanitize_exception(exc)) from None
            days = sorted(row.window.start for row in normalized)
            actual_window = f"{days[0].isoformat()}..{days[-1].isoformat()}"
            flags: set[DataQualityFlag] = set()
            for row in normalized:
                flags.update(row.quality_flags)
            if requested_window and requested_window != actual_window:
                flags.add(DataQualityFlag.INCOMPLETE_WINDOW)
            payload = rows_to_payload(normalized)
            payload["provider_totals"] = result.payload.get("totals") or {}
            payload["missing_fields"] = list(missing)
            metadata = self._artifacts.write_json(
                "performance_rows",
                payload,
                schema_version=ROWS_SCHEMA_VERSION,
                row_count=len(normalized),
                platform=entry.platform.value,
                account_ref=alias,
                entity_type=EntityType.CAMPAIGN.value,
                requested_window=requested_window,
                actual_window=actual_window,
                quality_flags=tuple(sorted(flags)),
                tool_name=entry.qualified_name,
                catalog_revision=catalog.revision,
            )
            columns = tuple(sorted({k for r in rows if isinstance(r, dict) for k in r}))
            return ReadResult(
                tool=entry.qualified_name,
                platform=entry.platform.value,
                account_alias=alias,
                catalog_revision=catalog.revision,
                artifact_id=metadata.artifact_id,
                artifact_kind="performance_rows",
                schema_version=ROWS_SCHEMA_VERSION,
                row_count=len(normalized),
                requested_window=requested_window,
                actual_window=actual_window,
                data_complete_through=result.data_complete_through,
                columns=columns,
                missing_fields=missing,
                quality_flags=tuple(sorted(flags)),
                preview={
                    "entities": len({r.entity_ref for r in normalized}),
                    "currency": normalized[0].currency,
                },
            )
        metadata = self._artifacts.write_json(
            "provider_result",
            {"schema_version": PROVIDER_RESULT_SCHEMA_VERSION, "result": result.payload},
            schema_version=PROVIDER_RESULT_SCHEMA_VERSION,
            platform=entry.platform.value,
            account_ref=alias,
            requested_window=requested_window,
            tool_name=entry.qualified_name,
            catalog_revision=catalog.revision,
        )
        preview = _bounded_preview(result.payload)
        return ReadResult(
            tool=entry.qualified_name,
            platform=entry.platform.value,
            account_alias=alias,
            catalog_revision=catalog.revision,
            artifact_id=metadata.artifact_id,
            artifact_kind="provider_result",
            schema_version=PROVIDER_RESULT_SCHEMA_VERSION,
            row_count=_count_rows(result.payload),
            requested_window=requested_window,
            actual_window=None,
            data_complete_through=result.data_complete_through,
            columns=tuple(sorted(result.payload.keys())),
            missing_fields=(),
            quality_flags=(),
            preview=preview,
        )


def _count_rows(payload: dict[str, JsonValue]) -> int | None:
    for value in payload.values():
        if isinstance(value, list):
            return len(value)
    return None


def _bounded_preview(payload: dict[str, JsonValue], limit: int = 1200) -> dict[str, JsonValue]:
    text = json.dumps(payload, default=str)
    if len(text) <= limit:
        return payload
    return {"truncated": True, "head": text[:limit]}


def build_platform_read_tools(
    catalog: AuthorizedToolCatalog, dispatcher: ReadDispatcher
) -> list[BaseTool]:
    """One model-facing tool per authorized read entry. Mutation entries are never bound."""
    aliases_by_platform = {
        platform: dispatcher.accounts.aliases(platform)
        for platform in {e.platform for e in catalog.entries}
    }
    tools: list[BaseTool] = []
    for entry in catalog.read_entries():
        tools.append(
            _make_read_tool(entry, aliases_by_platform.get(entry.platform, ()), dispatcher)
        )
    return tools


def _make_read_tool(
    entry: CatalogEntry, aliases: Sequence[str], dispatcher: ReadDispatcher
) -> BaseTool:
    schema_hash = entry.schema_hash
    name = entry.qualified_name

    async def _run(**kwargs: Any) -> str:
        try:
            result = await dispatcher.execute(name, kwargs, selection_schema_hash=schema_hash)
        except ReadDenied as exc:
            return json.dumps({"denied": True, "reason": exc.reason, "detail": exc.detail})
        except ProviderError as exc:
            return json.dumps({"error": True, "detail": sanitize_exception(exc)})
        return result.model_dump_json()

    description = f"[{entry.platform.value}] {entry.description}".strip()
    return StructuredTool(
        name=name,
        description=description[:1024],
        args_schema=model_facing_schema(entry, aliases),
        coroutine=_run,
        metadata={
            "paid_media": {
                "platform": entry.platform.value,
                "schema_hash": schema_hash,
                "class": "read",
            }
        },
    )
