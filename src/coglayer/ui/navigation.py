"""Pure navigation decisions for the Streamlit assessment flow."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

TASK_PAGE_MAP: Mapping[str, str] = {
    "go_no_go": "go_no_go",
    "sequence_span": "sequence_span",
    "digit_span": "digit_span",
    "stroop": "stroop",
    "corsi_blocks": "corsi_blocks",
    "n_back": "n_back",
    "letter_number_sequencing": "letter_number_sequencing",
    "perception_lab": "perception_lab",
}


@dataclass(frozen=True)
class NavigationTarget:
    """Describe the next UI page and whether a new session is required."""

    page: str
    reset_session: bool
    message: str | None


def navigate_decision(decision: Mapping[str, object]) -> NavigationTarget:
    """Map an API decision to a safe Streamlit navigation target."""
    status = decision.get("status")
    reason = decision.get("reason")
    message = reason if isinstance(reason, str) and reason else None

    if status == "next_task":
        task_id = decision.get("next_task")
        if isinstance(task_id, str) and task_id in TASK_PAGE_MAP:
            return NavigationTarget(
                page=TASK_PAGE_MAP[task_id],
                reset_session=False,
                message=message,
            )
        return NavigationTarget(
            page="next",
            reset_session=False,
            message="The next assessment task is unavailable.",
        )

    if status == "insufficient_data":
        return NavigationTarget(
            page="next",
            reset_session=True,
            message=message or "The assessment needs a fresh session.",
        )

    if status == "complete":
        return NavigationTarget(page="profile", reset_session=False, message=message)

    return NavigationTarget(
        page="next",
        reset_session=False,
        message="The assessment could not determine the next step.",
    )
