"""Direct read adapters for X and OpenAI Ads, plus legacy standalone LinkedIn connections.

Each adapter contributes `RawTool` entries that go through the same deny-by-default catalog as
Pipeboard tools, and a `ReadProvider` that executes them host-side. Mutations are never defined
here; a direct write adapter would need its own reviewed policy rows and canary.
"""

from __future__ import annotations

from paid_media_agent.config import Settings
from paid_media_agent.domain.common import JsonValue, Platform
from paid_media_agent.tools.catalog import CatalogEntry, RawTool
from paid_media_agent.tools.direct.linkedin import LinkedInReadProvider, linkedin_raw_tools
from paid_media_agent.tools.direct.openai_ads import OpenAIAdsReadProvider, openai_ads_raw_tools
from paid_media_agent.tools.direct.x_ads import XAdsReadProvider, x_ads_raw_tools
from paid_media_agent.tools.providers import ProviderError, ProviderResult, ReadProvider


def configured_direct_platforms(settings: Settings) -> tuple[Platform, ...]:
    """Direct platforms with complete credentials; the settings object owns the rule."""
    return settings.direct_platforms()


def direct_raw_tools(settings: Settings) -> list[RawTool]:
    tools: list[RawTool] = []
    for platform in configured_direct_platforms(settings):
        if platform is Platform.LINKEDIN_ADS:
            tools.extend(linkedin_raw_tools())
        elif platform is Platform.X_ADS:
            tools.extend(x_ads_raw_tools())
        elif platform is Platform.OPENAI_ADS:
            tools.extend(openai_ads_raw_tools())
    return tools


def direct_read_providers(settings: Settings) -> dict[Platform, ReadProvider]:
    providers: dict[Platform, ReadProvider] = {}
    for platform in configured_direct_platforms(settings):
        if platform is Platform.LINKEDIN_ADS:
            providers[platform] = LinkedInReadProvider.from_settings(settings)
        elif platform is Platform.X_ADS:
            providers[platform] = XAdsReadProvider.from_settings(settings)
        elif platform is Platform.OPENAI_ADS:
            providers[platform] = OpenAIAdsReadProvider.from_settings(settings)
    return providers


class CompositeReadProvider:
    """Routes each authorized read to the provider that owns its platform."""

    def __init__(
        self, default: ReadProvider | None, by_platform: dict[Platform, ReadProvider]
    ) -> None:
        self._default = default
        self._by_platform = dict(by_platform)

    async def call_read(
        self, entry: CatalogEntry, arguments: dict[str, JsonValue]
    ) -> ProviderResult:
        provider = self._by_platform.get(entry.platform, self._default)
        if provider is None:
            raise ProviderError(f"no read provider is configured for {entry.platform.value}")
        return await provider.call_read(entry, arguments)


__all__ = [
    "CompositeReadProvider",
    "configured_direct_platforms",
    "direct_raw_tools",
    "direct_read_providers",
]
