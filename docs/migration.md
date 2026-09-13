# Migration notes

## From a direct-integration agent to this package

1. Move provider OAuth to Pipeboard where it exists; keep a thin read adapter only for platforms
   Pipeboard does not cover (`tools/direct/`). The catalog is the only entry point for capability.
2. Replace prompt-level tool restrictions with the authorized catalog and the invocation guard.
   A prompt that says "do not call X" is not a capability profile.
3. Replace ad-hoc arithmetic with `PerformanceRow` normalization and `compare_periods`. Keep
   provider-native fields under `source_fields` instead of widening the common model.
4. Replace "are you sure?" confirmations with `propose_change` and `execute_change`: persisted
   ChangeSet, signed single-use approval, one attempt, readback, receipt.
5. Encode business judgment in `.agents/skills/` (the wiki is `.agents/skills/paid-media-wiki/`); keep
   organization-specific goals, thresholds, and account ids in host configuration and `docs/org/`.

## Between the two deployment paths

- Self-hosted to Managed Deep Agents: keep `agent.py`, `identity.py`, `instructions.md`,
  `.agents/skills/` and its root `skills/` link, `schedules/`, `channels/slack.py`, `config/`, and
  `docs/org/`; MDA supplies threads, checkpoints, the sandbox, identity, and Slack. Replace `slack:<team>:<user>` approver refs with
  the identities MDA presents (a refused approval names one).
- Managed Deep Agents to self-hosted: set `DATABASE_URL`, generate `PAID_MEDIA_API_TOKENS` and the
  signing key, create the Slack app from the manifest, and use `slack:<team>:<user>` approver refs.
  Proposals, claims, and receipts keep the same objects and ids across memory and Postgres.
- Wiki links changed on 2026-09-08 from `/docs/business-context/<page>` to
  `/skills/paid-media-wiki/<page>`; the org profile is read through `get_org_context`.

## Version 0.1.0

First implementation. There are no stored-format migrations yet; the Postgres tables are created by
`PostgresRepositories.setup()` and the LangGraph checkpointer's own setup.
