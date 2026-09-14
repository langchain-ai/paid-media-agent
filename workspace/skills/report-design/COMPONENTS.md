# Report components

Use `render_report` for reconciled performance reports. These recipes are for custom briefs
that need a different structure. Read `DESIGN.md` first and use its current company tokens.

## Document shell

Embed CSS in the document and declare its custom properties from `DESIGN.md`. The property
names below match the renderer's tokens. Do not copy a separate palette into this guide.
Use escaped text for placeholders and keep the document readable without JavaScript.

```html
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--canvas); color: var(--ink);
    font: 14px/1.5 var(--font-family); }
  main { max-width: var(--content-width); margin: auto; padding: 34px var(--page-gutter) 40px; }
  h1, h2, h3, p, figure { margin: 0; }
  h1, h2 { font-weight: var(--heading-weight); }
  h1 { margin: 14px 0 10px; font-size: 34px; line-height: 1.12; letter-spacing: -.03em; }
  h2 { font-size: 19px; }
  section { margin-top: var(--section-gap); }
  .section-heading { padding-bottom: 10px; margin-bottom: 22px; border-bottom: 1.5px solid var(--ink); }
  .caption, dt { color: var(--muted); font-size: 12px; }
  .summary { max-width: 80ch; margin-top: 18px; line-height: 1.6; }
  .metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
    margin: 20px 0 24px; border: 1px solid var(--card-line); border-radius: var(--radius-metric); overflow: hidden; }
  .metrics > div { min-width: 0; padding: 22px var(--card-padding); border-right: 1px solid var(--line); }
  .metrics > div:last-child { border-right: 0; }
  .metrics dt { font: 400 10px/1.5 var(--font-mono); letter-spacing: .12em; text-transform: uppercase; }
  .card { padding: var(--card-padding); background: var(--paper);
    border: 1px solid var(--card-line); border-radius: var(--radius-card); }
  dd { margin: 4px 0 0; overflow-wrap: anywhere; }
  .value { margin: 8px 0; font-size: 30px; font-weight: 300; line-height: 1.15; font-variant-numeric: tabular-nums; }
  .change-increase { color: var(--increase); }
  .change-decrease { color: var(--decrease); }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 7px 12px; border-bottom: 1px solid var(--line); text-align: left; }
  th { color: var(--muted); background: var(--paper); font: 400 10px/1.5 var(--font-mono); }
  th:first-child, td:first-child { padding-left: 0; }
  th:last-child, td:last-child { padding-right: 0; }
  .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  @media screen and (max-width: 680px) {
    main { padding: 28px 18px; } h1 { font-size: 26px; }
    .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .metrics > div { padding: 18px; }
    .metrics > div:nth-child(2) { border-right: 0; }
    .metrics > div:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
    .value { font-size: 24px; } table { min-width: 450px; }
  }
  @page { size: A4; margin: 16mm; }
  @media print {
    body { font-size: 9.5pt; } main { padding: 0; max-width: none; }
    h1 { font-size: 22pt; } h2 { font-size: 13pt; } .value { font-size: 18pt; }
    h1, h2, h3 { break-after: avoid; } .metrics, tr { break-inside: avoid; }
    .table-wrap { overflow: visible; } thead { display: table-header-group; }
    table { font-size: 9pt; } .caption, dt { font-size: 8pt; }
  }
</style>
<main>
  <header>
    <p class="caption">{{ reporting_window }} · Compared with {{ previous_window }}</p>
    <h1>{{ specific_title }}</h1>
    <p class="summary">{{ finding_and_material_caveat }}</p>
  </header>
  <section aria-label="Key metrics">
    <div class="section-heading"><h2>{{ section_title }}</h2></div>
    <dl class="metrics">
      <div><dt>{{ metric_with_unit }}</dt><dd class="value">{{ verified_value }}</dd>
        <dd class="caption">{{ signed_change }} vs previous</dd></div>
    </dl>
  </section>
</main>
```

Repeat only the metric cells needed. Apply `change-increase` or `change-decrease` to signed
changes, preserving the sign. Use normal body size for unavailable values and omit their change.
Give tables `scope="col"` headers and a `role="region"` wrapper with a label and `tabindex="0"`.

## Comparison charts

Use the layout and scale rules in `DESIGN.md`. Compute positions in code:
`100 * value / maximum`, using all current and previous values in the chart. Zero stays zero;
omit missing values. Separate currencies. Keep exact values in text beside the graphic.

For paired bars, use an SVG with `viewBox="0 0 100 14"` and `preserveAspectRatio="none"`.
Place the current bar at y=0 and previous at y=9, each 5 units tall. Set widths from the
computed percentages. Resolve `current`, `previous-fill`, and `previous` into literal SVG
fill and stroke values from the company tokens.

For connected dots, use percentage x-coordinates without a viewBox so circles stay round.
Use a filled current point, outlined previous point, and a line between them. Omit the line
unless both values exist. Use `line` for the zero-to-maximum baseline.

SVGs may use `aria-hidden="true"` only when adjacent text supplies the same information.
Keep the full values in a table and use one shared current/previous legend.

## Recommendations and sources

Show the action and its evidence first. Put expected effect, measurement, and reversal in a
native `details` disclosure; expand it for print. Keep short recommendations together in PDF.
Use company panel tokens without status badges or extra accent stripes.

End with source references and data notes. Preserve identifiers as text, not invented links.
Include incomplete coverage, missing sources, currency, and attribution limits where relevant.
