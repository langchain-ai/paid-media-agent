"""Markdown messages with a small, generic approval action row."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

ACTION_APPROVE = "pma_approve"
ACTION_REJECT = "pma_reject"


class SlackMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    blocks: tuple[dict[str, Any], ...] = ()


def render_answer(text: str) -> SlackMessage:
    return SlackMessage(text=text)


def approval_message(text: str, routing_id: str) -> SlackMessage:
    return SlackMessage(
        text=text,
        blocks=(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": label},
                        "action_id": action,
                        "value": routing_id,
                    }
                    for label, action in (
                        ("Approve", ACTION_APPROVE),
                        ("Reject", ACTION_REJECT),
                    )
                ],
            },
        ),
    )
