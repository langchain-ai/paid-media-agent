#!/usr/bin/env bash
# Install Paid Media Agent: uv if it is missing, a clone of the repository, and its dependencies.
#
#   curl -fsSL https://raw.githubusercontent.com/langchain-ai/paid-media-agent/main/install.sh | bash
#
# It never asks for or writes a key. PAID_MEDIA_AGENT_DIR picks the folder (default
# ./paid-media-agent); PAID_MEDIA_AGENT_REPO picks what to clone (a fork, say).
set -euo pipefail

REPO="${PAID_MEDIA_AGENT_REPO:-https://github.com/langchain-ai/paid-media-agent.git}"
DIR="${PAID_MEDIA_AGENT_DIR:-paid-media-agent}"

say() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || fail "git is required: install it, then run this again."

if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (https://docs.astral.sh/uv/)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  command -v uv >/dev/null 2>&1 || fail "uv installed, but it is not on PATH: open a new terminal and run this again."
fi

if [ -e "$DIR" ]; then
  [ -f "$DIR/agent.py" ] && [ -d "$DIR/.git" ] || fail "$DIR already exists and is not a Paid Media Agent checkout."
  say "Updating $DIR"
  git -C "$DIR" pull --ff-only
else
  say "Cloning $REPO into $DIR"
  git clone --depth 1 "$REPO" "$DIR"
fi

say "Installing dependencies (Python 3.12+; uv fetches it if needed)"
(cd "$DIR" && uv sync)

cat <<EOF

Installed in $DIR. To put it in your team's Slack with Managed Deep Agents:

  cd $DIR
  uv run paid-media-agent config set LANGSMITH_API_KEY ANTHROPIC_API_KEY PIPEBOARD_API_TOKEN
  uv run paid-media-agent accounts discover --add
  uv run paid-media-agent mda deploy --yes

config set asks for each key without showing it. Run these in your own terminal.
Or open $DIR in Claude Code, Codex or Cursor and say "Deploy it to our Slack."
To try it first, with no keys: uv run paid-media-agent demo --with-proposal
EOF
