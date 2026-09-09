# Architecture index

The project has one agent core and several delivery adapters. Capability and safety stay in shared
code; surfaces only translate inputs and presentation.

## Read order

1. [Runtime profiles](runtime-profiles.md)
2. [Tools and context](tools-and-context.md)
3. [Writes and approvals](writes-and-approvals.md)
4. [Surfaces and presentation](surfaces-and-presentation.md)
5. [Sandbox and snapshots](sandbox-and-snapshots.md)
6. [Capability map](capability-map.md)

## Binding invariants

1. One shared agent assembly.
2. Direct model providers, no required model gateway.
3. Deny-by-default host-side tool authorization.
4. Provider-native deferred search only for verified OpenAI and Anthropic support.
5. Portable LLM tool selection for other models.
6. Model judgment, deterministic computation.
7. Read-only tools direct; mutations behind exact approval.
8. Account identity and credentials remain host-owned.
9. One mutation attempt and bounded readback.
10. Same domain and presentation objects across Slack, the CLI, and schedules.
11. Public context only. Private company evidence never enters the repository.
12. Add complexity only after a measured failure in the simpler design.

## Ownership test

Ask what must remain true if the model, provider, Slack transport, or deployment profile changes. If it
must remain true, it belongs in domain or policy code. If it changes only how a result is delivered,
it belongs in a surface adapter. If it is reusable judgment, it belongs in a skill. If it is stable
business context, it belongs in the wiki.
