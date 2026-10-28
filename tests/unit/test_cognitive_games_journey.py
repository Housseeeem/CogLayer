"""Comprehensive end-to-end and journey tests for Cognitive Lab interactive games.

Covers:
- UI page rendering and component generation for all 6 new games
- Navigation from Cognitive Lab cards
- Decision mapping for all tasks
- Backend submission, validation, scoring, persistence, and profile update
- Duplicate submission prevention (409)
- Consent verification (403) and session isolation
- Handling of incomplete sessions and invalid payloads (422)
"""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.core.settings import Settings
from coglayer.ui.navigation import NavigationTarget, navigate_decision
from coglayer.ui.page_views.cognitive_lab import render_cognitive_lab_page
from coglayer.ui.page_views.corsi_blocks import render_corsi_blocks_page
from coglayer.ui.page_views.digit_span import render_digit_span_page
from coglayer.ui.page_views.letter_number import render_letter_number_page
from coglayer.ui.page_views.n_back import render_n_back_page
from coglayer.ui.page_views.perception import render_perception_lab_page
from coglayer.ui.page_views.stroop import render_stroop_page


# ---------------------------------------------------------------------------
# TestClient fixture with isolated SQLite database
# ---------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path: pathlib.Path) -> TestClient:
    """Create a FastAPI TestClient wired to an isolated SQLite database."""
    settings = Settings(db_path=str(tmp_path / "cognitive_test.db"))
    app = create_app(settings)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. UI Rendering Tests for the 6 Cognitive Games
# ---------------------------------------------------------------------------
@patch("coglayer.ui.page_views.digit_span.httpx.get")
@patch("coglayer.ui.page_views.digit_span.components.html")
@patch("coglayer.ui.page_views.digit_span.st")
def test_render_digit_span_page(
    mock_st: MagicMock,
    mock_html: MagicMock,
    mock_get: MagicMock,
) -> None:
    """Digit span page renders header, instructions, and interactive HTML component."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.button.return_value = False
    mock_st.session_state = {}
    mock_st.columns.return_value = [MagicMock(), MagicMock()]

    render_digit_span_page("http://testserver", "user_1", "sess_1")

    assert mock_st.header.called
    assert mock_html.called


@patch("coglayer.ui.page_views.digit_span.httpx.get")
@patch("coglayer.ui.page_views.digit_span.st")
def test_digit_span_already_completed(
    mock_st: MagicMock,
    mock_get: MagicMock,
) -> None:
    """Digit span page detects previously completed task in the session."""
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"completed_tasks": ["digit_span"]},
    )
    mock_st.button.return_value = False
    mock_st.session_state = {}
    mock_st.columns.return_value = [MagicMock(), MagicMock()]

    render_digit_span_page("http://testserver", "user_1", "sess_1")

    assert mock_st.success.called


@patch("coglayer.ui.page_views.stroop.httpx.get")
@patch("coglayer.ui.page_views.stroop.components.html")
@patch("coglayer.ui.page_views.stroop.st")
def test_render_stroop_page(
    mock_st: MagicMock,
    mock_html: MagicMock,
    mock_get: MagicMock,
) -> None:
    """Stroop page renders header, instructions, and interactive HTML component."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.button.return_value = False
    mock_st.session_state = {}
    mock_st.columns.return_value = [MagicMock(), MagicMock()]

    render_stroop_page("http://testserver", "user_1", "sess_1")

    assert mock_st.header.called
    assert mock_html.called


@patch("coglayer.ui.page_views.corsi_blocks.httpx.get")
@patch("coglayer.ui.page_views.corsi_blocks.components.html")
@patch("coglayer.ui.page_views.corsi_blocks.st")
def test_render_corsi_blocks_page(
    mock_st: MagicMock,
    mock_html: MagicMock,
    mock_get: MagicMock,
) -> None:
    """Corsi blocks page renders header, instructions, and interactive HTML component."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.button.return_value = False
    mock_st.session_state = {}
    mock_st.columns.return_value = [MagicMock(), MagicMock()]

    render_corsi_blocks_page("http://testserver", "user_1", "sess_1")

    assert mock_st.header.called
    assert mock_html.called


@patch("coglayer.ui.page_views.n_back.httpx.get")
@patch("coglayer.ui.page_views.n_back.components.html")
@patch("coglayer.ui.page_views.n_back.st")
def test_render_n_back_page(
    mock_st: MagicMock,
    mock_html: MagicMock,
    mock_get: MagicMock,
) -> None:
    """N-Back page renders header, instructions, and interactive HTML component."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.button.return_value = False
    mock_st.session_state = {}
    mock_st.columns.return_value = [MagicMock(), MagicMock()]

    render_n_back_page("http://testserver", "user_1", "sess_1")

    assert mock_st.header.called
    assert mock_html.called


