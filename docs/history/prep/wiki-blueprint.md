# Wiki blueprint

## Audience

- paid-media operators who need the reasoning behind an answer;
- developers adding sources, analysis, reports, or writes;
- coding agents that need fast source and ownership routing.

## Layers

| Layer | Purpose | Location | Mutation policy |
|---|---|---|---|
| External sources | current public contracts | linked from `docs/sources/` and business `sources.md` | read-only links; refresh summaries |
| Source briefs | bounded research notes | `prep/research-briefs/` | replace when refreshed with date/source note |
| Compiled architecture | component ownership and invariants | `docs/architecture/` | edit with behavior changes |
| Compiled business wiki | stable paid-media doctrine | `docs/business-context/` | edit with source-backed doctrine changes |
| Runtime skills | task workflow and references | `skills/` | edit with tested behavior changes |
| Hot/open/log | volatile state, decisions, history | root and wiki-local files | hot/open editable; log append-only |

## Navigation contract

Root `AGENTS.md` stays under a few screens and routes to the owning page. Every maintained wiki has an
index, sources, hot context, open questions, and append-only log. Added or renamed pages update their
index in the same change.

## Source boundary

The public repository paraphrases general lessons from private implementations. It never imports
private records, ids, credentials, screenshots, fixtures, or company-specific strategy.

