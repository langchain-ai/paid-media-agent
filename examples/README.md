# Examples

- [`ask.py`](ask.py): run one question through the shared assembly with your configured model,
  fixture catalog, and fake writes. It is the smallest programmatic use of the package.

```bash
cp .env.example .env            # set PAID_MEDIA_MODEL and the matching provider key
uv run python examples/ask.py "Which fixture campaign moved the most in the last two weeks?"
```

The example uses the local runtime profile: in-memory checkpointer, fixture accounts, and the
fake write provider. Replace `build_local_runtime` with `build_self_hosted_runtime` to use a live
Pipeboard catalog and durable persistence.
