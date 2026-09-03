"""Write policy data: operations, reviewed mutation rows, and the fixture policy. No execution here."""

from __future__ import annotations

import hashlib
import tomllib
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from paid_media_agent.domain.common import PIPEBOARD_PLATFORMS, RiskLevel
from paid_media_agent.domain.proposals import (
    canonical_json,
)
from paid_media_agent.tools.catalog import (
    AuthorizedToolCatalog,
    ToolClass,
)


class WriteOperation(BaseModel):
    """One admitted mutation: which read proves its state and which fields it may change."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    readback_tool: str
    target_arg: str
    editable_fields: tuple[str, ...]
    readback_fields: dict[str, str]
    """Maps proposal field -> field name in the readback payload."""
    risk: RiskLevel
    units: dict[str, str] = Field(default_factory=dict)
    readback_entity_key: str | None = "campaign"
    """Key holding the entity object inside the readback payload, or None for a flat payload."""
    validate_only_arg: str | None = None
    """Schema argument that turns the call into provider-side validation, when the tool has one."""
    idempotency_arg: str | None = None
    """Schema argument for a provider idempotency key, when the tool has one."""

    def digest(self) -> str:
        return hashlib.sha256(
            canonical_json(self.model_dump(mode="json")).encode("utf-8")
        ).hexdigest()[:16]


class WritePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    operations: tuple[WriteOperation, ...]

    def get(self, tool_name: str) -> WriteOperation | None:
        for op in self.operations:
            if op.tool_name == tool_name:
                return op
        return None

    def admitted_names(self) -> tuple[str, ...]:
        return tuple(op.tool_name for op in self.operations)


class PolicyIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    reason: str


class WritePolicyEntry(BaseModel):
    """One TOML row. `admitted` is the operator's explicit release decision for this operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    admitted: bool = False
    readback_tool: str
    target_arg: str
    editable_fields: tuple[str, ...]
    readback_fields: dict[str, str]
    risk: RiskLevel = RiskLevel.MEDIUM
    units: dict[str, str] = Field(default_factory=dict)
    readback_entity_key: str | None = "campaign"
    validate_only_arg: str | None = None
    idempotency_arg: str | None = None
    notes: str = ""


class WritePolicyFile(BaseModel):
    """Reviewed mutation set. Rows are data: removing a row makes the operation unreachable."""

    model_config = ConfigDict(frozen=True)

    operations: dict[str, WritePolicyEntry] = Field(default_factory=dict)

    @classmethod
    def from_toml(cls, path: Path) -> WritePolicyFile:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        raw = data.get("operations", {})
        if not isinstance(raw, Mapping):
            raise ValueError("write policy must contain an [operations] table")
        return cls(operations={name: WritePolicyEntry.model_validate(v) for name, v in raw.items()})

    def admitted_names(self) -> tuple[str, ...]:
        return tuple(name for name, entry in self.operations.items() if entry.admitted)

    def validate_against(
        self, catalog: AuthorizedToolCatalog
    ) -> tuple[WritePolicy, tuple[PolicyIssue, ...]]:
        """Keep only admitted operations the current catalog can honor. Everything else is an issue."""
        operations: list[WriteOperation] = []
        issues: list[PolicyIssue] = []
        for name, entry in self.operations.items():
            if not entry.admitted:
                issues.append(PolicyIssue(tool_name=name, reason="not_admitted"))
                continue
            catalog_entry = catalog.get(name)
            if catalog_entry is None:
                issues.append(PolicyIssue(tool_name=name, reason="not_in_catalog"))
                continue
            if catalog_entry.tool_class is not ToolClass.MUTATION:
                issues.append(
                    PolicyIssue(
                        tool_name=name,
                        reason=f"catalog_class_{catalog_entry.tool_class.value}:{catalog_entry.policy.reason}",
                    )
                )
                continue
            properties = catalog_entry.input_schema.get("properties", {})
            if not isinstance(properties, Mapping):
                issues.append(PolicyIssue(tool_name=name, reason="malformed_schema"))
                continue
            missing = [f for f in (entry.target_arg, *entry.editable_fields) if f not in properties]
            for optional_arg in (entry.validate_only_arg, entry.idempotency_arg):
                if optional_arg is not None and optional_arg not in properties:
                    missing.append(optional_arg)
            if missing:
                issues.append(
                    PolicyIssue(tool_name=name, reason=f"schema_missing_fields:{','.join(missing)}")
                )
                continue
            readback = catalog.get(entry.readback_tool)
            if readback is None or readback.tool_class is not ToolClass.READ:
                issues.append(PolicyIssue(tool_name=name, reason="readback_tool_unavailable"))
                continue
            if set(entry.readback_fields) != set(entry.editable_fields):
                issues.append(
                    PolicyIssue(tool_name=name, reason="readback_fields_must_cover_editable_fields")
                )
                continue
            operations.append(
                WriteOperation(
                    tool_name=name,
                    readback_tool=entry.readback_tool,
                    target_arg=entry.target_arg,
                    editable_fields=entry.editable_fields,
                    readback_fields=entry.readback_fields,
                    risk=entry.risk,
                    units=entry.units,
                    readback_entity_key=entry.readback_entity_key,
                    validate_only_arg=entry.validate_only_arg,
                    idempotency_arg=entry.idempotency_arg,
                )
            )
        return WritePolicy(operations=tuple(operations)), tuple(issues)


def fixture_write_policy() -> WritePolicy:
    ops: list[WriteOperation] = []
    for platform in PIPEBOARD_PLATFORMS:
        prefix = f"{platform.value}__"
        ops.append(
            WriteOperation(
                tool_name=f"{prefix}update_campaign_budget",
                readback_tool=f"{prefix}get_campaign",
                target_arg="campaign_id",
                editable_fields=("daily_budget",),
                readback_fields={"daily_budget": "daily_budget"},
                risk=RiskLevel.MEDIUM,
                units={"daily_budget": "account currency per day"},
                validate_only_arg="validate_only",
            )
        )
        ops.append(
            WriteOperation(
                tool_name=f"{prefix}update_campaign_status",
                readback_tool=f"{prefix}get_campaign",
                target_arg="campaign_id",
                editable_fields=("status",),
                readback_fields={"status": "status"},
                risk=RiskLevel.HIGH,
            )
        )
    return WritePolicy(operations=tuple(ops))
