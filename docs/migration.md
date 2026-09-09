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
5. Encode business judgment in `skills/` (the wiki is `skills/paid-media-wiki/`); keep
   organization-specific goals, thresholds, and account ids in host configuration and `docs/org/`.

## From the self-hosted profile to Managed Deep Agents

The self-hosted profile is on the `self-hosted` branch. Moving a deployment to `main`:

- keep `agent.py`, `identity.py`, `instructions.md`, `skills/`, `schedules/`, `channels/slack.py`,
  `config/`, and `docs/org/`; MDA supplies threads, checkpoints, the sandbox, identity, and Slack;
- drop `DATABASE_URL`, `PAID_MEDIA_API_TOKENS`, `SLACK_*`, `PAID_MEDIA_BACKEND`, and
  `PAID_MEDIA_RUNTIME` from `.env`; `config show` lists what is still read;
- replace `slack:<team>:<user>` approver refs with the identities MDA presents (a refused
  approval names one);
- wiki links change from `/docs/business-context/<page>` to `/skills/paid-media-wiki/<page>`.

## Version 0.1.0

First implementation. There are no stored-format migrations; proposals, approval claims, and
receipts are in-memory objects owned by the running process.
