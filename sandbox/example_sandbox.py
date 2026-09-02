"""Opt-in managed sandbox declaration for Managed Deep Agents.

MDA treats `sandbox/__init__.py` as the sandbox declaration and requires it to export a named
`sandbox`. This project leaves the file out by default so a deploy does not provision a sandbox
you did not ask for. To enable one, copy this file to `sandbox/__init__.py` and point it at the
snapshot built from `sandbox/Dockerfile` (see `sandbox/README.md`).
"""

from managed_deepagents import define_sandbox

sandbox = define_sandbox(snapshot_name="paid-media-agent-sandbox")
