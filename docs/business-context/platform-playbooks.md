# Platform playbooks

Generic operating notes per platform. Live tool schemas decide what is actually available; discover
before assuming. Company-specific strategy belongs in host configuration or user input.

## Google Ads

- Search campaigns follow intent; brand and non-brand behave differently and should not be judged
  on one blended CPA. Performance Max blends channels and hides placement detail.
- Keyword and search-term grain exists when the connected catalog exposes it. Those reads are
  large; summarize them with tools rather than reading rows.
- Cost arrives in micros; the normalizer converts it. Conversions can be fractional.

## Meta Ads

- Campaign, ad set, and ad grains. Ad sets own audience and budget; ads own creative.
- Attribution windows (click and view) are settings, not facts; the same conversion count moves
  when the window changes. State the window the read used when it is reported.
- Learning phase resets after material edits to an ad set; expect noisy efficiency for days.

## LinkedIn Ads

- Campaign groups, campaigns, and creatives. Costs are high; judge on lead quality and pipeline
  when a downstream source exists, not on CPL alone.
- Analytics are daily with a row cap; narrow the window when a read is capped.
- Lead-gen forms and website conversions are different events; name which one a figure is.

## X Ads

- Campaigns, line items (ad groups), and promoted posts. Stats are fetched in 7-day slices.
- Spend is billed charge in micros; conversion metrics depend on the conversion tracking set up.

## Reddit Ads

- Campaigns and ad groups. Conversion value is often not reported, so ROAS is unavailable and
  cross-platform totals that include Reddit are suppressed.
- Community and interest targeting behave differently; compare within the same type.

## OpenAI Ads

- Campaigns, ad groups, and ads through a bearer key. Insights are daily; history is short.
- Treat it as a new channel: small numbers, wide variance, no benchmarks worth citing.

## Across platforms

Conversions are platform-attributed and not deduplicated. Compare efficiency within a platform,
compare spend across platforms, and let the deterministic tools suppress totals they cannot defend.
