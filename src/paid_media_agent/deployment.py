"""User-facing MDA configuration, read by the console and the deployment declarations."""

from __future__ import annotations

import ast
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SLACK_ICON_FILENAME = "slack-icon.png"


class DeploymentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAID_MEDIA_", env_file=".env", extra="ignore")

    slack_name: str = Field(
        default="Paid Media Agent",
        min_length=1,
        max_length=35,
        pattern=r"^[a-zA-Z0-9_.][a-zA-Z0-9_. -]*[a-zA-Z0-9_.]$|^[a-zA-Z0-9_.]$",
        description="Agent display name in Slack",
    )
    slack_description: str = Field(
        default="Analyzes ad spend, conversions, and campaign performance across your accounts.",
        max_length=139,
        description="Short Slack app description",
    )
    slack_background_color: str = Field(
        default="",
        pattern=r"^$|^#[0-9a-fA-F]{6}$",
        description="Optional Slack icon background, #RRGGBB",
    )
    slack_trigger_on_all_messages: bool = Field(
        default=False, description="Respond to every channel message"
    )
    slack_allow_bot_triggers: bool = Field(
        default=False, description="Allow other Slack bots to start runs"
    )
    report_time: time = Field(default=time(13), description="Weekly and monthly report time, HH:MM")
    report_timezone: str = Field(
        default="UTC", description="IANA report timezone, e.g. America/Los_Angeles"
    )
    weekly_report_day: int = Field(
        default=0, ge=0, le=6, description="Weekly report day: 0 Monday through 6 Sunday"
    )
    monthly_report_day: int = Field(
        default=1, ge=1, le=28, description="Monthly report day: 1 through 28"
    )

    @field_validator("report_time")
    @classmethod
    def minute_precision(cls, value: time) -> time:
        if value.second or value.microsecond or value.tzinfo is not None:
            raise ValueError("use HH:MM; choose the timezone separately")
        return value

    @field_validator("report_timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("use an IANA timezone, such as America/Los_Angeles") from exc
        return value

    @property
    def weekly_cron(self) -> str:
        day = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")[self.weekly_report_day]
        return f"{self.report_time.minute} {self.report_time.hour} * * {day}"

    @property
    def monthly_cron(self) -> str:
        return f"{self.report_time.minute} {self.report_time.hour} {self.monthly_report_day} * *"


def schedule_sources(root: Path, settings: DeploymentSettings) -> dict[Path, str]:
    """Change only cron/timezone literals. MDA statically parses schedules; prompts stay authored."""
    sources: dict[Path, str] = {}
    for cadence, cron in (("weekly", settings.weekly_cron), ("monthly", settings.monthly_cron)):
        path = root / "schedules" / f"{cadence}_report.py"
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError(
                "Report schedules must be files inside the project's schedules directory"
            )
        if not path.exists():
            continue
        source = path.read_bytes()
        module = ast.parse(source)
        definition = next(
            (
                node.value
                for node in module.body
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "schedule"
                    for target in node.targets
                )
            ),
            None,
        )
        if (
            not isinstance(definition, ast.Call)
            or not isinstance(definition.func, ast.Name)
            or definition.func.id != "define_schedule"
        ):
            raise ValueError(f"{path.name}: expected schedule = define_schedule(...)")
        lines = source.splitlines(keepends=True)
        changes: list[tuple[int, int, bytes]] = []
        for key, value in (("cron", cron), ("timezone", settings.report_timezone)):
            node = next((kw.value for kw in definition.keywords if kw.arg == key), None)
            if (
                not isinstance(node, ast.Constant)
                or not isinstance(node.value, str)
                or node.end_lineno is None
                or node.end_col_offset is None
            ):
                raise ValueError(f"{path.name}: {key} must be a string literal to edit it in setup")
            if node.value == value:
                continue
            start = sum(map(len, lines[: node.lineno - 1])) + node.col_offset
            end = sum(map(len, lines[: node.end_lineno - 1])) + node.end_col_offset
            changes.append((start, end, f'"{value}"'.encode()))
        for start, end, value_bytes in sorted(changes, reverse=True):
            source = source[:start] + value_bytes + source[end:]
        sources[path] = source.decode()
    return sources
