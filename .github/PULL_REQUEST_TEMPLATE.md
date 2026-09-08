## What and why

One paragraph. Link the issue if there is one.

## How it was verified

- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`
- [ ] The fixture demo still runs: `uv run paid-media-agent demo --with-proposal`
- [ ] If behavior, tools, reports, or approvals changed: the owning wiki page and skill were updated
- [ ] If a command or setting changed: `OPERATIONS.md` and `.env.example` were updated
- [ ] No secrets, account ids, or private data in the diff

## Notes for the reviewer

Anything you want looked at closely, or a decision you made that could go another way.
