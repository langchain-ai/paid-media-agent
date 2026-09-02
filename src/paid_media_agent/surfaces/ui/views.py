"""UI JSON views. Every field maps to a shared presentation object; no UI-only behavior."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from paid_media_agent.domain.presentation import PRESENTATION_VERSION, ProposalView, ReceiptView
from paid_media_agent.surfaces.runner import RunOutcome


class OutcomeView(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str = PRESENTATION_VERSION
    thread_id: str
    text: str
    interrupted: bool
    proposal: ProposalView | None
    receipt: ReceiptView | None
    available_actions: tuple[str, ...]


def outcome_view(outcome: RunOutcome) -> OutcomeView:
    actions: tuple[str, ...] = ()
    if (
        outcome.interrupted
        and outcome.proposal is not None
        and outcome.proposal.state.value == "awaiting_approval"
    ):
        actions = ("approve", "edit", "reject")
    return OutcomeView(
        thread_id=outcome.thread_id,
        text=outcome.text,
        interrupted=outcome.interrupted,
        proposal=outcome.proposal,
        receipt=outcome.receipt,
        available_actions=actions,
    )
