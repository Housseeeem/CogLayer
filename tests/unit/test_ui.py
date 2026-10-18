"""Unit tests for CogLayer Streamlit UI components.

Verifies page functions handle mock responses gracefully and satisfy
the non-clinical requirements and import restrictions.

Requirements: R-010.1, R-010.2, R-010.5
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from coglayer.ui.pages.coach import render_coach_page
from coglayer.ui.pages.consent import render_consent_page
from coglayer.ui.pages.go_no_go import render_go_no_go_page
from coglayer.ui.pages.profile import render_profile_page
from coglayer.ui.pages.sequence_span import render_sequence_span_page


@patch("coglayer.ui.pages.consent.httpx.get")
@patch("coglayer.ui.pages.consent.st")
def test_consent_page_renders(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """Consent page renders without exceptions when user has consented."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"has_consented": True})
    mock_st.button.return_value = False
    render_consent_page("http://testserver", "user_1")
    assert mock_st.header.called


@patch("coglayer.ui.pages.go_no_go.httpx.get")
@patch("coglayer.ui.pages.go_no_go.st")
@patch("coglayer.ui.pages.go_no_go.components.html")
def test_go_no_go_page_renders(
    mock_html: MagicMock, mock_st: MagicMock, mock_get: MagicMock
) -> None:
    """Go/No-Go page renders embedded HTML component."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    render_go_no_go_page("http://testserver", "user_1", "sess_1")
    assert mock_html.called


@patch("coglayer.ui.pages.go_no_go.httpx.get")
@patch("coglayer.ui.pages.go_no_go.st")
@patch("coglayer.ui.pages.go_no_go.components.html")
def test_go_no_go_shows_decision_reason(
    mock_html: MagicMock, mock_st: MagicMock, mock_get: MagicMock
) -> None:
    """Go/No-Go displays the stored decision reason before the task."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.session_state = {"decision_reason": "Start with response inhibition."}
    mock_st.columns.return_value = [MagicMock(), MagicMock()]

    render_go_no_go_page("http://testserver", "user_1", "sess_1")

    mock_st.info.assert_any_call("Start with response inhibition.")


@patch("coglayer.ui.pages.sequence_span.httpx.get")
@patch("coglayer.ui.pages.sequence_span.st")
@patch("coglayer.ui.pages.sequence_span.components.html")
def test_sequence_span_page_renders(
    mock_html: MagicMock, mock_st: MagicMock, mock_get: MagicMock
) -> None:
    """Sequence span page renders embedded HTML component."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    render_sequence_span_page("http://testserver", "user_1", "sess_1")
    assert mock_html.called


@patch("coglayer.ui.pages.sequence_span.httpx.get")
@patch("coglayer.ui.pages.sequence_span.st")
@patch("coglayer.ui.pages.sequence_span.components.html")
def test_sequence_span_shows_decision_reason(
    mock_html: MagicMock, mock_st: MagicMock, mock_get: MagicMock
) -> None:
    """Sequence Span displays the stored decision reason before the task."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.session_state = {"decision_reason": "Continue with visual memory."}
    mock_st.columns.return_value = [MagicMock(), MagicMock()]

    render_sequence_span_page("http://testserver", "user_1", "sess_1")

    mock_st.info.assert_any_call("Continue with visual memory.")


@patch("coglayer.ui.pages.profile.httpx.get")
@patch("coglayer.ui.pages.profile.st")
def test_profile_page_renders(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """Profile page renders metrics and displays warning on multiple dimensions."""
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "dimensions": {
                "response_inhibition": {
                    "lower": 0.5,
                    "upper": 0.9,
                    "mean": 0.7,
                    "n_evidence": 2,
                },
                "sequential_visual_memory": {
                    "lower": 0.4,
                    "upper": 0.8,
                    "mean": 0.6,
                    "n_evidence": 1,
                },
            },
            "data_quality": {
                "response_inhibition": {"completeness": 1.0},
                "sequential_visual_memory": {"completeness": 0.8},
            },
        },
    )
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    render_profile_page("http://testserver", "user_1")
    assert mock_st.warning.called


