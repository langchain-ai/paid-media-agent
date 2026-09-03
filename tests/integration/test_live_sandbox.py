"""Live sandbox probe. Needs a LangSmith key with sandbox permissions and a published snapshot."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from paid_media_agent.config import Settings
from paid_media_agent.runtime.sandbox import open_sandbox, probe_sandbox

pytestmark = pytest.mark.skipif(
    not os.environ.get("PAID_MEDIA_LIVE_TESTS")
    or not os.environ.get("PAID_MEDIA_SANDBOX_SNAPSHOT"),
    reason="set PAID_MEDIA_LIVE_TESTS=1 and PAID_MEDIA_SANDBOX_SNAPSHOT to run",
)


def test_snapshot_can_host_the_agent() -> None:
    root = Path(__file__).resolve().parents[2]
    sandbox = open_sandbox(Settings(), name="paid-media-live-test")
    try:
        checks = probe_sandbox(sandbox, root)
    finally:
        sandbox.close()
    assert [c.name for c in checks if c.status != "ok"] == []
