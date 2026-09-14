---
name: paid-media-design
description: Configure company branding or update report design, tokens, templates, and runtime design guidance. Use during onboarding, when DESIGN.md changes, or when a user requests report styling or layout changes.
---

# Maintain report design

## Read first

- [DESIGN.md](../../../workspace/skills/report-design/DESIGN.md): company design decisions.
- [Theme tokens](../../../src/paid_media_agent/reports/templates/tokens.j2): renderer values.
- [Report template](../../../src/paid_media_agent/reports/templates/report.html.j2): HTML and print layout.
- [Runtime skill](../../../workspace/skills/report-design/SKILL.md) and
  [component recipes](../../../workspace/skills/report-design/COMPONENTS.md): document-authoring guidance.
- [Customization](../../../docs/customization.md#report-design): user setup and deployment paths.

Preserve the accepted appearance unless the user requests a visual change.

## Set the company style

During onboarding, offer to apply the company's palette, fonts, and report name. Use supplied
brand guidance or an approved example; ask only for missing choices. If none is available,
keep the shipped defaults and explain that `DESIGN.md` can be updated later. Do not block setup.

For lasting changes, update `workspace/skills/report-design/DESIGN.md` first, then apply the same
values to `tokens.j2` in the same change. Encourage users asking for recurring report changes to
record them there. A one-off document request does not change the company's defaults.

Company tokens are authoritative. Reuse existing semantic roles for colors, font families,
spacing, and corners. Do not improvise a palette, import another product's styling, or add
literal brand values to templates or component recipes. Preserve the company's requested fonts
with valid local fallbacks. Add a logo only when requested and authorized.

## Edit the owning layer

| Change | Edit |
| --- | --- |
| Palette, fonts, spacing, corners, report name, optional logo | `DESIGN.md` and `tokens.j2` |
| Layout, responsive behavior, print pagination | `report.html.j2`; update design rules if they change |
| Guidance for custom documents | Runtime `SKILL.md` and `COMPONENTS.md` |
| Calculation or data semantics | The analysis/report code and its existing tests |

Keep theme values out of Python. Use tokens for CSS and resolve the same values into SVG and
PDF styles. Do not duplicate logos or palettes across skill folders. Custom document recipes
must read the company tokens from `DESIGN.md`.

Keep figures, date windows, currencies, missing states, and attribution rules intact. Style
changes must not change calculations, tool access, approvals, or delivery. Preserve unrelated
work and keep source references and company data out of public examples.

Local coding-agent skills live in `.agents/skills`; `.claude/skills` links to that directory.
Keep this workflow there. Only `workspace/skills` goes into the runtime skill bundle.

## Verify

1. Run the relevant existing tests, starting with
   `uv run pytest tests/unit/test_reads_and_surfaces.py tests/unit/test_docs_links.py -q`.
2. Render a synthetic report. Inspect desktop, narrow-screen, and every PDF page. Verify that
   the company colors and fonts reach charts and print, signs and units remain visible,
   tables fit or scroll, and the reported values are unchanged.
3. Run the repository checks in `AGENTS.md`. For runtime skill changes, use a clean `mda build`
   and inspect `.mda/__contexthub__/skills`. Confirm `.agents` skills are not in that bundle.
4. Rebuild self-hosted images after renderer changes. Runtime skill mounts update separately;
   a Markdown edit alone does not update the built-in report template or a hosted deployment.

Show the result and state what was verified. Commit or deploy only when requested.