def test_profile_formatting_functions() -> None:
    """Test format_observations and format_uncertainty_interval with hand-derived values.

    Hand-derived:
      - 1 observation -> "1 session"
      - 2 observations -> "2 sessions"
      - lower=0.52, upper=0.88 -> "52% - 88%"
      - lower=0.50, upper=0.90 -> "50% - 90%"
    """
    from coglayer.ui.pages.profile import format_observations, format_uncertainty_interval

    assert format_observations(1) == "1 session"
    assert format_observations(2) == "2 sessions"
    assert format_uncertainty_interval(0.52, 0.88) == "52% - 88%"
    assert format_uncertainty_interval(0.50, 0.90) == "50% - 90%"


@patch("coglayer.ui.pages.coach.httpx.post")
@patch("coglayer.ui.pages.coach.st")
def test_coach_page_renders(mock_st: MagicMock, mock_post: MagicMock) -> None:
    """Coach page displays feedback text when complete."""
    mock_post.return_value = MagicMock(
        status_code=200,
        text="Great progress! Keep practicing.",
    )
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    render_coach_page("http://testserver", "user_1")
    assert mock_st.info.called


@patch("coglayer.ui.pages.coach.httpx.post")
@patch("coglayer.ui.pages.coach.st")
def test_coach_page_403(mock_st: MagicMock, mock_post: MagicMock) -> None:
    """Coach page displays warning if not complete (HTTP 403)."""
    mock_post.return_value = MagicMock(status_code=403, text="Forbidden")
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    render_coach_page("http://testserver", "user_1")
    assert mock_st.warning.called


@patch("coglayer.ui.pages.consent.httpx.post")
@patch("coglayer.ui.pages.consent.httpx.get")
@patch("coglayer.ui.pages.consent.st")
def test_consent_page_gives_consent(
    mock_st: MagicMock, mock_get: MagicMock, mock_post: MagicMock
) -> None:
    """Consent page records consent when button clicked."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"has_consented": False})
    mock_post.return_value = MagicMock(status_code=201)
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    mock_st.button.return_value = True
    mock_st.session_state = {}
    render_consent_page("http://testserver", "user_1")
    assert mock_st.session_state.get("page") == "next"


@patch("coglayer.ui.pages.profile.httpx.get")
@patch("coglayer.ui.pages.profile.st")
def test_profile_page_empty(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """Profile page displays info when no dimensions exist."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"dimensions": {}})
    mock_st.button.return_value = False
    render_profile_page("http://testserver", "user_1")
    assert mock_st.info.called


@patch("coglayer.ui.pages.go_no_go.httpx.get")
@patch("coglayer.ui.pages.go_no_go.st")
def test_go_no_go_already_completed(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """Go/No-Go shows completed banner when task done."""
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"completed_tasks": ["go_no_go"]},
    )
    mock_st.button.return_value = False
    render_go_no_go_page("http://testserver", "user_1", "sess_1")
    assert mock_st.success.called


@patch("coglayer.ui.pages.sequence_span.httpx.get")
@patch("coglayer.ui.pages.sequence_span.st")
def test_sequence_span_already_completed(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """Sequence span shows completed banner when task done."""
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"completed_tasks": ["sequence_span"]},
    )
    mock_st.button.return_value = False
    render_sequence_span_page("http://testserver", "user_1", "sess_1")
    assert mock_st.success.called


@patch("coglayer.ui.app.render_consent_page")
@patch("coglayer.ui.app.st")
def test_app_main(mock_st: MagicMock, mock_render_consent: MagicMock) -> None:
    """Main Streamlit app router initializes session state and dispatches."""
    from coglayer.ui.app import main

    session_store: dict[str, object] = {}
    mock_st.session_state = session_store
    mock_st.text_input.return_value = "user_default"
    mock_st.radio.return_value = "consent"
    mock_st.button.return_value = False

    main()
    assert mock_render_consent.called
    assert "user_id" in session_store
    assert session_store.get("page") == "consent"


