# Claude entry point

Read [AGENTS.md](AGENTS.md) first and follow it as the binding repository contract. Then read the
files it routes to for the change at hand. Do not duplicate their content here.

Desktop app only: when a user asks to set up or onboard, start the `setup` configuration from
`.claude/launch.json` so the console opens in the Browser pane (`preview_start` with name
`setup`). The terminal CLI has no pane; there, plain `uv run paid-media-agent setup` opens the
system browser.
