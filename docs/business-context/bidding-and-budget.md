# Bidding and budget

## Pacing

Pacing is average daily spend over a window divided by the daily budget. `summarize_window` computes
it per campaign when the `list_campaigns` artifact is supplied.

- Platforms may overspend a daily budget on strong days and underspend on weak ones; most balance
  over a calendar month. Pacing above 1.0 for two days is normal; pacing above 1.0 for a month is
  a budget that is effectively larger than configured.
- Pacing well below 1.0 means the budget is not the constraint. Raising it will not add delivery;
  look at bids, audience size, approval status, or creative fatigue.
- A paused campaign with residual spend on the pause day is not an anomaly.

## Changing budgets

- Prefer steps of roughly 20 to 30 percent. Large jumps reset learning on auction platforms and make
  before-and-after comparison unreadable.
- Give a change a full weekly cycle before judging it, longer when conversions are sparse.
- Increase budget where the marginal result is still efficient, which usually means the campaign is
  pacing at or above budget with stable or improving efficiency. Cut where spend rises and
  efficiency falls across two windows, not one day.
- Every budget change is a proposal with a before value, an after value, a reason, and a reversal.

## Bidding strategies, in general terms

- Automated strategies (target CPA, target ROAS, maximize conversions) need conversion volume and a
  learning period; changing targets often restarts learning.
- Manual or capped bids give control but need attention; they are rarely the first lever.
- Bid changes and budget changes at the same time cannot be attributed. Change one thing at a time.

## What the tools own

Arithmetic, pacing ratios, and window coverage come from `summarize_window` and `compare_periods`.
Quote them. Do not compute a percentage or an average in prose.