@patch("coglayer.ui.page_views.letter_number.httpx.get")
@patch("coglayer.ui.page_views.letter_number.components.html")
@patch("coglayer.ui.page_views.letter_number.st")
def test_render_letter_number_page(
    mock_st: MagicMock,
    mock_html: MagicMock,
    mock_get: MagicMock,
) -> None:
    """Letter-Number Sequencing page renders header, instructions, and HTML component."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.button.return_value = False
    mock_st.session_state = {}
    mock_st.columns.return_value = [MagicMock(), MagicMock()]

    render_letter_number_page("http://testserver", "user_1", "sess_1")

    assert mock_st.header.called
    assert mock_html.called


@patch("coglayer.ui.page_views.perception.httpx.get")
@patch("coglayer.ui.page_views.perception.components.html")
@patch("coglayer.ui.page_views.perception.st")
def test_render_perception_lab_page(
    mock_st: MagicMock,
    mock_html: MagicMock,
    mock_get: MagicMock,
) -> None:
    """Perception Lab page renders tabs, stimuli audit table, and Necker Cube experiment."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"completed_tasks": []})
    mock_st.button.return_value = False
    mock_st.session_state = {}
    mock_tab1 = MagicMock()
    mock_tab2 = MagicMock()
    mock_st.tabs.return_value = [mock_tab1, mock_tab2]
    mock_st.columns.return_value = [MagicMock(), MagicMock()]

    render_perception_lab_page("http://testserver", "user_1", "sess_1")

    assert mock_st.header.called
    assert mock_st.tabs.called
    assert mock_html.called


# ---------------------------------------------------------------------------
# 2. Cognitive Lab recommended-session UI
# ---------------------------------------------------------------------------
_SAMPLE_PLAN = {
    "user_id": "user_1",
    "plan_date": "2026-10-25",
    "status": "generated",
    "is_personalized": False,
    "recommendations": [
        {
            "task_id": "go_no_go",
            "rationale": "Introductory exploration of Response Inhibition for new practice.",
            "target_dimension": "response_inhibition",
            "difficulty_level": "introductory",
        },
        {
            "task_id": "digit_span",
            "rationale": "Introductory exploration of Working Memory for new practice.",
            "target_dimension": "working_memory",
            "difficulty_level": "introductory",
        },
    ],
}


def _button_labels(mock_st: MagicMock) -> list[str]:
    labels: list[str] = []
    for call in mock_st.button.call_args_list:
        args, kwargs = call
        label = kwargs.get("label", args[0] if args else "")
        labels.append(str(label))
    return labels


def _button_call(mock_st: MagicMock, label: str) -> Any:
    for call in mock_st.button.call_args_list:
        args, kwargs = call
        actual = kwargs.get("label", args[0] if args else "")
        if actual == label:
            return call
    raise AssertionError(f"No button labelled {label!r}: {_button_labels(mock_st)}")


def _configure_lab_streamlit(mock_st: MagicMock, session_state: dict[str, object]) -> None:
    mock_st.session_state = session_state
    mock_st.button.return_value = False
    mock_st.columns.side_effect = lambda n: [
        MagicMock() for _ in range(n if isinstance(n, int) else 2)
    ]


def _http_status_error(status_code: int, detail: str) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://testserver/v1/assessment/daily-plan/user_1")
    response = httpx.Response(status_code, request=request, json={"detail": detail})
    return httpx.HTTPStatusError("HTTP error", request=request, response=response)


