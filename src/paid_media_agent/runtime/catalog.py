"""Which tool catalog a process runs: live Pipeboard and direct adapters, or the fixture set."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from paid_media_agent.config import Settings
from paid_media_agent.runtime.profiles import load_write_policy_file
from paid_media_agent.tools.catalog import (
    DEFAULT_LOCAL_POLICY,
    AuthorizedToolCatalog,
    CatalogProvider,
    StaticCatalogProvider,
    build_authorized_catalog,
)
from paid_media_agent.tools.fixtures import (
    FIXTURE_LOCAL_POLICY,
    FixtureReadProvider,
    build_fixture_catalog,
    fixture_raw_tools,
)
from paid_media_agent.tools.providers import ReadProvider, WriteProvider


@dataclass(frozen=True)
class LoadedCatalog:
    catalog: AuthorizedToolCatalog
    provider: CatalogProvider
    read_provider: ReadProvider | None
    write_provider: WriteProvider | None
    """Live write adapter when the catalog is live. It stays behind `WriteGate`."""

    @property
    def live(self) -> bool:
        return self.read_provider is not None and self.write_provider is not None


async def load_catalog(settings: Settings, *, project_root: Path | None = None) -> LoadedCatalog:
    """Live Pipeboard catalog when a token is configured, otherwise the fixture catalog.

    X and OpenAI Ads join the same catalog when configured. Legacy direct LinkedIn works only
    without Pipeboard, so the two providers never compete for the same platform.
    The reviewed write-policy file decides which live mutations are admitted.
    """
    from paid_media_agent.tools.direct import (
        CompositeReadProvider,
        direct_raw_tools,
        direct_read_providers,
    )

    if settings.paid_media_data_mode == "sample":
        catalog = build_fixture_catalog()
        return LoadedCatalog(
            catalog=catalog,
            provider=StaticCatalogProvider(catalog),
            read_provider=None,
            write_provider=None,
        )
    direct_tools = direct_raw_tools(settings)
    direct_providers = direct_read_providers(settings)
    if settings.pipeboard_api_token is None:
        if not direct_tools:
            if settings.paid_media_data_mode == "live":
                raise ValueError("Connect an ad platform before opening a live session.")
            catalog = build_fixture_catalog()
            return LoadedCatalog(
                catalog=catalog,
                provider=StaticCatalogProvider(catalog),
                read_provider=None,
                write_provider=None,
            )
        # Explicit live sessions never mix synthetic platforms into the results.
        catalog = build_authorized_catalog(
            [
                *(fixture_raw_tools() if settings.paid_media_data_mode == "auto" else []),
                *direct_tools,
            ],
            policy=FIXTURE_LOCAL_POLICY,
            source="fixture+direct" if settings.paid_media_data_mode == "auto" else "direct",
        )
        return LoadedCatalog(
            catalog=catalog,
            provider=StaticCatalogProvider(catalog),
            read_provider=CompositeReadProvider(FixtureReadProvider(), direct_providers),
            write_provider=None,
        )
    from paid_media_agent.tools.pipeboard import (
        PipeboardCatalogLoader,
        PipeboardReadProvider,
        PipeboardWriteProvider,
    )

    admitted: tuple[str, ...] = ()
    if project_root is not None:
        policy_file = load_write_policy_file(settings, project_root)
        if policy_file is not None:
            admitted = policy_file.admitted_names()
    local_policy = DEFAULT_LOCAL_POLICY.model_copy(update={"admitted_mutations": admitted})
    loader = PipeboardCatalogLoader(
        settings=settings, policy=local_policy, extra_raw_tools=direct_tools
    )
    catalog = await loader.refresh()
    return LoadedCatalog(
        catalog=catalog,
        provider=loader,
        read_provider=CompositeReadProvider(PipeboardReadProvider(loader), direct_providers),
        write_provider=PipeboardWriteProvider(loader),
    )
