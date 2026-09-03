# Log

Append-only record of material changes to this repository's behavior. Newest first. The build-phase
journal (2026-08-31 to 2026-09-03) is preserved in
[docs/history/build-log-2026-09.md](docs/history/build-log-2026-09.md).

## 2026-09-03 (gap closure and clarity pass)

- Closed the top parity gaps that can be verified without live credentials: ad-group and creative
  grain on the direct adapters and the fixture catalog, five public playbook wiki pages routed from
  the analysis skill, and a repeatable question eval under `tests/eval/`.
- Clarity pass from two read-only reviews: removed dead code and duplicated helpers, wired the
  signed Slack HTTP transport into `serve` and the Edit reply into the Slack service, dropped the
  unused catalog TTL and schedule run mode, made `OPERATIONS.md` the command reference, rewrote
  the README quick start around the credential-free demo, corrected `AGENTS.md`, and moved build
  scaffolding under `docs/history/`.