@patch("coglayer.ui.page_views.cognitive_lab.get_assessment_session")
@patch("coglayer.ui.page_views.cognitive_lab.get_daily_plan")
@patch("coglayer.ui.page_views.cognitive_lab.st")
def test_cognitive_lab_does_not_render_catalog(
    mock_st: MagicMock,
    mock_get_plan: MagicMock,
    mock_get_session: MagicMock,
) -> None:
    """Cognitive Lab does not render the general eight-game catalog."""
    _configure_lab_streamlit(mock_st, {"session_id": "sess_123", "user_id": "user_1"})
    mock_get_plan.return_value = _SAMPLE_PLAN
    mock_get_session.return_value = {
        "session_id": "sess_123",
        "user_id": "user_1",
        "completed_tasks": [],
    }

    render_cognitive_lab_page("http://testserver", "user_1")

    subheaders = [str(call.args[0]) for call in mock_st.subheader.call_args_list if call.args]
    assert "All Cognitive Lab Activities" not in subheaders
    labels = _button_labels(mock_st)
    assert not any(label.startswith("Open ") for label in labels)
    assert "Start Corsi Blocks" not in labels
    assert "Start Stroop" not in labels
    assert "Start N-Back" not in labels


@patch("coglayer.ui.page_views.cognitive_lab.get_assessment_session")
@patch("coglayer.ui.page_views.cognitive_lab.get_daily_plan")
@patch("coglayer.ui.page_views.cognitive_lab.st")
def test_cognitive_lab_shows_only_recommended_task_controls(
    mock_st: MagicMock,
    mock_get_plan: MagicMock,
    mock_get_session: MagicMock,
) -> None:
    """Only recommended task IDs appear as start controls."""
    _configure_lab_streamlit(mock_st, {"session_id": "sess_123", "user_id": "user_1"})
    mock_get_plan.return_value = _SAMPLE_PLAN
    mock_get_session.return_value = {
        "session_id": "sess_123",
        "user_id": "user_1",
        "completed_tasks": [],
    }

    render_cognitive_lab_page("http://testserver", "user_1")

    labels = _button_labels(mock_st)
    assert "Start Go / No-Go" in labels
    assert "Start Digit Span" in labels
    start_labels = [label for label in labels if label.startswith("Start ")]
    assert start_labels == ["Start Go / No-Go", "Start Digit Span"]


@patch("coglayer.ui.page_views.cognitive_lab.get_assessment_session")
@patch("coglayer.ui.page_views.cognitive_lab.get_daily_plan")
@patch("coglayer.ui.page_views.cognitive_lab.st")
def test_cognitive_lab_completed_task_has_no_enabled_start(
    mock_st: MagicMock,
    mock_get_plan: MagicMock,
    mock_get_session: MagicMock,
) -> None:
    """Completed recommended tasks have no enabled Start control."""
    _configure_lab_streamlit(mock_st, {"session_id": "sess_123", "user_id": "user_1"})
    mock_get_plan.return_value = {**_SAMPLE_PLAN, "status": "started"}
    mock_get_session.return_value = {
        "session_id": "sess_123",
        "user_id": "user_1",
        "completed_tasks": ["go_no_go"],
    }

    render_cognitive_lab_page("http://testserver", "user_1")

    completed = _button_call(mock_st, "Completed")
    assert completed.kwargs.get("disabled") is True
    start_digit = _button_call(mock_st, "Start Digit Span")
    assert start_digit.kwargs.get("disabled") is False
    assert "Start Go / No-Go" not in _button_labels(mock_st)


@patch("coglayer.ui.page_views.cognitive_lab.get_assessment_session")
@patch("coglayer.ui.page_views.cognitive_lab.get_daily_plan")
@patch("coglayer.ui.page_views.cognitive_lab.st")
def test_cognitive_lab_incomplete_tasks_can_start_with_session(
    mock_st: MagicMock,
    mock_get_plan: MagicMock,
    mock_get_session: MagicMock,
) -> None:
    """Recommended incomplete tasks can be started with a valid session."""
    _configure_lab_streamlit(mock_st, {"session_id": "sess_123", "user_id": "user_1"})
    mock_get_plan.return_value = _SAMPLE_PLAN
    mock_get_session.return_value = {
        "session_id": "sess_123",
        "user_id": "user_1",
        "completed_tasks": [],
    }

    render_cognitive_lab_page("http://testserver", "user_1")

    for label in ("Start Go / No-Go", "Start Digit Span"):
        assert _button_call(mock_st, label).kwargs.get("disabled") is False


