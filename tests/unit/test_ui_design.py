"""Presentation regressions for the integrated CogLayer design."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from coglayer.ui.design import (
    activity_card_html,
    activity_frame_html,
    interval_bar_html,
    lab_hero_html,
    workspace_header_html,
)
from coglayer.ui.page_views.cognitive_lab import render_cognitive_lab_page


def test_display_content_cannot_inject_html() -> None:
    """API-derived labels and descriptions remain text in styled cards."""
    card = activity_card_html(
        task_id="digit_span",
        label='<script>alert("label")</script>',
        dimension="Memory & attention",
        level="Introductory",
        description='<img src=x onerror="alert(1)">',
    )

    assert "<script>" not in card
    assert "<img" not in card
    assert "&lt;script&gt;" in card
    assert "Memory &amp; attention" in card
    assert "&lt;img" in card
    assert "&lt;img" in workspace_header_html("<img src=x>")


def test_lab_hero_reports_only_supplied_activity_completion() -> None:
    """Progress describes the active plan, without invented performance data."""
    hero = lab_hero_html(completed=1, total=3)

    assert "1 of 3 activities complete" in hero
    assert 'role="progressbar"' in hero
    assert 'aria-valuenow="1"' in hero
    assert 'aria-valuemax="3"' in hero
    assert "Alex" not in hero
    assert "74%" not in hero
    assert "minutes" not in hero


def test_empty_lab_plan_has_no_invalid_progressbar() -> None:
    """A missing plan does not expose a zero-maximum progressbar."""
    hero = lab_hero_html(completed=0, total=0)

    assert "No activities recommended yet" in hero
    assert "progressbar" not in hero


def test_interval_visualization_uses_the_api_estimate() -> None:
    """The visual marker uses the supplied [0, 1] estimate and interval."""
    bar = interval_bar_html(lower=0.4, upper=0.8, mean=0.65)

    assert "--lower:40.0%" in bar
    assert "--range:40.0%" in bar
    assert "--mean:65.0%" in bar
    assert 'aria-hidden="true"' in bar


@pytest.mark.parametrize("head", [True, False])
def test_activity_skin_preserves_stimuli_and_timing_code(head: bool) -> None:
    """Only surrounding CSS is added; stimulus rules and scripts stay intact."""
    styles = "<style>.go{background:#10b981}.nogo{background:#ef4444}</style>"
    script = "const onset = performance.now(); setTimeout(nextTrial, 900);"
    source = f"<body><script>{script}</script></body>"
    if head:
        source = f"<head>{styles}</head>{source}"
    else:
        source = styles + source

    styled = activity_frame_html(source)

    assert styles in styled
    assert re.findall(r"<script>(.*?)</script>", styled) == [script]
    assert 'id="coglayer-activity-style"' in styled
    assert activity_frame_html(styled) == styled


@patch("coglayer.ui.page_views.cognitive_lab.get_daily_plan")
@patch("coglayer.ui.page_views.cognitive_lab.get_assessment_session")
@patch("coglayer.ui.page_views.cognitive_lab.st")
def test_styled_lab_counts_only_recommended_tasks_from_owned_session(
    mock_st: MagicMock,
    mock_session: MagicMock,
    mock_plan: MagicMock,
) -> None:
    """The integrated hero counts API-owned plan completion, not sample fixtures."""
    mock_st.session_state = {"user_id": "real-user", "session_id": "real-session"}
    mock_st.button.return_value = False
    mock_st.columns.return_value = [MagicMock(), MagicMock()]
    mock_plan.return_value = {
        "recommendations": [
            {"task_id": "go_no_go", "target_dimension": "response_inhibition"},
            {"task_id": "digit_span", "target_dimension": "working_memory"},
        ],
        "status": "started",
    }
    mock_session.return_value = {
        "user_id": "real-user",
        "session_id": "real-session",
        "completed_tasks": ["go_no_go", "unrelated-task"],
    }

    render_cognitive_lab_page("http://testserver", "real-user")

    markup = "\n".join(str(call.args[0]) for call in mock_st.markdown.call_args_list)
    assert "1 of 2 activities complete" in markup
    assert "2 of 2 activities complete" not in markup
    assert "Sample" not in markup
    mock_session.assert_called_once_with("http://testserver", "real-user", "real-session")


def test_streamlit_workspace_keeps_the_real_session_when_starting_an_activity() -> None:
    """The actual Streamlit entrypoint starts an API recommendation in the active session."""
    app_path = Path(__file__).parents[2] / "src/coglayer/ui/app.py"

    def response_for(url: str, **_kwargs: object) -> httpx.Response:
        payload: dict[str, object]
        if "/onboarding/profile/" in url:
            payload = {"theme": "standard"}
        elif "/daily-plan/" in url:
            payload = {
                "recommendations": [
                    {"task_id": "go_no_go", "target_dimension": "response_inhibition"}
                ],
                "plan_date": "2026-10-30",
                "status": "generated",
            }
        elif "/sessions/real-session" in url:
            payload = {
                "user_id": "real-user",
                "session_id": "real-session",
                "completed_tasks": [],
            }
        else:
            raise AssertionError(f"Unexpected HTTP request: {url}")
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    with (
        patch("httpx.get", side_effect=response_for),
        patch("httpx.post") as create_session,
        patch("httpx.patch") as start_plan,
    ):
        start_plan.return_value = httpx.Response(
            200,
            json={"status": "started"},
            request=httpx.Request("PATCH", "http://testserver/daily-plan"),
        )
        app = AppTest.from_file(app_path, default_timeout=10)
        app.session_state["user_id"] = "real-user"
        app.session_state["session_id"] = "real-session"
        app.session_state["page"] = "lab"
        app.run()

        assert not app.exception
        assert any("0 of 1 activities complete" in item.value for item in app.markdown)
        assert any("cog-brand" in item.value for item in app.markdown)
        app.button(key="daily_rec_go_no_go").click().run()

        assert not app.exception
        assert app.session_state["session_id"] == "real-session"
        assert app.session_state["page"] == "go_no_go"
        assert app.query_params["session_id"] == "real-session"
        assert any("Go / No-Go" in item.value for item in app.header)
        start_plan.assert_called_once()
        assert start_plan.call_args.kwargs["json"]["session_id"] == "real-session"
        create_session.assert_not_called()