@patch("coglayer.ui.app.render_coach_page")
@patch("coglayer.ui.app.st")
def test_app_main_dispatches_coach(mock_st: MagicMock, mock_render_coach: MagicMock) -> None:
    """Main Streamlit app router dispatches to coach page."""
    from coglayer.ui.app import main

    session_store: dict[str, object] = {"user_id": "user_default", "page": "coach"}
    mock_st.session_state = session_store
    mock_st.text_input.return_value = "user_default"
    mock_st.radio.return_value = "coach"
    mock_st.button.return_value = False

    main()
    assert mock_render_coach.called


@patch("coglayer.ui.app.render_dashboard_page")
@patch("coglayer.ui.app.st")
def test_app_main_dispatches_dashboard(
    mock_st: MagicMock, mock_render_dashboard: MagicMock
) -> None:
    """Main Streamlit app router dispatches to dashboard page."""
    from coglayer.ui.app import main

    session_store: dict[str, object] = {"user_id": "user_default", "page": "dashboard"}
    mock_st.session_state = session_store
    mock_st.text_input.return_value = "user_default"
    mock_st.radio.return_value = "dashboard"
    mock_st.button.return_value = False

    main()
    assert mock_render_dashboard.called


@patch("coglayer.ui.pages.consent.httpx.post")
@patch("coglayer.ui.pages.consent.httpx.get")
@patch("coglayer.ui.pages.consent.st")
def test_consent_page_error_handling(
    mock_st: MagicMock, mock_get: MagicMock, mock_post: MagicMock
) -> None:
    """Consent page displays warning when checking consent fails and error when recording fails."""
    mock_get.side_effect = Exception("Connection refused")
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    mock_st.button.return_value = True
    mock_post.side_effect = Exception("API error")
    mock_st.session_state = {}
    render_consent_page("http://testserver", "user_1")
    assert mock_st.warning.called
    assert mock_st.error.called


@patch("coglayer.ui.pages.consent.httpx.post")
@patch("coglayer.ui.pages.consent.httpx.get")
@patch("coglayer.ui.pages.consent.st")
def test_existing_consent_continues_to_next(
    mock_st: MagicMock, mock_get: MagicMock, mock_post: MagicMock
) -> None:
    """Already-consented users enter decision-driven routing."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"has_consented": True})
    mock_st.button.return_value = True
    mock_st.session_state = {}

    render_consent_page("http://testserver", "user_1")

    assert mock_st.session_state["page"] == "next"
    assert not mock_post.called


@patch("coglayer.ui.app.get_decision")
@patch("coglayer.ui.app.httpx.post")
def test_next_creates_session_once_and_routes(
    mock_post: MagicMock, mock_get_decision: MagicMock
) -> None:
    """The next route creates one session, then routes using its decision."""
    from coglayer.ui.app import _handle_next_page

    session_store: dict[str, object] = {}
    mock_post.return_value = MagicMock(status_code=201, json=lambda: {"session_id": "sess_1"})
    mock_get_decision.return_value = {
        "status": "next_task",
        "next_task": "go_no_go",
        "reason": "Start here.",
    }

    with patch("coglayer.ui.app.st.session_state", session_store):
        _handle_next_page("user_1")
        _handle_next_page("user_1")

    assert mock_post.call_count == 1
    assert mock_get_decision.call_count == 2
    assert session_store["session_id"] == "sess_1"
    assert session_store["page"] == "go_no_go"


def test_next_routes_each_decision_status() -> None:
    """The next route maps task, insufficient, and complete decisions."""
    from coglayer.ui.app import _route_decision

    cases = [
        ({"status": "next_task", "next_task": "sequence_span"}, "sequence_span"),
        ({"status": "insufficient_data"}, "next"),
        ({"status": "complete"}, "profile"),
    ]
    for decision, expected_page in cases:
        state: dict[str, object] = {}
        with patch("coglayer.ui.app.st.session_state", state), patch("coglayer.ui.app.st.rerun"):
            _route_decision(decision)
        assert state["page"] == expected_page