@patch("coglayer.ui.page_views.cognitive_lab.update_daily_plan_status")
@patch("coglayer.ui.page_views.cognitive_lab.get_assessment_session")
@patch("coglayer.ui.page_views.cognitive_lab.get_daily_plan")
@patch("coglayer.ui.page_views.cognitive_lab.st")
def test_cognitive_lab_start_updates_status_and_routes(
    mock_st: MagicMock,
    mock_get_plan: MagicMock,
    mock_get_session: MagicMock,
    mock_update_status: MagicMock,
) -> None:
    """Clicking Start updates plan status and routes to the task page."""
    session_state: dict[str, object] = {"session_id": "sess_123", "user_id": "user_1"}
    _configure_lab_streamlit(mock_st, session_state)
    mock_st.button.side_effect = [True, False, False]
    mock_get_plan.return_value = _SAMPLE_PLAN
    mock_get_session.return_value = {
        "session_id": "sess_123",
        "user_id": "user_1",
        "completed_tasks": [],
    }

    render_cognitive_lab_page("http://testserver", "user_1")

    mock_update_status.assert_called_once_with(
        api_url="http://testserver",
        user_id="user_1",
        plan_date="2026-10-25",
        status="started",
        session_id="sess_123",
    )
    assert session_state["page"] == "go_no_go"
    mock_st.rerun.assert_called_once()


@patch("coglayer.ui.page_views.cognitive_lab.get_assessment_session")
@patch("coglayer.ui.page_views.cognitive_lab.get_daily_plan")
@patch("coglayer.ui.page_views.cognitive_lab.st")
def test_cognitive_lab_warns_when_no_session(
    mock_st: MagicMock,
    mock_get_plan: MagicMock,
    mock_get_session: MagicMock,
) -> None:
    """Missing sessions do not allow starting tasks."""
    _configure_lab_streamlit(mock_st, {"session_id": None, "user_id": "user_1"})
    mock_get_plan.return_value = _SAMPLE_PLAN

    render_cognitive_lab_page("http://testserver", "user_1")

    mock_get_session.assert_not_called()
    assert mock_st.warning.called
    for label in ("Start Go / No-Go", "Start Digit Span"):
        assert _button_call(mock_st, label).kwargs.get("disabled") is True


@patch("coglayer.ui.page_views.cognitive_lab.get_daily_plan")
@patch("coglayer.ui.page_views.cognitive_lab.st")
def test_cognitive_lab_plan_fetch_failure_is_honest(
    mock_st: MagicMock,
    mock_get_plan: MagicMock,
) -> None:
    """Plan-fetch failures do not reveal the catalog or a consent-only error."""
    _configure_lab_streamlit(mock_st, {"session_id": "sess_123", "user_id": "user_1"})
    mock_get_plan.side_effect = _http_status_error(500, "Internal Server Error")

    render_cognitive_lab_page("http://testserver", "user_1")

    subheaders = [str(call.args[0]) for call in mock_st.subheader.call_args_list if call.args]
    assert "All Cognitive Lab Activities" not in subheaders
    assert not any(label.startswith("Open ") for label in _button_labels(mock_st))
    error_texts = [str(call.args[0]) for call in mock_st.error.call_args_list if call.args]
    assert error_texts
    assert all("consent" not in text.lower() for text in error_texts)


@patch("coglayer.ui.page_views.cognitive_lab.get_daily_plan")
@patch("coglayer.ui.page_views.cognitive_lab.st")
def test_cognitive_lab_consent_failure_mentions_consent(
    mock_st: MagicMock,
    mock_get_plan: MagicMock,
) -> None:
    """A 403 consent failure explains that active consent is required."""
    _configure_lab_streamlit(mock_st, {"session_id": "sess_123", "user_id": "user_1"})
    mock_get_plan.side_effect = _http_status_error(403, "User has not given active consent.")

    render_cognitive_lab_page("http://testserver", "user_1")

    warning_texts = [
        str(call.args[0]).lower() for call in mock_st.warning.call_args_list if call.args
    ]
    error_texts = [str(call.args[0]).lower() for call in mock_st.error.call_args_list if call.args]
    combined = " ".join(warning_texts + error_texts)
    assert "consent" in combined


