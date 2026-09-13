"""MDA native Slack channel: mentions, DMs, threads, and approve/reject interrupts."""

from pathlib import Path

from managed_deepagents import channels

from paid_media_agent.deployment import SLACK_ICON_FILENAME, DeploymentSettings

_settings = DeploymentSettings()

channel = channels.slack(
    name=_settings.slack_name,
    description=_settings.slack_description,
    icon=SLACK_ICON_FILENAME if Path(__file__).with_name(SLACK_ICON_FILENAME).is_file() else None,
    background_color=_settings.slack_background_color or None,
    trigger_on_all_messages=_settings.slack_trigger_on_all_messages,
    allow_bot_triggers=_settings.slack_allow_bot_triggers,
)
