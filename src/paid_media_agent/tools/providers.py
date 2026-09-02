"""Provider execution protocols. Network and fixture implementations sit behind these."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from paid_media_agent.domain.common import JsonValue
from paid_media_agent.tools.catalog import CatalogEntry


class ProviderResult(BaseModel):
    """Raw provider payload plus provider-reported completeness metadata."""

    model_config = ConfigDict(frozen=True)

    payload: dict[str, JsonValue] = Field(default_factory=dict)
    data_complete_through: str | None = None
    currency: str | None = None
    timezone: str | None = None


class ProviderError(Exception):
    """Sanitized provider failure. The message must be safe to show the model."""


class ProviderTimeout(ProviderError):
    """The provider did not answer in time. The outcome is unknown, not failed."""


class ReadProvider(Protocol):
    async def call_read(
        self, entry: CatalogEntry, arguments: dict[str, JsonValue]
    ) -> ProviderResult: ...


class WriteProvider(Protocol):
    """Executes exactly the mutation the host hands it. Never bound to the model.

    Readback is not part of this protocol: state is proven through the authorized read path.
    """

    async def call_mutation(
        self, entry: CatalogEntry, arguments: dict[str, JsonValue]
    ) -> dict[str, JsonValue]: ...