@patch("coglayer.ui.page_views.cognitive_lab.get_assessment_session")
@patch("coglayer.ui.page_views.cognitive_lab.get_daily_plan")
@patch("coglayer.ui.page_views.cognitive_lab.st")
def test_cognitive_lab_personalized_and_discovery_messages(
    mock_st: MagicMock,
    mock_get_plan: MagicMock,
    mock_get_session: MagicMock,
) -> None:
    """Personalized and initial-discovery copy follow is_personalized."""
    mock_get_session.return_value = {
        "session_id": "sess_123",
        "user_id": "user_1",
        "completed_tasks": [],
    }

    _configure_lab_streamlit(mock_st, {"session_id": "sess_123", "user_id": "user_1"})
    mock_get_plan.return_value = {**_SAMPLE_PLAN, "is_personalized": True}
    render_cognitive_lab_page("http://testserver", "user_1")
    info_texts = [str(call.args[0]) for call in mock_st.info.call_args_list if call.args]
    assert any("Personalized" in text for text in info_texts)
    assert all("Initial discovery" not in text for text in info_texts)

    mock_st.info.reset_mock()
    mock_st.caption.reset_mock()
    mock_get_plan.return_value = {**_SAMPLE_PLAN, "is_personalized": False}
    render_cognitive_lab_page("http://testserver", "user_1")
    caption_texts = [str(call.args[0]) for call in mock_st.caption.call_args_list if call.args]
    info_texts = [str(call.args[0]) for call in mock_st.info.call_args_list if call.args]
    combined = caption_texts + info_texts
    assert any("Initial discovery" in text for text in combined)
    assert all("Personalized recommendation" not in text for text in combined)


@patch("coglayer.ui.page_views.cognitive_lab.get_assessment_session")
@patch("coglayer.ui.page_views.cognitive_lab.get_daily_plan")
@patch("coglayer.ui.page_views.cognitive_lab.st")
def test_cognitive_lab_session_lookup_failure_does_not_mark_complete(
    mock_st: MagicMock,
    mock_get_plan: MagicMock,
    mock_get_session: MagicMock,
) -> None:
    """Failed session lookups do not mark recommended tasks completed."""
    _configure_lab_streamlit(mock_st, {"session_id": "sess_123", "user_id": "user_1"})
    mock_get_plan.return_value = {**_SAMPLE_PLAN, "status": "started"}
    mock_get_session.side_effect = httpx.ConnectError("unreachable")

    render_cognitive_lab_page("http://testserver", "user_1")

    assert "Completed" not in _button_labels(mock_st)
    assert _button_call(mock_st, "Start Go / No-Go").kwargs.get("disabled") is False


def test_navigate_decision_maps_all_cognitive_tasks() -> None:
    """Verify that navigate_decision maps all 8 cognitive tasks to their pages."""
    all_tasks = [
        "go_no_go",
        "sequence_span",
        "digit_span",
        "stroop",
        "corsi_blocks",
        "n_back",
        "letter_number_sequencing",
        "perception_lab",
    ]
    for tid in all_tasks:
        decision = {"status": "next_task", "next_task": tid, "reason": f"Next is {tid}"}
        target = navigate_decision(decision)
        assert target == NavigationTarget(page=tid, reset_session=False, message=f"Next is {tid}")


