"""Managed Deep Agents schedule. It runs the same agent as a conversation would; any change it
proposes still waits for a human approval, and the prompt asks for a report, not a change.

MDA posts this run's own answer to `deliver_to` (set it with
`paid-media-agent config set PAID_MEDIA_REPORT_SLACK_CHANNEL=C...`), so the report is built in this
run: a background helper's answer would arrive in a later run that nothing posts."""

from managed_deepagents import define_schedule

schedule = define_schedule(
    cron="0 13 * * MON",
    timezone="UTC",
    prompt=(
        "Run the weekly paid media report. Use list_accounts, read campaign performance for every "
        "alias over the last 14 complete days, call compare_periods for the last 7 days versus the "
        "7 days before, then render_report with a short executive summary. Name every unavailable "
        "platform and never invent a cross-platform total. Do the work in this run, without "
        "background helpers: your answer here is what gets posted. Answer with the summary in five "
        "lines or fewer and where the full report is."
    ),
)
