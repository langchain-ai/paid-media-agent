"""Managed Deep Agents schedule. It runs the same agent as a conversation would; any change it
proposes still waits for a human approval, and the prompt asks for a report, not a change."""

from managed_deepagents import define_schedule

schedule = define_schedule(
    cron="0 13 * * MON",
    timezone="UTC",
    prompt=(
        "Run the weekly paid media report. Use list_accounts, read campaign performance for every "
        "alias over the last 14 complete days, call compare_periods for the last 7 days versus the "
        "7 days before, then render_report with a short executive summary. Name every unavailable "
        "platform and never invent a cross-platform total."
    ),
)
