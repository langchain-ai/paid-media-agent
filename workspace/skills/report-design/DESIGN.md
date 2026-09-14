# Report design

This file defines the company's report style. Replace the defaults with your company's approved
palette, fonts, spacing, and logo rules. Reuse those decisions across reports and custom briefs.
Record lasting design changes here rather than styling each output independently.

## Ownership

| File | Purpose |
| --- | --- |
| `DESIGN.md` | Company design rules read by the reporting agent |
| `src/paid_media_agent/reports/templates/tokens.j2` | The built-in renderer's theme values and brand name |
| `src/paid_media_agent/reports/templates/report.html.j2` | The built-in HTML and PDF layout |
| `COMPONENTS.md` | Markup recipes for custom briefs |

The coding agent keeps this specification and the renderer tokens aligned in the same change.
Editing this Markdown alone does not change `render_report`. The local `paid-media-design`
skill covers that workflow. No design service or external account is required.

## Company tokens

These are the shipped defaults. When company tokens are supplied, replace this table and the
matching values in `tokens.j2`. Map company colors to these roles instead of adding a new palette.

| Role | Value |
| --- | --- |
| `canvas` | `#ffffff` |
| `paper` | `#fbfbfc` |
| `ink` / `muted` | `#030710` / `#6c7077` |
| `line` / `card-line` | `#e4e6e9` / `#e4e6e9` |
| `current` | `#006ddd` |
| `previous-fill` / `previous` | `#f3f4f6` / `#737983` |
| `increase` / `decrease` | `#19704c` / `#ad4242` |
| `font-family` | `Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif` |
| `font-mono` | `IBM Plex Mono, ui-monospace, SFMono-Regular, Menlo, monospace` |
| `heading-weight` | `600` |
| `radius-card` / `radius-metric` | `14px` / `14px` |
| `content-width` / `page-gutter` | `1180px` / `32px` |
| `section-gap` / `card-padding` | `40px` / `24px` |

Use `canvas` for the page and metric strip, `paper` for chart and recommendation panels, and
`current` for chart data and section numbers. Use one data accent, neutral surfaces, and dark
current values. Do not assign colors to individual metrics or platforms.

Use `increase` and `decrease` only for signed changes, preserving `+` and `-`. Zero and unavailable
values stay neutral. Colors indicate numeric direction, not whether higher spend or cost is good.
Keep body text at least 4.5:1 contrast and distinguish chart series by labels and outlines too.

Use locally available fonts and system fallbacks. Do not request fonts from a CDN or include
licensed assets without permission. Reports have no logo by default. To add a requested logo,
place an authorized SVG beside the renderer template and set `brand.logo_template` and
`brand.logo_alt` in `tokens.j2`. Set `brand.name` for the report label and PDF footer.

## Layout

- Use one centered document with a short report label, strong title, compact date and scope row,
  and a specific finding. Keep headings outside panels.
- Group key metrics in a connected strip with dividers: four columns on desktop, two on mobile.
  Show combined metrics only when the underlying totals are valid.
- Use numbered section headings with a thin rule. Place related charts in two columns on
  desktop and one on mobile. Keep recommendations visually consistent with chart panels.
- Use the company's spacing tokens. Defaults are 40px between sections, 24px inside panels,
  and 18px page gutters on narrow screens. Avoid decorative icons, shadows, and gradients.
- Keep tables full-width, with no surrounding card or outer padding. Use 7px vertical and
  12px horizontal cell padding, no inset on outer columns, and light row dividers.
  Right-align numeric columns and use tabular numerals. Let long labels wrap.
- Put wide tables in labeled, keyboard-focusable scroll regions. The page itself must not
  overflow. Keep campaign movements and source detail in disclosures, expanded in PDF.
- Show an action and its evidence before measurement and follow-up. Omit empty sections and
  captions that repeat visible labels. Keep material caveats beside the affected figures.

| Type | HTML | PDF |
| --- | --- | --- |
| Title | 34px / 1.12 | 22pt / 1.12 |
| Section heading | 19px / 1.4 | 13pt / 1.4 |
| Key metric | 30px / 1.15, weight 300 | 18pt / 1.15 |
| Body | 14px / 1.5 | 9.5pt / 1.5 |
| Table | 13px / 1.45 | 9pt / 1.45 |
| Caption | 11-12px / 1.5 | 8pt / 1.5 |

Use the heading weight token for titles. Reserve uppercase mono text for short labels.
Format dates as `Aug 22-28, 2026`, including both months or years when the range crosses them.
Use signs on changes, not on ordinary positive rates such as CTR. Keep currency units visible.

## Charts

Use paired bars for spend and attributed conversions, and connected dots for cost per conversion
and return on ad spend. Put account labels left, the graphic in the middle, and exact figures
right. On mobile, put the graphic below its labels. Share one current/previous legend.

Start scales at zero and use the same maximum across both periods and all rows in each chart.
Show zero and maximum labels. Separate currencies and retain platform attribution boundaries.
Missing values have no graphic and say unavailable; a real zero has zero length and a zero label.
Do not interpolate daily trends from period totals or imply that conversions are unique customers.

Use inline SVG or a local image. Resolve colors from company tokens into explicit SVG fills and
strokes for PDF support. Keep exact figures in adjacent text and a table; decorative SVGs can then
be hidden from assistive technology. No chart library or animation is needed for period comparisons.

## Print

Default to A4 portrait with 16mm margins and discreet page numbers; use Letter when requested.
Keep account headings with their metrics and the start of their table. Repeat table headers,
keep rows together, and allow long sections to flow across pages. Expand supporting disclosures.
Inspect every rendered page for clipping, empty pages, detached headings, and unreadable labels.
