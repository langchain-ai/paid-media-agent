# Shortcuts for the commands everyone runs. Each line is what CI runs, nothing more.
.PHONY: setup demo check test lint format doctor

setup:        ## install everything
	uv sync --all-extras --dev

demo:         ## fixture data through the real graph, including an approval
	uv run paid-media-agent demo --with-proposal

check:        ## the CI gate: lint, format, types, tests
	uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q

lint:
	uv run ruff check . --fix && uv run ruff format .

test:
	uv run pytest -q

doctor:
	uv run paid-media-agent doctor