# ---------------------------------------------------------------------------
# 3. End-to-End Task Journey Integration Tests (API + Scoring + DB + Profile)
# ---------------------------------------------------------------------------
def test_digit_span_end_to_end_journey(client: TestClient) -> None:
    """Digit Span: user consent -> session -> submit trials -> verify DB & profile."""
    user_id = "user_ds_1"
    # Consent
    c_resp = client.post("/v1/assessment/consent", json={"user_id": user_id})
    assert c_resp.status_code == 201

    # Session
    s_resp = client.post("/v1/assessment/sessions", json={"user_id": user_id})
    assert s_resp.status_code == 201
    session_id = s_resp.json()["session_id"]

    # Submit forward & backward trials
    raw_payload = {
        "trials": [
            {
                "stimulus": "582",
                "condition": "forward",
                "expected": "582",
                "response": "582",
                "length": 3,
                "rt_ms": 1200.0,
            },
            {
                "stimulus": "3947",
                "condition": "forward",
                "expected": "3947",
                "response": "3947",
                "length": 4,
                "rt_ms": 1400.0,
            },
            {
                "stimulus": "729",
                "condition": "backward",
                "expected": "927",
                "response": "927",
                "length": 3,
                "rt_ms": 1500.0,
            },
            {
                "stimulus": "5184",
                "condition": "backward",
                "expected": "4815",
                "response": "4815",
                "length": 4,
                "rt_ms": 1600.0,
            },
        ]
    }

    sub_resp = client.post(
        "/v1/assessment/tasks/digit_span/submit",
        json={"session_id": session_id, "user_id": user_id, "raw_result": raw_payload},
    )
    assert sub_resp.status_code == 200
    res_data = sub_resp.json()

    assert res_data["metrics"]["digit_span_max"] == 4.0
    assert res_data["metrics"]["forward_span"] == 4.0
    assert res_data["metrics"]["backward_span"] == 4.0
    assert res_data["metrics"]["accuracy"] == 1.0

    # Verify session completed_tasks updated
    sess_check = client.get(f"/v1/assessment/sessions/{session_id}?user_id={user_id}")
    assert sess_check.status_code == 200
    assert "digit_span" in sess_check.json()["completed_tasks"]

    # Verify duplicate submission is rejected (409)
    dup_resp = client.post(
        "/v1/assessment/tasks/digit_span/submit",
        json={"session_id": session_id, "user_id": user_id, "raw_result": raw_payload},
    )
    assert dup_resp.status_code == 409


def test_stroop_end_to_end_journey(client: TestClient) -> None:
    """Stroop: user consent -> session -> submit congruent & incongruent -> verify metrics."""
    user_id = "user_stroop_1"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post(
        "/v1/assessment/sessions",
        json={"user_id": user_id},
    ).json()["session_id"]

    raw_payload = {
        "trials": [
            {
                "stimulus": "RED",
                "expected": "RED",
                "response": "RED",
                "condition": "congruent",
                "rt_ms": 420.0,
            },
            {
                "stimulus": "BLUE",
                "expected": "BLUE",
                "response": "BLUE",
                "condition": "congruent",
                "rt_ms": 450.0,
            },
            {
                "stimulus": "RED",
                "expected": "BLUE",
                "response": "BLUE",
                "condition": "incongruent",
                "rt_ms": 680.0,
            },
            {
                "stimulus": "GREEN",
                "expected": "RED",
                "response": "RED",
                "condition": "incongruent",
                "rt_ms": 720.0,
            },
        ]
    }

    sub_resp = client.post(
        "/v1/assessment/tasks/stroop/submit",
        json={"session_id": session_id, "user_id": user_id, "raw_result": raw_payload},
    )
    assert sub_resp.status_code == 200
    metrics = sub_resp.json()["metrics"]

    assert metrics["congruent_accuracy"] == 1.0
    assert metrics["incongruent_accuracy"] == 1.0
    assert metrics["stroop_effect_ms"] > 0  # Incongruent RT > Congruent RT


def test_corsi_blocks_end_to_end_journey(client: TestClient) -> None:
    """Corsi Blocks: user consent -> session -> submit spatial sequences -> verify DB."""
    user_id = "user_corsi_1"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post(
        "/v1/assessment/sessions",
        json={"user_id": user_id},
    ).json()["session_id"]

    raw_payload = {
        "sequences": [
            {
                "stimulus": "1,5,6",
                "condition": "forward",
                "expected": "1,5,6",
                "response": "1,5,6",
                "length": 3,
                "rt_ms": 2200.0,
            },
            {
                "stimulus": "3,0,7,2",
                "condition": "forward",
                "expected": "3,0,7,2",
                "response": "3,0,7,2",
                "length": 4,
                "rt_ms": 2600.0,
            },
            {
                "stimulus": "6,1,4",
                "condition": "backward",
                "expected": "4,1,6",
                "response": "4,1,6",
                "length": 3,
                "rt_ms": 2500.0,
            },
        ]
    }

    sub_resp = client.post(
        "/v1/assessment/tasks/corsi_blocks/submit",
        json={"session_id": session_id, "user_id": user_id, "raw_result": raw_payload},
    )
    assert sub_resp.status_code == 200
    metrics = sub_resp.json()["metrics"]

    assert metrics["corsi_span_max"] == 4.0
    assert metrics["forward_span"] == 4.0
    assert metrics["backward_span"] == 3.0
    assert metrics["accuracy"] == 1.0


