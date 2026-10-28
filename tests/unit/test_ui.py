"""Unit tests for CogLayer Streamlit UI components.

Verifies page functions handle mock responses gracefully and satisfy
the non-clinical requirements and import restrictions.

Requirements: R-010.1, R-010.2, R-010.5
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from coglayer.ui.page_views.coach import render_coach_page
from coglayer.ui.page_views.consent import render_consent_page
from coglayer.ui.page_views.go_no_go import render_go_no_go_page
from coglayer.ui.page_views.ioi import _render_opportunity, render_ioi_page
from coglayer.ui.page_views.profile import render_profile_page
from coglayer.ui.page_views.sequence_span import render_sequence_span_page


@patch("coglayer.ui.page_views.consent.httpx.get")
@patch("coglayer.ui.page_views.consent.st")
def test_consent_page_renders(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """Consent page renders without exceptions when user has consented."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"has_consented": True})
    mock_st.button.return_value = False
    render_consent_page("http://testserver", "user_1")
    assert mock_st.header.called


@patch("coglayer.ui.page_views.ioi.get_ioi_score")
@patch("coglayer.ui.page_views.ioi.record_ioi_event")
@patch("coglayer.ui.page_views.ioi.st")
def test_ioi_page_renders_all_explicit_opportunities(
    mock_st: MagicMock,
    mock_record: MagicMock,
    mock_score: MagicMock,
) -> None:
    """The IOI page presents all components without recording on page view."""
    mock_score.return_value = {
        "status": "INSUFFICIENT_EVIDENCE",
        "aggregate_score": None,
        "components": {
            component: {
                "score": 0.0,
                "evidence_count": 0,
                "weight": 0.2,
                "sufficient": False,
            }
            for component in (
                "critical_verification",
                "clarification",
                "iteration",
                "autonomy",
                "responsible_usage",
            )
        },
    }
    mock_st.session_state = {}
    mock_st.button.return_value = False
    mock_st.container.return_value.__enter__.return_value = MagicMock()

    render_ioi_page("http://testserver", "user_1", "session_1")

    assert mock_st.subheader.call_count >= 6
    mock_record.assert_not_called()
    mock_score.assert_called_once_with("http://testserver", "user_1", "session_1")


def _prepare_ioi_mock(mock_st: MagicMock, *, button_clicked: bool = True) -> None:
    """Configure the minimal Streamlit surface used by one IOI opportunity."""
    mock_st.session_state = {}
    mock_st.container.return_value.__enter__.return_value = MagicMock()
    mock_st.radio.return_value = "Yes, I did this"
    mock_st.button.return_value = button_clicked


@patch("coglayer.ui.page_views.ioi.record_ioi_event")
@patch("coglayer.ui.page_views.ioi.st")
def test_ioi_opportunity_success_201_resets_submission_state(
    mock_st: MagicMock, mock_record: MagicMock
) -> None:
    """A recorded opportunity reports success and clears its submitting flag."""
    _prepare_ioi_mock(mock_st)
    mock_record.return_value = {"status": "recorded", "event_id": "event-1"}

    _render_opportunity(
        "http://testserver",
        "user_1",
        "session_1",
        "clarification",
        "clarification_opportunity",
        "Clarification",
        "Prompt",
    )

    assert mock_st.session_state["ioi_opportunity_session_1_clarification"]
    assert mock_st.session_state["ioi_submitting_session_1_clarification"] is False
    mock_st.success.assert_called_once_with("Observation recorded.")
    mock_st.button.assert_called_once_with(
        "Record this opportunity",
        key="ioi_record_session_1_clarification",
        disabled=False,
    )


