# Open-source principles for this repository

What the best-run open-source projects do, distilled into rules we hold ourselves to, and the
concrete "gems" borrowed from them. Each rule names the projects it is learned from and how this
repository applies it. Treat gaps as work items, not aspirations.

Sources of the patterns: FastAPI and Pydantic (docs-first, typed, one-command install), uv and Ruff
by Astral (single fast tool, zero-config defaults, pre-commit hook), PostHog and Supabase and Cal.com
(one `docker compose up` self-host, opt-in telemetry with a written policy), Playwright and Vite
(quickstart in under two minutes, examples that run), LangChain and LangGraph (agent-native repo
files, `AGENTS.md`), Excalidraw and tldraw (an architecture page a newcomer can read in ten
minutes), Home Assistant (a security policy people actually use), Keep a Changelog and
Conventional Commits (release notes that write themselves).

## 1. The first five minutes decide adoption

1. **One command to a working result, with nothing to sign up for.** The README's first code block
   must produce something real without credentials. Ours: `uv run paid-media-agent demo --with-proposal`.
2. **Prerequisites on the first screen.** Version, package manager, nothing else.
3. **A second command that shows the product, not the internals.** Ours: `setup`, the local console.
4. **Every command shown the way a fresh checkout runs it.** No implicit virtualenv, no aliases.
   Ours: `uv run ...` everywhere, including inside the console.
5. **The demo never goes stale.** Sample prompts must work on any day the repo is cloned. Ours:
   synthetic data is anchored to today; tests pin the shipped dates.
6. **A visible way to see it work.** A screenshot or a recording of the real thing, not a diagram.

## 2. Documentation is the product surface

7. **One canonical page per question.** Commands live in `OPERATIONS.md`; architecture in
   `docs/architecture/`; the agent's knowledge in `.agents/skills/`. Nothing restates another
   page.
8. **A map for coding agents.** `AGENTS.md` names every directory and the verification commands;
   `CLAUDE.md` only points at it. Frontier repos now ship this alongside the human README.
9. **Write the failure, not only the happy path.** Every error a newcomer will hit has a sentence
   that names the fix (missing Pango, a key without permissions, a stale token).
10. **Examples run.** Anything under `examples/` is executed in CI or deleted.
11. **A changelog humans read.** Keep a Changelog format, an Unreleased section, one line per
    user-visible change; release notes are cut from it.

## 3. Repository hygiene the top projects all share

12. **Community health files exist and are short.** `LICENSE`, `CODE_OF_CONDUCT.md`,
    `CONTRIBUTING.md`, `SECURITY.md` with a private reporting path, issue and pull request
    templates that ask for the reproduction, not an essay.
13. **CI is the definition of done.** Lint, format check, type check, tests, the demo, an import
    smoke, and a secret scan on every pull request; a version matrix for the supported runtimes.
14. **Local hooks mirror CI.** A `.pre-commit-config.yaml` with the same formatter and linter, so
    contributors never discover lint in CI.
15. **Dependencies are locked and updated by a bot.** `uv.lock` committed, Dependabot on.
16. **Releases are automated and reproducible.** Tag `vX.Y.Z`, CI builds the artifacts, publishes
    the GitHub release with the changelog section, and nothing is built on a laptop.
17. **Lint suppressions are real.** Unused `noqa` markers fail (`RUF100`); the rule set in
    `pyproject.toml` is the rule set that runs.

## 4. Run it anywhere, honestly

18. **Self-hosting is one file.** A `Dockerfile` for the service and a `docker-compose.yml` that
    brings up the dependencies with sensible defaults (PostHog, Supabase), next to the managed
    one-command deploy, so nobody is locked into either.
19. **Managed and self-hosted share one code path.** Adapters differ; business logic does not.
20. **Telemetry is off, and the policy is written down.** This repository sends nothing anywhere
    except the providers you configure. Say so where people look. A pre-release plan for opt-out
    adoption tracking is in `docs/plans/adoption-tracking.md`.
21. **Secrets never enter the repository, the image, the prompts, or the logs.** `.env.example`
    documents every key; `.env` is ignored; images copy no env files; the console masks values.

## 5. Agent-native repositories (the newer discipline)

22. **The agent's knowledge is versioned prose**, reviewable in pull requests: `instructions.md`,
    `.agents/skills/`, the business wiki.
23. **Deterministic code owns numbers, permissions, and mutations.** The model chooses and
    explains; code computes and executes.
24. **Evals are in the repo and runnable by anyone.** `tests/eval/` holds the questions, the
    runner, and the grader; the README says how long a run takes and what it costs.
25. **A parity or audit document records what is missing**, ranked, so contributors pick real work.

## Status against this repository

| Rule | Status | Where |
|---|---|---|
| 1-4, 6 | done | `README.md`, console `uv run` prefixes |
| 5 | done | `PAID_MEDIA_FIXTURE_ANCHOR`, anchored fixtures |
| 7-8 | done | `OPERATIONS.md`, `AGENTS.md`, `CLAUDE.md` |
| 9 | done | doctor messages, OPERATIONS notes on Pango and key permissions |
| 10 | partial | `examples/ask.py` is not executed in CI |
| 11 | done | `CHANGELOG.md` |
| 12 | done | `CODE_OF_CONDUCT.md`, issue and PR templates, `SECURITY.md` |
| 13 | done | `.github/workflows/ci.yml`, `compatibility.yml` |
| 14 | done | `.pre-commit-config.yaml` |
| 15 | done | `uv.lock`, `.github/dependabot.yml` |
| 16 | done | `.github/workflows/release.yml` on `v*` tags |
| 17 | done | `RUF100` in `pyproject.toml` |
| 18 | done | `Dockerfile`, `docker-compose.yml`, `docs/self-hosting.md` |
| 19-21 | done | one assembly; no telemetry; `.env` handling |
| 22-25 | done | `instructions.md`, `.agents/skills/`, `tests/eval/`, `docs/audits/` |

Open: rule 10 (run the example in CI) and, beyond hygiene, the ranked functional gaps in
[docs/audits/parity-audit-2026-09-03.md](audits/parity-audit-2026-09-03.md).
