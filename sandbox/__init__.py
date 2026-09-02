"""MDA sandbox declaration. Enabled only when a compatible snapshot is named explicitly."""

import os

from managed_deepagents import define_sandbox

_snapshot = os.environ.get("PAID_MEDIA_SANDBOX_SNAPSHOT")
if _snapshot:
    sandbox = define_sandbox(snapshot_name=_snapshot, idle_ttl_seconds=900)
