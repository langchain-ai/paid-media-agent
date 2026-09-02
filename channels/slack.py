"""MDA native Slack channel: mentions, DMs, threads, and approve/reject interrupts."""

from managed_deepagents import channels

channel = channels.slack(
    name="Paid Media Agent",
    description="Analyzes connected ad accounts and stages changes for human approval.",
)