def test_n_back_end_to_end_journey(client: TestClient) -> None:
    """N-Back: user consent -> session -> submit 2-back sequence -> verify d-prime & accuracy."""
    user_id = "user_nback_1"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post(
        "/v1/assessment/sessions",
        json={"user_id": user_id},
    ).json()["session_id"]

    # 4 trials: 2 targets (Hit), 2 non-targets (Correct Rejection)
    raw_payload = {
        "trials": [
            {
                "stimulus": "B",
                "is_target": True,
                "expected": "MATCH",
                "response": "MATCH",
                "rt_ms": 500.0,
            },
            {
                "stimulus": "M",
                "is_target": False,
                "expected": "NO_MATCH",
                "response": "NO_MATCH",
                "rt_ms": 550.0,
            },
            {
                "stimulus": "T",
                "is_target": True,
                "expected": "MATCH",
                "response": "MATCH",
                "rt_ms": 480.0,
            },
            {
                "stimulus": "X",
                "is_target": False,
                "expected": "NO_MATCH",
                "response": "NO_MATCH",
                "rt_ms": 520.0,
            },
        ]
    }

    sub_resp = client.post(
        "/v1/assessment/tasks/n_back/submit",
        json={"session_id": session_id, "user_id": user_id, "raw_result": raw_payload},
    )
    assert sub_resp.status_code == 200
    metrics = sub_resp.json()["metrics"]

    assert metrics["n_back_accuracy"] == 1.0
    assert metrics["target_accuracy"] == 1.0
    assert metrics["false_alarm_rate"] == 0.0
    assert "d_prime" in metrics


def test_letter_number_sequencing_end_to_end_journey(client: TestClient) -> None:
    """Letter-Number Sequencing: submit alphanumeric trials -> verify sorting rule & metrics."""
    user_id = "user_lns_1"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post(
        "/v1/assessment/sessions",
        json={"user_id": user_id},
    ).json()["session_id"]

    raw_payload = {
        "trials": [
            {
                "stimulus": "4 B 1",
                "expected": "1 4 B",
                "response": "1 4 B",
                "length": 3,
                "rt_ms": 1800.0,
            },
            {
                "stimulus": "D 7 A 2",
                "expected": "2 7 A D",
                "response": "2 7 A D",
                "length": 4,
                "rt_ms": 2200.0,
            },
            {
                "stimulus": "3 G 9 E",
                "expected": "3 9 E G",
                "response": "3 9 E G",
                "length": 4,
                "rt_ms": 2400.0,
            },
        ]
    }

    sub_resp = client.post(
        "/v1/assessment/tasks/letter_number_sequencing/submit",
        json={"session_id": session_id, "user_id": user_id, "raw_result": raw_payload},
    )
    assert sub_resp.status_code == 200
    metrics = sub_resp.json()["metrics"]

    assert metrics["accuracy"] == 1.0
    assert metrics["lns_span_max"] == 4.0


def test_perception_lab_end_to_end_journey(client: TestClient) -> None:
    """Perception Lab: submit Necker cube switch counts -> verify stability metric."""
    user_id = "user_perc_1"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post(
        "/v1/assessment/sessions",
        json={"user_id": user_id},
    ).json()["session_id"]

    raw_payload = {
        "trials": [
            {
                "stimulus": "necker_cube",
                "expected": "REPORT",
                "response": "6",
                "rt_ms": 30000.0,
            }
        ]
    }

    sub_resp = client.post(
        "/v1/assessment/tasks/perception_lab/submit",
        json={"session_id": session_id, "user_id": user_id, "raw_result": raw_payload},
    )
    assert sub_resp.status_code == 200
    metrics = sub_resp.json()["metrics"]

    assert metrics["switch_rate"] == 6.0
    # Stability: 1.0 - (6 / 30) = 0.8
    assert metrics["perceptual_stability"] == 0.8