@patch("coglayer.ui.page_views.ioi.record_ioi_event")
@patch("coglayer.ui.page_views.ioi.st")
def test_ioi_opportunity_idempotent_200_is_informational(
    mock_st: MagicMock, mock_record: MagicMock
) -> None:
    """An idempotent duplicate response is not presented as a new write."""
    _prepare_ioi_mock(mock_st)
    mock_record.return_value = {"status": "duplicate", "event_id": "event-1"}

    _render_opportunity(
        "http://testserver",
        "user_1",
        "session_1",
        "clarification",
        "clarification_opportunity",
        "Clarification",
        "Prompt",
    )

    mock_st.info.assert_called_once_with("This opportunity was already recorded.")
    mock_st.success.assert_not_called()
    assert mock_st.session_state["ioi_submitting_session_1_clarification"] is False


@patch("coglayer.ui.page_views.ioi.record_ioi_event")
@patch("coglayer.ui.page_views.ioi.st")
def test_ioi_opportunity_409_is_informational_and_resets_state(
    mock_st: MagicMock, mock_record: MagicMock
) -> None:
    """A conflict reports the existing opportunity and clears the flag."""
    _prepare_ioi_mock(mock_st)
    request = httpx.Request("POST", "http://testserver/v1/assessment/ioi/events")
    response = httpx.Response(409, request=request)
    mock_record.side_effect = httpx.HTTPStatusError(
        "conflict",
        request=request,
        response=response,
    )

    _render_opportunity(
        "http://testserver",
        "user_1",
        "session_1",
        "clarification",
        "clarification_opportunity",
        "Clarification",
        "Prompt",
    )

    mock_st.info.assert_called_once_with("This opportunity was already recorded.")
    mock_st.error.assert_not_called()
    assert mock_st.session_state["ioi_submitting_session_1_clarification"] is False


@patch("coglayer.ui.page_views.ioi.record_ioi_event")
@patch("coglayer.ui.page_views.ioi.st")
def test_ioi_opportunity_other_http_error_is_reported_and_resets_state(
    mock_st: MagicMock, mock_record: MagicMock
) -> None:
    """Non-conflict HTTP errors remain visible and clear the submission flag."""
    _prepare_ioi_mock(mock_st)
    request = httpx.Request("POST", "http://testserver/v1/assessment/ioi/events")
    response = httpx.Response(500, request=request)
    mock_record.side_effect = httpx.HTTPStatusError(
        "server error",
        request=request,
        response=response,
    )

    _render_opportunity(
        "http://testserver",
        "user_1",
        "session_1",
        "clarification",
        "clarification_opportunity",
        "Clarification",
        "Prompt",
    )

    mock_st.error.assert_called_once()
    assert mock_st.session_state["ioi_submitting_session_1_clarification"] is False


@patch("coglayer.ui.page_views.ioi.st")
def test_ioi_opportunity_keys_are_isolated_by_session(
    mock_st: MagicMock,
) -> None:
    """Two sessions use independent opportunity, outcome, and button keys."""
    _prepare_ioi_mock(mock_st, button_clicked=False)

    _render_opportunity(
        "http://testserver",
        "user_1",
        "session_1",
        "clarification",
        "clarification_opportunity",
        "Clarification",
        "Prompt",
    )
    _render_opportunity(
        "http://testserver",
        "user_1",
        "session_2",
        "clarification",
        "clarification_opportunity",
        "Clarification",
        "Prompt",
    )

    assert "ioi_opportunity_session_1_clarification" in mock_st.session_state
    assert "ioi_opportunity_session_2_clarification" in mock_st.session_state
    assert mock_st.radio.call_args_list[0].kwargs["key"] == "ioi_outcome_session_1_clarification"
    assert mock_st.radio.call_args_list[1].kwargs["key"] == "ioi_outcome_session_2_clarification"
    assert mock_st.button.call_args_list[0].kwargs["key"] == "ioi_record_session_1_clarification"
    assert mock_st.button.call_args_list[1].kwargs["key"] == "ioi_record_session_2_clarification"


