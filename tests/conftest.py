"""Shared fixtures: settings, fixture catalog, scripted models, and a local graph builder."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from paid_media_agent.config import Settings
from paid_media_agent.tools.catalog import AuthorizedToolCatalog, StaticCatalogProvider
from paid_media_agent.tools.fixtures import FixtureState, build_fixture_catalog

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolated_environment() -> Iterator[None]:
    """Console actions export .env values into the process; never let that leak across tests."""
    snapshot = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(snapshot)


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        paid_media_model="scripted:demo",
        paid_media_workspace_root=tmp_path / "workspace",
        paid_media_allow_self_approval=True,
        paid_media_approver_ids="local-user,reviewer-1",
        paid_media_approval_signing_key="test-signing-key-with-enough-bytes",
    )


@pytest.fixture
def catalog() -> AuthorizedToolCatalog:
    return build_fixture_catalog()


@pytest.fixture
def catalog_provider(catalog: AuthorizedToolCatalog) -> StaticCatalogProvider:
    return StaticCatalogProvider(catalog)


@pytest.fixture
def fixture_state() -> FixtureState:
    return FixtureState()
