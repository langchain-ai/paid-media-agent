# Browser walkthrough

`console_walkthrough.mjs` drives the setup console with headless Chromium and captures a screenshot
per route. It runs the fixture demo, saves model settings, discovers and maps a fixture account,
validates the write policy, engages and clears the kill switch, runs the MDA preflight, and checks
the process controls in the dark theme. It fails on any browser console error.

Run it against a throwaway copy of the project so form submissions do not touch your real `.env`:

```bash
mkdir -p /tmp/pma-console && cp -R instructions.md .env.example agent.py skills config channels docs /tmp/pma-console/
(cd /tmp/pma-console && uv run --project "$PWD/../paid-media-agent-open-source" paid-media-agent setup --no-open --port 8766)
# in another shell, with Node 22 and `npm i playwright && npx playwright install chromium`
node tests/e2e/console_walkthrough.mjs "http://127.0.0.1:8766/#token=<printed token>" ./shots
```

The Python suite covers the same actions through `tests/contract/test_console_api.py`; this script
adds the rendered page, the forms, and the theme toggle.
