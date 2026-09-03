# Skills plan

| Skill | Trigger | Owns | References/scripts | Must not own |
|---|---|---|---|---|
| `paid-media-analysis` | analysis, diagnosis, comparison, recommendation | question framing, evidence workflow, interpretation | business wiki, validation checklist, deterministic compute entry | tool permissions or arithmetic implementation |
| `paid-media-report` | report, summary artifact, PDF | report workflow and narrative constraints | `ReportPayload`, renderer, templates, reconciliation check | layout decisions in model prose |
| `paid-media-writes` | pause, budget, bid, target, create, update | proposal and reviewer workflow | write-safety wiki, proposal checklist | approval creation or provider execution authority |
| `paid-media-onboarding` | install, demo, Pipeboard, account connection, doctor | setup and safe diagnostic workflow | `.env.example`, config example, doctor command | secrets or live mutation tests |

Each `SKILL.md` has valid YAML frontmatter with only `name` and `description`. Descriptions state when
to use the skill. Keep frequently changed provider schemas in runtime discovery, not skill prose.

Add a skill only for a reusable capability that needs its own workflow and references. Put project
facts in the wiki and code constraints in code.

