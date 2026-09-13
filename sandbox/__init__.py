"""MDA builds setup.sh at deployment and reuses the snapshot for each new thread."""

from managed_deepagents import define_sandbox

sandbox = define_sandbox(docker_image="python:3.13-slim", idle_ttl_seconds=1800)
