# Browser walkthrough

`console_walkthrough.mjs` drives the setup wizard with headless Chromium and captures a screenshot
per screen: welcome (capabilities and example prompts), model presets and a custom key name, ad
accounts, try-it (an in-page question and LangGraph Studio start and stop), the managed vs
self-hosted choice, MDA preflight, and the done screen in the dark theme. It fails on any browser
console error.

Run it against a throwaway copy of the project so form submissions do not touch your real `.env`.
The copy needs `pyproject.toml` and `langgraph.json` so Studio can load the graph:

```bash
mkdir -p /tmp/pma-console/workspace
cp -R instructions.md .env.example agent.py pyproject.toml uv.lock langgraph.json skills config channels docs /tmp/pma-console/
(cd /tmp/pma-console && "$PWD/../paid-media-agent-open-source/.venv/bin/paid-media-agent" setup --no-open --port 8766)
# in another shell, with Node 22 and `npm i playwright && npx playwright install chromium`
node tests/e2e/console_walkthrough.mjs "http://127.0.0.1:8766/#token=<printed token>" ./shots
```

The Python suite covers the same actions through `tests/contract/test_console_api.py`; this script
adds the rendered page, the forms, the process controls, and the theme toggle.