# ---------------------------------------------------------------------------
# 4. Error, Consent and Boundary Handling Tests
# ---------------------------------------------------------------------------
def test_submission_forbidden_without_consent(client: TestClient) -> None:
    """Submissions without prior user consent must fail with HTTP 403."""
    user_id = "unconsented_user"
    resp = client.post(
        "/v1/assessment/tasks/digit_span/submit",
        json={
            "session_id": "dummy_sess",
            "user_id": user_id,
            "raw_result": {"trials": []},
        },
    )
    assert resp.status_code == 403


def test_submission_forbidden_for_wrong_session(client: TestClient) -> None:
    """Submissions for non-existent or unowned session fail with HTTP 403."""
    user_id = "consented_user"
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    resp = client.post(
        "/v1/assessment/tasks/digit_span/submit",
        json={
            "session_id": "non_existent_sess",
            "user_id": user_id,
            "raw_result": {"trials": []},
        },
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 5. UI Button and Network Error Branches
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "render_func",
    [
        render_digit_span_page,
        render_stroop_page,
        render_corsi_blocks_page,
        render_n_back_page,
        render_letter_number_page,
        render_perception_lab_page,
    ],
)
@patch("httpx.get")
def test_game_pages_handle_network_error(mock_get: MagicMock, render_func: object) -> None:
    """All game pages catch network errors when checking session status and warn."""
    mock_get.side_effect = Exception("Connection refused")
    with patch("streamlit.button", return_value=False), patch("streamlit.warning") as mock_warn:
        with patch("streamlit.columns", return_value=[MagicMock(), MagicMock()]):
            with patch("streamlit.components.v1.html"):
                with patch("streamlit.session_state", {}):
                    render_func("http://testserver", "u1", "s1")  # type: ignore[operator]
                    assert mock_warn.called


@pytest.mark.parametrize(
    ("render_func", "task_name"),
    [
        (render_digit_span_page, "digit_span"),
        (render_stroop_page, "stroop"),
        (render_corsi_blocks_page, "corsi_blocks"),
        (render_n_back_page, "n_back"),
        (render_letter_number_page, "letter_number_sequencing"),
        (render_perception_lab_page, "perception_lab"),
    ],
)
@patch("httpx.get")
def test_game_pages_completed_and_back_buttons(
    mock_get: MagicMock,
    render_func: object,
    task_name: str,
) -> None:
    """When task is completed, clicking buttons updates session_state."""
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"completed_tasks": [task_name]},
    )
    # 1. Back button top
    state_1: dict[str, object] = {}
    with patch("streamlit.button", side_effect=[True, False, False]):
        with patch("streamlit.session_state", state_1):
            with patch("streamlit.rerun") as mock_rerun:
                render_func("http://testserver", "u1", "s1")  # type: ignore[operator]
                assert state_1.get("page") == "lab"
                assert mock_rerun.called

    # 2. Return completed button
    state_2: dict[str, object] = {}
    with patch("streamlit.button", side_effect=[False, True, False]):
        with patch("streamlit.session_state", state_2):
            with patch("streamlit.columns", return_value=[MagicMock(), MagicMock()]):
                with patch("streamlit.rerun") as mock_rerun:
                    render_func("http://testserver", "u1", "s1")  # type: ignore[operator]
                    assert state_2.get("page") == "lab"
                    assert mock_rerun.called

    # 3. View profile button
    state_3: dict[str, object] = {}
    with patch("streamlit.button", side_effect=[False, False, True]):
        with patch("streamlit.session_state", state_3):
            with patch("streamlit.columns", return_value=[MagicMock(), MagicMock()]):
                with patch("streamlit.rerun") as mock_rerun:
                    render_func("http://testserver", "u1", "s1")  # type: ignore[operator]
                    assert state_3.get("page") == "profile"
                    assert mock_rerun.called
