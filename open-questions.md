# Open questions

These decisions must be explicit before the public release. None blocks the local fixture-first build.

| Decision | Default for local work | Release gate |
|---|---|---|
| Open-source license | Keep the repository private/local and recommend Apache-2.0 for review | Maintainer approves the exact license text |
| Project and product name | `Paid Media Agent` | Trademark check and final naming approval |
| Supported Pipeboard platforms at v1 | Google Ads, Meta Ads, Reddit Ads | Verify public availability and read/write schema at release time |
| Default runtime model | No product default beyond an example in `.env.example` | Publish a tested model matrix, not a single-provider claim |
| Rich Slack distribution | User-created Slack app with manifest | Confirm scopes, installation guide, and Marketplace intent |
| Self-hosted UI | Agent Chat UI when an Agent Server-compatible endpoint is available | Define support level and auth contract |
| Persistence | Postgres for production; in-memory only in tests | Migration, backup, and retention policy documented |
| Telemetry | Off by default | Document exactly what can be enabled and what never leaves the host |
| Contribution governance | Maintainer review | Add maintainer contacts, security address, and release policy |
| `connectors/mcp.py` in the MDA layout | Omitted; tools enter only through the authorized catalog in the shared assembly | Confirm with maintainers that the SPEC layout entry should be removed or documented as intentionally absent |
| Live Pipeboard schema shape | Normalizer maps common field names and leaves unknown metrics missing | Verify against the authenticated catalog and adjust `tools/normalize.py` field maps before release |
| Native PDF dependencies | HTML fallback when WeasyPrint's Pango/Cairo libraries are missing | Decide whether the snapshot is the only supported PDF path |
