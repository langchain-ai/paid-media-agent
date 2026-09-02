"""Authorized tool catalog: deny-by-default classification of provider tools."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from paid_media_agent.domain.common import JsonValue, Platform
from paid_media_agent.domain.proposals import canonical_json

QUALIFIED_NAME_SEPARATOR = "__"
MAX_TOOL_NAME_LENGTH = 64
_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class ToolClass(StrEnum):
    READ = "read"
    MUTATION = "mutation"
    DENIED = "denied"


class PolicyDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_class: ToolClass
    reason: str


class RawTool(BaseModel):
    """Provider tool as loaded from an MCP catalog, before any policy decision."""

    model_config = ConfigDict(frozen=True)

    platform: str
    name: str
    description: str = ""
    input_schema: dict[str, JsonValue] = Field(default_factory=dict)
    annotations: dict[str, JsonValue] | None = None
    source_endpoint: str = ""


class CatalogEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    platform: Platform
    name: str
    qualified_name: str
    description: str
    input_schema: dict[str, JsonValue]
    read_only_hint: bool | None
    destructive_hint: bool | None
    idempotent_hint: bool | None
    source_endpoint: str
    policy: PolicyDecision
    schema_hash: str
    account_arg: str | None
    """Name of the provider account-id argument that the host injects from the alias."""

    @property
    def tool_class(self) -> ToolClass:
        return self.policy.tool_class


class PlatformPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    platform: Platform
    account_arg_names: tuple[str, ...]


class LocalPolicy(BaseModel):
    """Repository-owned deny policy. Editing a skill cannot change it."""

    model_config = ConfigDict(frozen=True)

    platforms: tuple[PlatformPolicy, ...]
    denied_name_patterns: tuple[str, ...] = (
        r"(^|_)mutate($|_)",
        r"(^|_)raw($|_)",
        r"(^|_)delete($|_)",
        r"(^|_)remove($|_)",
        r"(^|_)purge($|_)",
    )
    admitted_mutations: tuple[str, ...] = ()
    """Qualified mutation names admitted to the governed write path. Empty by default."""

    def platform_policy(self, platform: Platform) -> PlatformPolicy | None:
        for policy in self.platforms:
            if policy.platform == platform:
                return policy
        return None


DEFAULT_LOCAL_POLICY = LocalPolicy(
    platforms=(
        PlatformPolicy(platform=Platform.GOOGLE_ADS, account_arg_names=("customer_id",)),
        PlatformPolicy(
            platform=Platform.META_ADS, account_arg_names=("account_id", "ad_account_id")
        ),
        PlatformPolicy(platform=Platform.REDDIT_ADS, account_arg_names=("account_id",)),
        PlatformPolicy(platform=Platform.LINKEDIN_ADS, account_arg_names=("account_id",)),
        PlatformPolicy(platform=Platform.X_ADS, account_arg_names=("account_id",)),
        PlatformPolicy(platform=Platform.OPENAI_ADS, account_arg_names=("account_id",)),
    ),
)


def schema_hash(input_schema: Mapping[str, JsonValue]) -> str:
    return hashlib.sha256(canonical_json(dict(input_schema)).encode("utf-8")).hexdigest()[:16]


def _as_bool(value: JsonValue) -> bool | None:
    return value if isinstance(value, bool) else None


def classify(
    raw: RawTool, policy: LocalPolicy
) -> tuple[PolicyDecision, Platform | None, str | None]:
    """Return the policy decision, the recognized platform, and the account argument name."""
    try:
        platform = Platform(raw.platform)
    except ValueError:
        return PolicyDecision(tool_class=ToolClass.DENIED, reason="unknown_platform"), None, None
    platform_policy = policy.platform_policy(platform)
    if platform_policy is None:
        return (
            PolicyDecision(tool_class=ToolClass.DENIED, reason="platform_not_enabled"),
            platform,
            None,
        )
    if not _TOOL_NAME_RE.match(raw.name):
        return (
            PolicyDecision(tool_class=ToolClass.DENIED, reason="malformed_tool_name"),
            platform,
            None,
        )
    schema = raw.input_schema
    if not isinstance(schema, Mapping) or schema.get("type", "object") != "object":
        return (
            PolicyDecision(tool_class=ToolClass.DENIED, reason="malformed_schema"),
            platform,
            None,
        )
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        return (
            PolicyDecision(tool_class=ToolClass.DENIED, reason="malformed_schema"),
            platform,
            None,
        )
    account_arg = next((n for n in platform_policy.account_arg_names if n in properties), None)
    lowered = raw.name.lower()
    for pattern in policy.denied_name_patterns:
        if re.search(pattern, lowered):
            return (
                PolicyDecision(tool_class=ToolClass.DENIED, reason="denied_name_policy"),
                platform,
                account_arg,
            )
    annotations = raw.annotations or {}
    read_only = _as_bool(annotations.get("readOnlyHint"))
    if read_only is None:
        return (
            PolicyDecision(tool_class=ToolClass.DENIED, reason="missing_mutation_metadata"),
            platform,
            account_arg,
        )
    if read_only:
        if account_arg is None:
            return (
                PolicyDecision(tool_class=ToolClass.DENIED, reason="no_account_scope"),
                platform,
                None,
            )
        return (
            PolicyDecision(tool_class=ToolClass.READ, reason="read_only_hint"),
            platform,
            account_arg,
        )
    if _as_bool(annotations.get("destructiveHint")) is True:
        return (
            PolicyDecision(tool_class=ToolClass.DENIED, reason="destructive_hint"),
            platform,
            account_arg,
        )
    if account_arg is None:
        return (
            PolicyDecision(tool_class=ToolClass.DENIED, reason="no_account_scope"),
            platform,
            None,
        )
    qualified = qualified_name(platform, raw.name)
    if qualified in policy.admitted_mutations:
        return (
            PolicyDecision(tool_class=ToolClass.MUTATION, reason="admitted_mutation"),
            platform,
            account_arg,
        )
    return (
        PolicyDecision(tool_class=ToolClass.DENIED, reason="mutation_not_admitted"),
        platform,
        account_arg,
    )


def qualified_name(platform: Platform, name: str) -> str:
    return f"{platform.value}{QUALIFIED_NAME_SEPARATOR}{name}"[:MAX_TOOL_NAME_LENGTH]


class AuthorizedToolCatalog(BaseModel):
    """Immutable, revision-hashed catalog. Only READ entries are ever bound to the model."""

    model_config = ConfigDict(frozen=True)

    entries: tuple[CatalogEntry, ...]
    revision: str
    source: str

    def get(self, qualified: str) -> CatalogEntry | None:
        for entry in self.entries:
            if entry.qualified_name == qualified:
                return entry
        return None

    def read_entries(self) -> tuple[CatalogEntry, ...]:
        return tuple(e for e in self.entries if e.tool_class is ToolClass.READ)

    def mutation_entries(self) -> tuple[CatalogEntry, ...]:
        return tuple(e for e in self.entries if e.tool_class is ToolClass.MUTATION)

    def denied_entries(self) -> tuple[CatalogEntry, ...]:
        return tuple(e for e in self.entries if e.tool_class is ToolClass.DENIED)

    def search(
        self, query: str, platform: Platform | None = None, limit: int = 8
    ) -> tuple[CatalogEntry, ...]:
        """Keyword search over read entries only. Denied and mutation tools are never listed."""
        terms = [t for t in re.split(r"[^a-z0-9]+", query.lower()) if t]
        scored: list[tuple[int, CatalogEntry]] = []
        for entry in self.read_entries():
            if platform is not None and entry.platform != platform:
                continue
            haystack = f"{entry.qualified_name} {entry.description}".lower()
            score = sum(haystack.count(term) for term in terms)
            if score or not terms:
                scored.append((score, entry))
        scored.sort(key=lambda pair: (-pair[0], pair[1].qualified_name))
        return tuple(entry for _, entry in scored[:limit])


def build_authorized_catalog(
    raw_tools: Iterable[RawTool], *, policy: LocalPolicy = DEFAULT_LOCAL_POLICY, source: str
) -> AuthorizedToolCatalog:
    entries: list[CatalogEntry] = []
    seen: set[str] = set()
    for raw in raw_tools:
        decision, platform, account_arg = classify(raw, policy)
        if platform is None:
            continue
        qualified = qualified_name(platform, raw.name)
        if qualified in seen:
            decision = PolicyDecision(tool_class=ToolClass.DENIED, reason="duplicate_tool_name")
        seen.add(qualified)
        annotations = raw.annotations or {}
        entries.append(
            CatalogEntry(
                platform=platform,
                name=raw.name,
                qualified_name=qualified,
                description=raw.description[:1000],
                input_schema=dict(raw.input_schema),
                read_only_hint=_as_bool(annotations.get("readOnlyHint")),
                destructive_hint=_as_bool(annotations.get("destructiveHint")),
                idempotent_hint=_as_bool(annotations.get("idempotentHint")),
                source_endpoint=raw.source_endpoint,
                policy=decision,
                schema_hash=schema_hash(raw.input_schema),
                account_arg=account_arg,
            )
        )
    entries.sort(key=lambda e: e.qualified_name)
    material = [
        {
            "name": e.qualified_name,
            "schema_hash": e.schema_hash,
            "class": e.tool_class.value,
            "reason": e.policy.reason,
            "description": e.description,
        }
        for e in entries
    ]
    revision = hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    return AuthorizedToolCatalog(entries=tuple(entries), revision=revision, source=source)


class CatalogProvider(Protocol):
    """Returns the current authorized catalog. Selection-time snapshots are never authority."""

    def current(self) -> AuthorizedToolCatalog: ...


class StaticCatalogProvider:
    def __init__(self, catalog: AuthorizedToolCatalog) -> None:
        self._catalog = catalog

    def current(self) -> AuthorizedToolCatalog:
        return self._catalog

    def replace(self, catalog: AuthorizedToolCatalog) -> None:
        """Swap the catalog. Used by tests to simulate a provider schema change."""
        self._catalog = catalog
