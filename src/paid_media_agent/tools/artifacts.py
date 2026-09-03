"""Workspace artifact store. Large results live here; the model sees ids and metadata."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from paid_media_agent.domain.common import DataQualityFlag, JsonValue

ARTIFACT_ID_RE = re.compile(r"^art_[a-f0-9]{16}$")
ArtifactKind = Literal["provider_result", "performance_rows", "analysis", "tool_result", "report"]

_KIND_DIRS: dict[str, str] = {
    "provider_result": "analysis",
    "performance_rows": "analysis",
    "analysis": "analysis",
    "tool_result": "analysis",
    "report": "out",
}


class ArtifactMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_id: str
    kind: ArtifactKind
    path: str
    sha256: str
    byte_size: int
    created_at: datetime
    schema_version: str
    row_count: int | None = None
    platform: str | None = None
    account_ref: str | None = None
    entity_type: str | None = None
    requested_window: str | None = None
    actual_window: str | None = None
    quality_flags: tuple[DataQualityFlag, ...] = ()
    tool_name: str | None = None
    catalog_revision: str | None = None


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    metadata: ArtifactMetadata
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class ArtifactError(Exception):
    pass


class FileSink(Protocol):
    """Receives a copy of every workspace file the host writes (the sandbox mirror)."""

    def put(self, relative_path: str, data: bytes) -> None: ...


class ArtifactStore:
    """Writes JSON artifacts under a workspace root and verifies hashes on read.

    With a `mirror`, every written file is also copied to the model's filesystem so the paths
    the model sees are the paths host tools wrote.
    """

    def __init__(self, root: Path, *, mirror: FileSink | None = None) -> None:
        self.root = root.resolve()
        self._mirror = mirror
        for sub in ("in", "out", "analysis"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def new_id() -> str:
        return f"art_{secrets.token_hex(8)}"

    def _path_for(self, artifact_id: str, kind: str) -> Path:
        if not ARTIFACT_ID_RE.match(artifact_id):
            raise ArtifactError("invalid artifact id")
        path = (self.root / _KIND_DIRS[kind] / f"{artifact_id}.json").resolve()
        if self.root not in path.parents:
            raise ArtifactError("artifact path escapes workspace")
        return path

    def write_json(
        self,
        kind: ArtifactKind,
        payload: dict[str, JsonValue],
        *,
        schema_version: str,
        row_count: int | None = None,
        platform: str | None = None,
        account_ref: str | None = None,
        entity_type: str | None = None,
        requested_window: str | None = None,
        actual_window: str | None = None,
        quality_flags: tuple[DataQualityFlag, ...] = (),
        tool_name: str | None = None,
        catalog_revision: str | None = None,
    ) -> ArtifactMetadata:
        artifact_id = self.new_id()
        path = self._path_for(artifact_id, kind)
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
        digest = hashlib.sha256(body).hexdigest()
        metadata = ArtifactMetadata(
            artifact_id=artifact_id,
            kind=kind,
            path=str(path.relative_to(self.root)),
            sha256=digest,
            byte_size=len(body),
            created_at=datetime.now(UTC),
            schema_version=schema_version,
            row_count=row_count,
            platform=platform,
            account_ref=account_ref,
            entity_type=entity_type,
            requested_window=requested_window,
            actual_window=actual_window,
            quality_flags=quality_flags,
            tool_name=tool_name,
            catalog_revision=catalog_revision,
        )
        envelope = {"metadata": metadata.model_dump(mode="json"), "payload": payload}
        # One row per line so the model can page through an artifact with read_file offsets.
        path.write_text(
            json.dumps(envelope, sort_keys=True, default=str, indent=1), encoding="utf-8"
        )
        self.publish(path)
        return metadata

    def publish(self, path: Path) -> None:
        """Mirror a file under the workspace root to the model's filesystem, if one is attached."""
        if self._mirror is None:
            return
        resolved = path.resolve()
        if self.root not in resolved.parents:
            raise ArtifactError("artifact path escapes workspace")
        self._mirror.put(resolved.relative_to(self.root).as_posix(), resolved.read_bytes())

    def read(self, artifact_id: str) -> ArtifactRecord:
        if not ARTIFACT_ID_RE.match(artifact_id):
            raise ArtifactError("invalid artifact id")
        for kind_dir in ("analysis", "out"):
            candidate = (self.root / kind_dir / f"{artifact_id}.json").resolve()
            if self.root not in candidate.parents:
                raise ArtifactError("artifact path escapes workspace")
            if candidate.exists():
                envelope = json.loads(candidate.read_text(encoding="utf-8"))
                metadata = ArtifactMetadata.model_validate(envelope["metadata"])
                payload = envelope["payload"]
                body = json.dumps(
                    payload, sort_keys=True, separators=(",", ":"), default=str
                ).encode("utf-8")
                if hashlib.sha256(body).hexdigest() != metadata.sha256:
                    raise ArtifactError("artifact content hash mismatch")
                return ArtifactRecord(metadata=metadata, payload=payload)
        raise ArtifactError("artifact not found")

    def absolute_path(self, metadata: ArtifactMetadata) -> Path:
        path = (self.root / metadata.path).resolve()
        if self.root not in path.parents:
            raise ArtifactError("artifact path escapes workspace")
        return path
