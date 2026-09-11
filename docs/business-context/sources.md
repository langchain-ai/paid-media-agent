# Business sources

Use official platform documentation for semantics and the live authenticated Pipeboard catalog for
current connected capability. Refresh fast-moving sources before release claims.

| Source | Owns | Does not prove |
|---|---|---|
| [Pipeboard integrations](https://pipeboard.co/integrations) | publicly listed platform connectors and MCP endpoints | a user's connection, exact current schema, or successful call |
| [Pipeboard MCP product](https://pipeboard.co/products/mcps) | public read/write, OAuth, token scoping, and MCP positioning | this project's authorization or approval safety |
| [Pipeboard for Google](https://pipeboard.co/google-mcp) | public Google permission and paused-creation description | the current authenticated account state |
| [Google Ads API fields](https://developers.google.com/google-ads/api/fields/latest/overview) | current Google resource and metric field reference | business interpretation or cross-channel comparability |
| [Meta Marketing API Insights](https://developers.facebook.com/docs/marketing-api/insights/) | Meta reporting dimensions, metrics, and API behavior | incrementality or another platform's definitions |
| [Reddit Ads API](https://ads-api.reddit.com/docs/v3/) | Reddit resource and reporting API reference | Pipeboard connection health |
| [LinkedIn Marketing APIs](https://learn.microsoft.com/en-us/linkedin/marketing/) | LinkedIn marketing resource contracts | a user's OAuth scope or account role |
| [X Ads API](https://developer.x.com/en/docs/x-ads-api) | X Ads resources and API contracts | current access tier or credentials |

Runtime source order:

1. live authenticated tool catalog and read result;
2. official provider docs;
3. repository fixtures and deterministic tests;
4. this compiled wiki;
5. model memory only as a search lead.

Do not add customer dashboards, private spreadsheets, internal chats, or production account data to
this public wiki.

