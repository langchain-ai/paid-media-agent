# Examples

- [`ask.py`](ask.py): run one question through the shared assembly with your configured model.
  It is the smallest programmatic use of the package and the same thing `paid-media-agent ask`
  does.

```bash
cp .env.example .env            # set PAID_MEDIA_MODEL and the matching provider key
uv run python examples/ask.py "Which campaign moved the most in the last two weeks?"
```

The example compiles the profile the deployment runs: the live catalog when a Pipeboard token or
direct-platform credentials are configured, the fixture accounts otherwise, with an in-memory
checkpointer. Writes stay behind the same gates as everywhere else.