@patch("coglayer.ui.page_views.go_no_go.httpx.get")
@patch("coglayer.ui.page_views.go_no_go.st")
@patch("coglayer.ui.page_views.go_no_go.components.html")
def test_go_no_go_page_renders(
    mock_html: MagicMock, mock_st: MagicMock, mock_get: MagicMock
) -> None:
    """Go/No-Go page renders embedded HTML component."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    render_go_no_go_page("http://testserver", "user_1", "sess_1")
    assert mock_html.called


@patch("coglayer.ui.page_views.go_no_go.httpx.get")
@patch("coglayer.ui.page_views.go_no_go.st")
@patch("coglayer.ui.page_views.go_no_go.components.html")
def test_go_no_go_shows_decision_reason(
    mock_html: MagicMock, mock_st: MagicMock, mock_get: MagicMock
) -> None:
    """Go/No-Go displays the stored decision reason before the task."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.session_state = {"decision_reason": "Start with response inhibition."}
    mock_st.columns.return_value = [MagicMock(), MagicMock()]

    render_go_no_go_page("http://testserver", "user_1", "sess_1")

    mock_st.info.assert_any_call("Start with response inhibition.")


@patch("coglayer.ui.page_views.sequence_span.httpx.get")
@patch("coglayer.ui.page_views.sequence_span.st")
@patch("coglayer.ui.page_views.sequence_span.components.html")
def test_sequence_span_page_renders(
    mock_html: MagicMock, mock_st: MagicMock, mock_get: MagicMock
) -> None:
    """Sequence span page renders embedded HTML component."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    render_sequence_span_page("http://testserver", "user_1", "sess_1")
    assert mock_html.called


@patch("coglayer.ui.page_views.sequence_span.httpx.get")
@patch("coglayer.ui.page_views.sequence_span.st")
@patch("coglayer.ui.page_views.sequence_span.components.html")
def test_sequence_span_shows_decision_reason(
    mock_html: MagicMock, mock_st: MagicMock, mock_get: MagicMock
) -> None:
    """Sequence Span displays the stored decision reason before the task."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.session_state = {"decision_reason": "Continue with visual memory."}
    mock_st.columns.return_value = [MagicMock(), MagicMock()]

    render_sequence_span_page("http://testserver", "user_1", "sess_1")

    mock_st.info.assert_any_call("Continue with visual memory.")


@patch("coglayer.ui.page_views.profile.httpx.get")
@patch("coglayer.ui.page_views.profile.st")
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
    from coglayer.ui.page_views.profile import format_observations, format_uncertainty_interval

    assert format_observations(1) == "1 session"
    assert format_observations(2) == "2 sessions"
    assert format_uncertainty_interval(0.52, 0.88) == "52% - 88%"
    assert format_uncertainty_interval(0.50, 0.90) == "50% - 90%"


@patch("coglayer.ui.page_views.coach.httpx.post")
@patch("coglayer.ui.page_views.coach.st")
def test_coach_page_renders(mock_st: MagicMock, mock_post: MagicMock) -> None:
    """Coach page displays info prompt when no conversation exists."""
    session_state: dict[str, object] = {}
    mock_st.session_state = session_state
    mock_st.button.return_value = False
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    render_coach_page("http://testserver", "user_1")
    assert mock_st.info.called


@patch("coglayer.ui.page_views.coach.httpx.post")
@patch("coglayer.ui.page_views.coach.st")
def test_coach_page_403(mock_st: MagicMock, mock_post: MagicMock) -> None:
    """Coach page displays warning if not complete (HTTP 403)."""
    mock_post.return_value = MagicMock(status_code=403, text="Forbidden")
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    render_coach_page("http://testserver", "user_1")
    assert mock_st.warning.called


@patch("coglayer.ui.page_views.consent.httpx.post")
@patch("coglayer.ui.page_views.consent.httpx.get")
@patch("coglayer.ui.page_views.consent.st")
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
    assert mock_st.session_state.get("page") == "lab"


