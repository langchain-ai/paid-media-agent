# Migration notes

## From a direct-integration agent to this package

1. Move provider OAuth to Pipeboard and delete per-platform HTTP clients. The catalog is the only
   entry point for provider capability.
2. Replace prompt-level tool restrictions with the authorized catalog and the invocation guard.
   A prompt that says "do not call X" is not a capability profile.
3. Replace ad-hoc arithmetic with `PerformanceRow` normalization and `compare_periods`. Keep
   provider-native fields under `source_fields` instead of widening the common model.
4. Replace "are you sure?" confirmations with `propose_change` and `execute_change`: persisted
   ChangeSet, signed single-use approval, one attempt, readback, receipt.
5. Encode business judgment in `skills/` and `docs/business-context/`; keep organization-specific
   goals, thresholds, and account ids in host configuration.

## Between runtime profiles

- Local to self-hosted: set `DATABASE_URL` and `PAID_MEDIA_API_TOKENS`; proposals, claims, and
  receipts move from memory to Postgres with the same objects and ids.
- Self-hosted to MDA: keep `agent.py`, `instructions.md`, `skills/`, and `channels/slack.py`;
  MDA supplies the backend, threads, identity, and native Slack. The rich Slack adapter stays an
  external service when Block Kit review or edits are required.

## Version 0.1.0

First implementation. There are no stored-format migrations yet; the Postgres tables are created by
`PostgresRepositories.setup()` and the LangGraph checkpointer's own setup.
