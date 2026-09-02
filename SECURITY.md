# Security policy

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on this repository ("Report a vulnerability" under
the Security tab). Do not open a public issue for a security problem and do not include account
identifiers, tokens, or provider payloads in a report. The maintainer contact for out-of-band
reports is recorded in [open-questions.md](open-questions.md) until the public release names one.

## What counts

- Any path that lets model output, Slack input, MCP metadata, or a file reach a provider mutation
  without a host-created, signed, single-use approval.
- Any way to reach a mutation tool, a raw mutate endpoint, or a delete from the model's tool
  surface.
- Approval replay, edit-without-reapproval, digest bypass, expired or foreign approvals, or a
  proposal executing on a thread other than its own.
- Credential exposure in prompts, tool results, artifacts, logs, Slack blocks, or receipts.
- Path traversal out of the workspace, artifact delivery of unexpected files, or Slack signature
  verification bypass.

## What we commit to

- Acknowledge reports within five business days.
- Keep the fixture-only default: no live provider mutation is reachable without the operator gates
  in [docs/operations/live-write-runbook.md](docs/operations/live-write-runbook.md).
- Publish fixes with a changelog entry and, where relevant, a regression test in `tests/`.

## Supported versions

Only the `main` branch is supported before the first tagged release.
