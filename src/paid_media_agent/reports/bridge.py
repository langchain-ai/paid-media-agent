"""Host-controlled artifact bridge: validates files before anything leaves the workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

ALLOWED_SUFFIXES: dict[str, str] = {
    ".html": "text/html",
    ".pdf": "application/pdf",
    ".json": "application/json",
}
MAX_ARTIFACT_BYTES = 15 * 1024 * 1024


class ArtifactReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    media_type: str
    byte_size: int
    validated_at: datetime


class BridgeError(Exception):
    pass


class ArtifactBridge:
    def __init__(self, out_root: Path) -> None:
        self._root = out_root.resolve()

    def validate(self, path: Path) -> ArtifactReceipt:
        resolved = path.resolve()
        if self._root not in resolved.parents:
            raise BridgeError("artifact path is outside the output directory")
        if resolved.is_symlink():
            raise BridgeError("symlinked artifacts are not delivered")
        media_type = ALLOWED_SUFFIXES.get(resolved.suffix.lower())
        if media_type is None:
            raise BridgeError("artifact type is not deliverable")
        if not resolved.is_file():
            raise BridgeError("artifact does not exist")
        size = resolved.stat().st_size
        if size == 0 or size > MAX_ARTIFACT_BYTES:
            raise BridgeError("artifact size is outside the deliverable range")
        return ArtifactReceipt(
            path=str(resolved.relative_to(self._root)),
            media_type=media_type,
            byte_size=size,
            validated_at=datetime.now(UTC),
        )

    def open_bytes(self, receipt: ArtifactReceipt) -> bytes:
        path = (self._root / receipt.path).resolve()
        if self._root not in path.parents:
            raise BridgeError("artifact path is outside the output directory")
        return path.read_bytes()