@patch("coglayer.ui.page_views.profile.httpx.get")
@patch("coglayer.ui.page_views.profile.st")
def test_profile_page_empty(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """Profile page displays info when no dimensions exist."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"dimensions": {}})
    mock_st.button.return_value = False
    render_profile_page("http://testserver", "user_1")
    assert mock_st.info.called


@patch("coglayer.ui.page_views.go_no_go.httpx.get")
@patch("coglayer.ui.page_views.go_no_go.st")
def test_go_no_go_already_completed(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """Go/No-Go shows completed banner when task done."""
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"completed_tasks": ["go_no_go"]},
    )
    mock_st.button.return_value = False
    render_go_no_go_page("http://testserver", "user_1", "sess_1")
    assert mock_st.success.called


@patch("coglayer.ui.page_views.sequence_span.httpx.get")
@patch("coglayer.ui.page_views.sequence_span.st")
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
    assert mock_st.radio.call_args.kwargs["options"] == (
        "consent",
        "lab",
        "profile",
        "coach",
        "ioi",
    )
    format_func = mock_st.radio.call_args.kwargs["format_func"]
    options = mock_st.radio.call_args.kwargs["options"]
    labels = [format_func(page) for page in options]
    assert "Next Assessment Task" not in labels
    assert labels[1] == "2. Cognitive Lab"
    assert labels[2] == "3. Cognitive Profile & Dashboard"


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


@patch("coglayer.ui.app.render_profile_dashboard_page")
@patch("coglayer.ui.app.st")
def test_app_main_dispatches_merged_profile_dashboard(
    mock_st: MagicMock, mock_render_profile_dashboard: MagicMock
) -> None:
    """Main Streamlit app router dispatches profile and dashboard to the merged page."""
    from coglayer.ui.app import main

    session_store: dict[str, object] = {"user_id": "user_default", "page": "dashboard"}
    mock_st.session_state = session_store
    mock_st.text_input.return_value = "user_default"
    mock_st.radio.return_value = "profile"
    mock_st.button.return_value = False

    main()
    assert session_store["page"] == "profile"
    assert mock_render_profile_dashboard.called


@patch("coglayer.ui.app.render_cognitive_lab_page")
@patch("coglayer.ui.app.httpx.post")
@patch("coglayer.ui.app.render_consent_page")
@patch("coglayer.ui.app.st")
def test_consent_transition_goes_to_cognitive_lab(
    mock_st: MagicMock,
    mock_render_consent: MagicMock,
    mock_post: MagicMock,
    mock_render_lab: MagicMock,
) -> None:
    """Consent navigation opens the Cognitive Lab without creating a session."""
    from coglayer.ui.app import main

    session_store: dict[str, object] = {
        "user_id": "user_default",
        "page": "consent",
        "session_id": None,
    }
    mock_st.session_state = session_store
    mock_st.context.url = "http://localhost:8501/"
    mock_st.text_input.return_value = "user_default"
    mock_st.button.return_value = False
    mock_st.radio.side_effect = lambda *args, **kwargs: session_store["page"]
    mock_render_consent.side_effect = lambda *args: session_store.update(
        {"page": "lab", "pending_page_selector": "lab"}
    )

    with patch("coglayer.ui.app.st.rerun"):
        main()
        main()

    assert session_store["session_id"] is None
    assert session_store["page"] == "lab"
    mock_post.assert_not_called()
    mock_render_lab.assert_called()
    assert mock_st.radio.call_args.kwargs["key"] == "page_selector"


@patch("coglayer.ui.app.render_profile_dashboard_page")
@patch("coglayer.ui.app.st")
def test_sidebar_navigation_updates_canonical_page(
    mock_st: MagicMock,
    mock_render_profile_dashboard: MagicMock,
) -> None:
    """A sidebar selection updates the canonical page and dispatches it."""
    from coglayer.ui.app import main

    session_store: dict[str, object] = {
        "user_id": "user_default",
        "page": "consent",
        "session_id": "sess_1",
    }
    mock_st.session_state = session_store
    mock_st.context.url = "http://localhost:8501/"
    mock_st.text_input.return_value = "user_default"
    mock_st.radio.return_value = "profile"
    mock_st.button.return_value = False

    def select_profile(*args: object, **kwargs: object) -> str:
        session_store["page_selector"] = "profile"
        callback = kwargs["on_change"]
        assert callable(callback)
        callback()
        return "profile"

    with patch("coglayer.ui.app.st.rerun"):
        mock_st.radio.side_effect = select_profile
        main()

    assert session_store["page"] == "profile"
    mock_render_profile_dashboard.assert_called_once_with("http://localhost:8000", "user_default")
    callback = mock_st.radio.call_args.kwargs["on_change"]
    assert callback is not None


@patch("coglayer.ui.app.render_ioi_page")
@patch("coglayer.ui.app.st")
def test_direct_ioi_url_dispatches_ioi_page(
    mock_st: MagicMock,
    mock_render_ioi: MagicMock,
) -> None:
    """The direct IOI URL selects and dispatches the IOI page."""
    from coglayer.ui.app import main

    session_store: dict[str, object] = {
        "user_id": "user_default",
        "page": "consent",
        "session_id": "sess_1",
    }
    mock_st.session_state = session_store
    mock_st.context.url = "http://localhost:8501/ioi"
    mock_st.text_input.return_value = "user_default"
    mock_st.radio.return_value = "ioi"
    mock_st.button.return_value = False

    main()

    assert session_store["page"] == "ioi"
    mock_render_ioi.assert_called_once_with("http://localhost:8000", "user_default", "sess_1")


def test_navigation_state_consumes_valid_and_invalid_pending_routes() -> None:
    """Pending sidebar routes synchronize safely and invalid values are discarded."""
    from coglayer.ui.app import _prepare_navigation_state

    state: dict[str, object] = {
        "page": "profile",
        "page_selector": "consent",
        "pending_page_selector": "profile",
    }
    with patch("coglayer.ui.app.st.session_state", state):
        _prepare_navigation_state("http://localhost:8501/")
    assert state["page"] == "profile"
    assert state["page_selector"] == "profile"
    assert "pending_page_selector" not in state

    state["page"] = "profile"
    state["pending_page_selector"] = "unknown"
    with patch("coglayer.ui.app.st.session_state", state):
        _prepare_navigation_state("http://localhost:8501/")
    assert state["page"] == "profile"
    assert "pending_page_selector" not in state


def test_ioi_url_does_not_override_later_programmatic_route() -> None:
    """An unchanged IOI URL does not override a queued sidebar route."""
    from coglayer.ui.app import _prepare_navigation_state

    state: dict[str, object] = {"page": "consent"}
    with patch("coglayer.ui.app.st.session_state", state):
        _prepare_navigation_state("http://localhost:8501/ioi")
    assert state["page"] == "ioi"
    assert state["page_selector"] == "ioi"

    rerun_state: dict[str, object] = {
        "page": "next",
        "pending_page_selector": "next",
        "last_seen_url": "http://localhost:8501/ioi",
    }
    with patch("coglayer.ui.app.st.session_state", rerun_state):
        _prepare_navigation_state("http://localhost:8501/ioi")
    assert rerun_state["page"] == "next"
    assert rerun_state["page_selector"] == "lab"
    assert "pending_page_selector" not in rerun_state


@patch("coglayer.ui.page_views.consent.httpx.post")
@patch("coglayer.ui.page_views.consent.httpx.get")
@patch("coglayer.ui.page_views.consent.st")
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


@patch("coglayer.ui.page_views.consent.httpx.post")
@patch("coglayer.ui.page_views.consent.httpx.get")
@patch("coglayer.ui.page_views.consent.st")
def test_existing_consent_continues_to_lab(
    mock_st: MagicMock, mock_get: MagicMock, mock_post: MagicMock
) -> None:
    """Already-consented users continue to the Cognitive Lab."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"has_consented": True})
    mock_st.button.return_value = True
    mock_st.session_state = {}

    render_consent_page("http://testserver", "user_1")

    assert mock_st.session_state["page"] == "lab"
    assert mock_st.session_state["pending_page_selector"] == "lab"
    assert not mock_post.called


@patch("coglayer.ui.app.get_decision")
def test_next_reuses_active_session_and_routes(
    mock_get_decision: MagicMock,
) -> None:
    """The next route reuses the active session without creating another one."""
    from coglayer.ui.app import _handle_next_page

    session_store: dict[str, object] = {"session_id": "sess_1"}
    query_params: dict[str, str] = {}
    mock_get_decision.return_value = {
        "status": "next_task",
        "next_task": "go_no_go",
        "reason": "Start here.",
    }

    with (
        patch("coglayer.ui.app.st.session_state", session_store),
        patch("coglayer.ui.app.st.query_params", query_params),
        patch("coglayer.ui.app.httpx.post") as post,
    ):
        _handle_next_page("user_1")
        _handle_next_page("user_1")

    post.assert_not_called()
    assert mock_get_decision.call_count == 2
    assert session_store["session_id"] == "sess_1"
    assert session_store["page"] == "go_no_go"


@patch("coglayer.ui.app.get_decision")
def test_next_does_not_create_session_without_explicit_selection(
    mock_get_decision: MagicMock,
) -> None:
    """Opening Next without an active session only displays the session picker."""
    from coglayer.ui.app import _handle_next_page

    session_store: dict[str, object] = {}
    with (
        patch("coglayer.ui.app.st.session_state", session_store),
        patch("coglayer.ui.app._render_session_picker") as render_picker,
        patch("coglayer.ui.app.httpx.post") as post,
    ):
        _handle_next_page("user_1")

    post.assert_not_called()
    mock_get_decision.assert_not_called()
    render_picker.assert_called_once_with("user_1")


@patch("coglayer.ui.app.st.rerun")
@patch("coglayer.ui.app.httpx.post")
def test_explicit_new_session_uses_returned_identifier(
    mock_post: MagicMock, mock_rerun: MagicMock
) -> None:
    """The explicit new-session action stores the API-created identifier."""
    from coglayer.ui.app import _create_new_session

    state: dict[str, object] = {"user_id": "user_1"}
    query_params: dict[str, str] = {}
    mock_post.return_value = MagicMock(status_code=201, json=lambda: {"session_id": "new-session"})

    with (
        patch("coglayer.ui.app.st.session_state", state),
        patch("coglayer.ui.app.st.query_params", query_params),
    ):
        _create_new_session("user_1")

    assert state["session_id"] == "new-session"
    assert query_params["session_id"] == "new-session"
    assert state["page"] == "lab"
    assert state["pending_page_selector"] == "lab"
    mock_rerun.assert_called_once()


def test_explicit_session_selection_restores_identifier() -> None:
    """Selecting a listed session stores its validated identifier."""
    from coglayer.ui.app import _select_session

    state: dict[str, object] = {"user_id": "user_1"}
    query_params: dict[str, str] = {}
    with (
        patch("coglayer.ui.app.st.session_state", state),
        patch("coglayer.ui.app.st.query_params", query_params),
    ):
        _select_session(
            {"session_id": "selected-session", "user_id": "user_1", "status": "pending"}
        )

    assert state["session_id"] == "selected-session"
    assert query_params["session_id"] == "selected-session"
    assert state["page"] == "lab"
    assert state["pending_page_selector"] == "lab"


def test_restore_session_from_url_keeps_exact_resumable_session() -> None:
    """A hard refresh restores the URL session without creating another one."""
    from coglayer.ui.app import _restore_session_from_url

    state: dict[str, object] = {}
    query_params = {"session_id": "original-session"}
    session = {
        "session_id": "original-session",
        "user_id": "user_1",
        "status": "pending",
    }
    with (
        patch("coglayer.ui.app.st.session_state", state),
        patch("coglayer.ui.app.st.query_params", query_params),
        patch("coglayer.ui.app.get_assessment_session", return_value=session) as get_session,
    ):
        assert _restore_session_from_url("user_1") == "original-session"

    get_session.assert_called_once_with(
        "http://localhost:8000",
        "user_1",
        "original-session",
    )
    assert state["session_id"] == "original-session"
    assert query_params["session_id"] == "original-session"


def test_restore_session_from_url_clears_non_resumable_or_invalid_ids() -> None:
    """Invalid URL sessions are cleared and never become active state."""
    from coglayer.ui.app import _restore_session_from_url

    for response in (
        {"session_id": "session-1", "user_id": "user_1", "status": "completed"},
        {"session_id": "session-1", "user_id": "user_1", "status": "interrupted"},
        {"session_id": "session-1", "user_id": "other-user", "status": "pending"},
        {"session_id": "other-session", "user_id": "user_1", "status": "pending"},
    ):
        state: dict[str, object] = {}
        query_params = {"session_id": "session-1"}
        with (
            patch("coglayer.ui.app.st.session_state", state),
            patch("coglayer.ui.app.st.query_params", query_params),
            patch("coglayer.ui.app.get_assessment_session", return_value=response),
        ):
            assert _restore_session_from_url("user_1") is None
        assert "session_id" not in query_params
        assert "session_id" not in state


@patch("coglayer.ui.app.render_cognitive_lab_page")
@patch("coglayer.ui.app.get_decision")
@patch("coglayer.ui.app.httpx.post")
@patch("coglayer.ui.app.st")
def test_new_assessment_session_clears_url_before_creating(
    mock_st: MagicMock,
    mock_post: MagicMock,
    mock_get_decision: MagicMock,
    mock_render_lab: MagicMock,
) -> None:
    """The explicit new-session action opens the Cognitive Lab with the new session."""
    from coglayer.ui.app import main

    session_store: dict[str, object] = {
        "user_id": "user_1",
        "page": "profile",
        "session_id": "old-session",
    }
    query_params = {"session_id": "old-session"}
    mock_st.session_state = session_store
    mock_st.query_params = query_params
    mock_st.context.url = "http://localhost:8501/"
    mock_st.text_input.return_value = "user_1"
    mock_st.radio.return_value = "profile"
    mock_st.button.return_value = True
    mock_post.return_value = MagicMock(status_code=201, json=lambda: {"session_id": "new-session"})

    with patch("coglayer.ui.app.st.rerun"):
        main()

    assert session_store["session_id"] == "new-session"
    assert query_params["session_id"] == "new-session"
    assert session_store["page"] == "lab"
    assert mock_post.call_count == 1
    mock_get_decision.assert_not_called()
    mock_render_lab.assert_called_once_with("http://localhost:8000", "user_1")


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
        with (
            patch("coglayer.ui.app.st.session_state", state),
            patch("coglayer.ui.app.st.rerun") as mock_rerun,
        ):
            _route_decision(decision)
        assert state["page"] == expected_page
        if expected_page == "profile":
            assert state["pending_page_selector"] == expected_page
        else:
            assert "pending_page_selector" not in state
        assert mock_rerun.call_count == 1


def test_next_unknown_task_warns_without_rerun() -> None:
    """An unknown task does not repeatedly fetch the same decision."""
    from coglayer.ui.app import _route_decision

    state: dict[str, object] = {}
    with (
        patch("coglayer.ui.app.st.session_state", state),
        patch("coglayer.ui.app.st.rerun") as mock_rerun,
        patch("coglayer.ui.app.st.warning") as mock_warning,
    ):
        _route_decision({"status": "next_task", "next_task": "unknown_game"})

    mock_rerun.assert_not_called()
    mock_warning.assert_called_once_with("The next assessment task is unavailable.")


def test_next_malformed_decision_warns_without_rerun() -> None:
    """A malformed decision does not repeatedly fetch the same decision."""
    from coglayer.ui.app import _route_decision

    state: dict[str, object] = {}
    with (
        patch("coglayer.ui.app.st.session_state", state),
        patch("coglayer.ui.app.st.rerun") as mock_rerun,
        patch("coglayer.ui.app.st.warning") as mock_warning,
    ):
        _route_decision({})

    mock_rerun.assert_not_called()
    mock_warning.assert_called_once_with("The assessment could not determine the next step.")


# ---------------------------------------------------------------------------
# Regression: _render_session_picker must offer a Create button
# ---------------------------------------------------------------------------
def test_session_picker_shows_create_button_when_no_sessions() -> None:
    """When no sessions exist, _render_session_picker renders a Create New Session button."""
    from coglayer.ui.app import _render_session_picker

    button_labels: list[str] = []

    def capture_button(label: str, **kwargs: object) -> bool:
        button_labels.append(label)
        return False

    state: dict[str, object] = {}
    with (
        patch("coglayer.ui.app.st.session_state", state),
        patch("coglayer.ui.app.st.info"),
        patch("coglayer.ui.app.st.caption"),
        patch("coglayer.ui.app.st.divider"),
        patch("coglayer.ui.app.get_assessment_sessions", return_value=[]),
        patch("coglayer.ui.app.st.button", side_effect=capture_button),
    ):
        _render_session_picker("user_1")

    assert "Create New Session" in button_labels


def test_session_picker_create_button_calls_create_session() -> None:
    """Clicking the Create New Session button in the picker creates a session."""
    from coglayer.ui.app import _render_session_picker

    click_count = 0

    def click_create(label: str, **kwargs: object) -> bool:
        nonlocal click_count
        click_count += 1
        # First button call is "Create New Session" (no sessions to resume)
        return label == "Create New Session"

    state: dict[str, object] = {}
    with (
        patch("coglayer.ui.app.st.session_state", state),
        patch("coglayer.ui.app.st.info"),
        patch("coglayer.ui.app.st.caption"),
        patch("coglayer.ui.app.st.divider"),
        patch("coglayer.ui.app.get_assessment_sessions", return_value=[]),
        patch("coglayer.ui.app.st.button", side_effect=click_create),
        patch("coglayer.ui.app._create_new_session") as mock_create,
    ):
        _render_session_picker("user_1")

    mock_create.assert_called_once_with("user_1")


@patch("coglayer.ui.app.render_go_no_go_page")
@patch("coglayer.ui.app.get_decision")
@patch("coglayer.ui.app.st")
def test_internal_next_dispatcher_still_routes_existing_callers(
    mock_st: MagicMock,
    mock_get_decision: MagicMock,
    mock_render_go_no_go: MagicMock,
) -> None:
    """The hidden next route still dispatches the decision engine for callers."""
    from coglayer.ui.app import main

    session_store: dict[str, object] = {
        "user_id": "user_1",
        "page": "next",
        "session_id": "sess_1",
    }
    mock_st.session_state = session_store
    mock_st.context.url = "http://localhost:8501/"
    mock_st.text_input.return_value = "user_1"
    mock_st.radio.return_value = "lab"
    mock_st.button.return_value = False
    mock_get_decision.return_value = {
        "status": "next_task",
        "next_task": "go_no_go",
    }

    with patch("coglayer.ui.app.st.rerun"):
        main()

    assert session_store["page"] == "go_no_go"
    mock_get_decision.assert_called_once()
    mock_render_go_no_go.assert_called_once_with(
        "http://localhost:8000",
        "user_1",
        "sess_1",
    )
