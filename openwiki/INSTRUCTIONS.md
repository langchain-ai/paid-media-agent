---
type: Repository guide
title: Repository Wiki Instructions
description: Scope and conventions for the OpenWiki code wiki of the Paid Media Agent repository.
tags: [documentation, repository, code-wiki]
---

A code wiki for coding agents working on this repository. AGENTS.md and docs/architecture/ are
the human-reviewed contract; this wiki is just-in-time evidence beneath them. Prioritize: how
`agent.py`, `runtime/`, `assembly.py`, and the tools compose; the governed write path and its
gates; the catalog and adapters; the console and CLI actions; how tests are organized; what the
hosted Managed Deep Agents deployment can and cannot read. Cite exact files and lines. Skip
`docs/history/`, `workspace/`, and `docs/org/`. Do not restate the business wiki under
`skills/paid-media-wiki/`; link to it.

Claim submissions: a new Claim must not carry an `id` field. Only Claims that already exist for
the page (listed by `inspect_claims`) may be referenced by id, and only to confirm, revise, or
retract them. If `submit_page` rejects a Claim as "not owned", remove the `id` and resubmit.
