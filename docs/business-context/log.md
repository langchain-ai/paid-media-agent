# Business-context log

## 2026-09-01

- Created a public, company-neutral paid-media doctrine.
- Defined goal hierarchy, metric and attribution boundaries, decision workflow, reporting contract,
  and governed-write safety.
- Established live schemas and official provider docs as higher authority than compiled context.

## 2026-09-01 (implementation)

- Encoded the metric definitions, missing-is-not-zero rule, equal-length comparison windows, and
  cross-platform total suppression in `tools/compute.py`; the fixture demonstrates a platform with
  no conversion value and an incomplete window.
- Reports render from `ReportPayload` with per-platform attribution caveats and visible unavailable sources.

## 2026-09-11

- Sample dates follow the fixture anchor; failed analysis cannot produce a successful demo.
- Simplified setup to the Python console: Welcome → Model → Accounts → Deployment. Retired the
  Next.js/chat port. MDA deploy checks the project automatically, reports errors inline, and
  supports Slack authorization continuation; self-hosting remains optional. Source: `admin/`.

## 2026-09-12

- Removed obsolete setup state and styles. Process polling preserves focus and expanded output;
  account rows stay independent across platforms. Model catalogs and cached connection checks
  now follow the runtime credential resolver, including cleared saved keys. Source: `admin/`.
- Simplified Deployment into one MDA card with editable setup details and one Deploy agent
  action. Other ways to run contains self-hosting and local tools. Removed the sample-analysis
  dialog and its welcome/model shortcuts. Sample account mode and the CLI demo remain.

## 2026-09-12: Full Pipeboard connection coverage

- Added TikTok, Pinterest, Snap, and GA4 to Google, Meta, and Reddit. All seven MCP catalogs load concurrently and use the existing authorized tool discovery and selection paths.
- One connection list groups all seven under Pipeboard, with separate direct-adapter rows. Account discovery includes advertisers and GA4 properties and permits partial connections.
- Native analytics payloads remain separate from verified spend normalization. Synthetic fixtures remain limited to Google, Meta, and Reddit. No live account was connected during verification.

### LinkedIn connector correction

Pipeboard also documents LinkedIn Ads at https://pipeboard.co/guides/linkedin-ads-mcp. The console now groups eight integrations under Pipeboard, with only X and OpenAI Ads separate. Existing direct LinkedIn credentials apply only when no Pipeboard token is configured.
