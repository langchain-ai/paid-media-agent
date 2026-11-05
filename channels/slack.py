"""MDA native Slack channel: mentions, DMs, threads, Stop, and approve/reject interrupts.

`status` shows the run's steps as Slack's plan above the reply, in paid-media phrasing
(`surfaces/progress.py`). It reads only the agent's state and never slows the run.
"""

from pathlib import Path

from managed_deepagents import channels

from paid_media_agent.deployment import SLACK_ICON_FILENAME, DeploymentSettings
from paid_media_agent.surfaces.progress import plan_from_state

_settings = DeploymentSettings()

channel = channels.slack(
    name=_settings.slack_name,
    description=_settings.slack_description,
    icon=SLACK_ICON_FILENAME if Path(__file__).with_name(SLACK_ICON_FILENAME).is_file() else None,
    background_color=_settings.slack_background_color or None,
    trigger_mode=_settings.slack_trigger_mode,
    allow_bot_triggers=_settings.slack_allow_bot_triggers,
    status=plan_from_state,
)
