# Changelog

## Unreleased

### Added

- Paid-media analysis through a shared Deep Agents assembly, with a credential-free fixture demo.
- A local setup console and CLI for models, account connections, and deployment.
- Pipeboard tool discovery and read-only direct adapters behind a host-controlled account catalog.
- Deterministic period comparisons and HTML/PDF reports with source reconciliation.
- Typed proposals, verified human approvals, one mutation attempt, and bounded readback receipts.
- Managed Deep Agents deployment with Slack and schedule declarations, plus a self-hosted API,
  Slack adapter, and optional Postgres persistence.
- Runtime skills and editable business context shared across both deployment paths.
- Every run's trace names the template it came from: `ls_template: langchain-ai/paid-media-agent`
  and `ls_template_version` metadata on the root run, on MDA and the local and self-hosted paths.
  Nothing about the deployment or its people; `PAID_MEDIA_TEMPLATE_TELEMETRY=false` turns it off.

Live provider writes remain disabled by default and require the documented release gates.

### Changed

- Clarify the README's capabilities, setup, deployment, and company customization guidance.
- Use the LangChain company logo in the README, with light and dark variants.
- Require `managed-deepagents` 0.9.3 or later. Document MDA's agent and personal memory layers
  and the day-to-day `mda` commands.
