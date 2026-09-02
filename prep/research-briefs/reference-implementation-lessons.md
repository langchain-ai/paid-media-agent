# Reference implementation lessons

Source boundary: a private paid-media agent repository was inspected as implementation evidence. No
private data, internal links, company strategy, account ids, production history, secrets, or fixtures
may be copied into this repository.

## Reusable lessons

- One agent with progressive tools and skills is easier to reason about than separate conversational
  and reporting agents.
- Model judgment and deterministic arithmetic need a hard boundary.
- Large tool catalogs require progressive disclosure plus a final trusted invocation guard.
- Direct read tools and approval-gated write dispatch should be structurally separate.
- The review surface must render from the exact object that executes.
- Account identity belongs in host configuration and dispatch, never prompt prose.
- One mutation plus bounded readback produces more honest outcomes than blind retries.
- Reports should render from typed data with templates and code-owned formatting.
- A business wiki should separate stable doctrine, volatile state, source access, open questions, and
  append-only history.

## Deliberately not carried over

- company-specific goals, campaign decisions, thresholds, or attribution tables;
- direct platform integrations that Pipeboard can replace in the public product;
- LangSmith Gateway configuration;
- legacy graphs, experiments, deployment names, cron ids, or internal workflow tools;
- provider-specific Slack branches.

