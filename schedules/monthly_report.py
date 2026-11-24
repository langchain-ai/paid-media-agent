"""Managed Deep Agents schedule. It runs the same agent as a conversation would; any change it
proposes still waits for a human approval, and the prompt asks for a report, not a change.

MDA posts this run's own answer to `deliver_to` (set it with
`paid-media-agent config set PAID_MEDIA_REPORT_SLACK_CHANNEL=C...`), so the report is built in this
run: a background helper's answer would arrive in a later run that nothing posts."""

from managed_deepagents import define_schedule

schedule = define_schedule(
    cron="0 13 1 * *",
    timezone="UTC",
    prompt=(
        "Run the monthly paid media report. Read campaign performance for every alias over the last "
        "56 complete days, call compare_periods for the last 28 days versus the 28 days before, then "
        "render_report with a short executive summary. Keep unavailable platforms visible. Do the "
        "work in this run, without background helpers: your answer here is what gets posted. "
        "Answer with the summary in five lines or fewer and where the full report is."
    ),
)
