"""Tests for decision-driven Streamlit navigation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from coglayer.ui.api import get_decision
from coglayer.ui.navigation import NavigationTarget, navigate_decision


def test_next_task_maps_to_registered_page() -> None:
    """A known decision task maps to its registered page."""
    decision = {
        "status": "next_task",
        "next_task": "sequence_span",
        "reason": "Sequence memory is next.",
    }

    assert navigate_decision(decision) == NavigationTarget(
        page="sequence_span",
        reset_session=False,
        message="Sequence memory is next.",
    )


def test_insufficient_data_starts_a_new_session() -> None:
    """Insufficient data targets the internal new-session route."""
    decision = {
        "status": "insufficient_data",
        "next_task": None,
        "reason": "Start a new session to retry.",
    }

    assert navigate_decision(decision) == NavigationTarget(
        page="next",
        reset_session=True,
        message="Start a new session to retry.",
    )


def test_complete_maps_to_profile() -> None:
    """A complete decision maps to the profile page."""
    assert navigate_decision({"status": "complete"}) == NavigationTarget(
        page="profile",
        reset_session=False,
        message=None,
    )


def test_unknown_or_malformed_decision_returns_message() -> None:
    """Invalid decisions return a safe target with a short user-facing message."""
    assert navigate_decision({"status": "next_task", "next_task": "unknown"}) == NavigationTarget(
        page="next",
        reset_session=False,
        message="The next assessment task is unavailable.",
    )
    assert navigate_decision({"status": "unexpected"}) == NavigationTarget(
        page="next",
        reset_session=False,
        message="The assessment could not determine the next step.",
    )


@patch("coglayer.ui.api.httpx.get")
def test_get_decision_fetches_session_decision(mock_get: MagicMock) -> None:
    """The UI helper requests the decision endpoint for one session."""
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"status": "complete"},
    )

    assert get_decision("http://testserver", "sess_1") == {"status": "complete"}
    mock_get.assert_called_once_with(
        "http://testserver/v1/assessment/sessions/sess_1/decision",
        timeout=5.0,
    )
