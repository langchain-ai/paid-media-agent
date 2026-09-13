# Analysis validation checklist

- Correct platform and configured account alias
- Requested and actual date window
- Timezone and period completeness
- Entity grain and parent key
- Currency and units
- Row count, nulls, duplicates, and suppressed rows
- Metric numerator and denominator availability
- Platform attribution window and click/view semantics
- Comparison period parity
- Account aggregate reconciliation
- Business-outcome source and join grain, when present
- Missing or conflicting source state
- Structured artifact path, schema version, and content hash

If a check fails, correct the pull or label the limitation before interpretation.

