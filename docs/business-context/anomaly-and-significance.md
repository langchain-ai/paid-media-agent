# Anomalies and significance

Day-over-day swings are common in paid media. Most are not anomalies: weekends, month starts,
budget resets, learning phases after a change, delayed conversion attribution, and platform data
still filling in.

## Reading a flagged day

`summarize_window` flags a day when spend or conversions move by at least half versus the prior day.
A flag is a prompt to look, not a finding. Check, in order:

1. Is the window complete? A day near `data_complete_through` is often still filling in, and
   conversions arrive later than spend.
2. Did configuration change? Budget, status, or bid changes on or just before the day explain most
   spend steps. `list_campaigns` shows the current state; change history is not available on
   every platform, so say when it is unknown.
3. Small numbers. A move from 2 conversions to 4 is not a trend. Use spend and clicks, which are
   larger, before conversions.
4. Weekly pattern. Compare the day with the same weekday a week earlier before calling it unusual.

## Significance without a statistics engine

Deterministic tools report exact values; they do not run significance tests. Be explicit:

- Call a change a trend only when it persists across several days or two full windows.
- Say "within normal day-to-day variation" when a swing is inside the range seen across the window.
- Quote the size of the base: "conversions rose from 7.6 to 13.9" is more honest than "+83%".
- Do not extrapolate a partial week to a full week.

## What to recommend

Investigate before acting. A single flagged day rarely justifies a budget or status change. When a
change is warranted, propose it with the reversal plan and a measurement window long enough to see
the effect through a full weekly cycle.
