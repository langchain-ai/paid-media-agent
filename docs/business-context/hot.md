# Current public context

- The v1 connector target is Pipeboard Streamable HTTP MCP.
- MDA deployment includes a sandbox by default. It bakes the dependency-only `sandbox/setup.sh`
  recipe once and reuses the snapshot; standalone publishing is optional.
- Initial analysis is fixture-first and platform-delivery focused.
- Business goals and targets are user configuration, not repository constants.
- The local coding agent gathers business context using the org-onboarding skill and CLI.
  The console provides a guide, not another required step. Manual setup uses `org interview`;
  both save in Git-ignored `docs/org/`, also mounted by Docker Compose.
- Current provider capability must be discovered at runtime.
- The first write path remains narrow, reversible, paused-first, and globally disabled until a
  separately authorized canary.

- Setup is Welcome → Model → Accounts → Deployment, served directly by Python. MDA is the
  recommended paid option; one Deploy action checks the project and starts MDA. Self-hosting
  remains available. Sample account mode and the CLI demo remain available; the console has no sample dialog or chat client.
- Setup preserves process-control focus during polling and keeps cross-platform account selections
  independent. Connection checks follow the effective runtime credentials.
