"""Managed Deep Agents schedule: the monthly cross-platform report (28-day windows)."""

from managed_deepagents import define_schedule

schedule = define_schedule(
    cron="0 13 1 * *",
    timezone="UTC",
    prompt=(
        "Run the monthly paid media report. Read campaign performance for every alias over the last "
        "56 complete days, call compare_periods for the last 28 days versus the 28 days before, then "
        "render_report with a short executive summary. Keep unavailable platforms visible."
    ),
)
