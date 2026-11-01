"""Unit tests for CogLayer cognitive dashboard helpers and components.

Verifies pure data helpers, radar chart generation, progress curves,
and dashboard page rendering in compliance with non-clinical rules.

Requirements: Layer C Dashboard
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from coglayer.ui.dashboard import (
    build_dimension_series,
    build_history_rows,
    build_interval_chart_data,
    build_progress_curve_data,
    build_radar_chart_data,
    build_radar_rows,
    create_interval_chart,
    create_progress_curve,
    create_radar_chart,
    select_overview_chart,
)
from coglayer.ui.page_views.dashboard import (
    render_dashboard_page,
    render_profile_dashboard_page,
)


def test_build_radar_rows_fixed_order() -> None:
    """Radar rows are built in fixed alphabetical order with lower, mean, upper, n_sessions.

    Hand-derived:
      - 2 dimensions provided in reverse alphabetical order:
        'sequential_visual_memory' (mean=0.65, lower=0.45, upper=0.85, n_evidence=2)
        'response_inhibition' (mean=0.75, lower=0.55, upper=0.95, n_evidence=3)
      - Fixed order must be alphabetical:
        Row 0: response_inhibition, lower=0.55, mean=0.75, upper=0.95, n_sessions=3
        Row 1: sequential_visual_memory, lower=0.45, mean=0.65, upper=0.85, n_sessions=2
    """
    profile = {
        "dimensions": {
            "sequential_visual_memory": {
                "dimension": "sequential_visual_memory",
                "mean": 0.65,
                "lower": 0.45,
                "upper": 0.85,
                "n_evidence": 2,
            },
            "response_inhibition": {
                "dimension": "response_inhibition",
                "mean": 0.75,
                "lower": 0.55,
                "upper": 0.95,
                "n_evidence": 3,
            },
        }
    }
    rows = build_radar_rows(profile)
    assert len(rows) == 2
    assert rows[0] == {
        "dimension": "response_inhibition",
        "lower": 0.55,
        "mean": 0.75,
        "upper": 0.95,
        "n_sessions": 3,
    }
    assert rows[1] == {
        "dimension": "sequential_visual_memory",
        "lower": 0.45,
        "mean": 0.65,
        "upper": 0.85,
        "n_sessions": 2,
    }


def test_build_dimension_series_chronological() -> None:
    """Per-dimension series contains outcomes in chronological order.

    An outcome is the primary metric of that task in that session.
    Hand-derived:
      - 'response_inhibition' has evidence at 10:00 (outcome 0.8) and 11:00 (outcome 1.0)
        -> 2-point series: [0.8, 1.0]
      - 'sequential_visual_memory' has evidence at 10:05 (outcome 0.6)
        -> 1-point series: [0.6]
    """
    profile = {
        "evidence_history": [
            {
                "dimension": "response_inhibition",
                "outcome": 0.8,
                "timestamp": "2026-10-17T10:00:00Z",
                "session_id": "s1",
                "task_id": "go_no_go",
            },
            {
                "dimension": "sequential_visual_memory",
                "outcome": 0.6,
                "timestamp": "2026-10-17T10:05:00Z",
                "session_id": "s1",
                "task_id": "sequence_span",
            },
            {
                "dimension": "response_inhibition",
                "outcome": 1.0,
                "timestamp": "2026-10-17T11:00:00Z",
                "session_id": "s2",
                "task_id": "go_no_go",
            },
        ]
    }
    series = build_dimension_series(profile)
    assert series["response_inhibition"] == [0.8, 1.0]
    assert series["sequential_visual_memory"] == [0.6]


def test_build_history_rows_most_recent_first() -> None:
    """History rows contain session_id, task_id, dimension, outcome, timestamp (most recent first).

    Hand-derived:
      - 3 evidence items at 10:00, 10:05, 11:00.
      - Most recent first order:
        Row 0: s2, go_no_go, response_inhibition, 1.0, 2026-10-17T11:00:00Z
        Row 1: s1, sequence_span, sequential_visual_memory, 0.6, 2026-10-17T10:05:00Z
        Row 2: s1, go_no_go, response_inhibition, 0.8, 2026-10-17T10:00:00Z
    """
    profile = {
        "evidence_history": [
            {
                "dimension": "response_inhibition",
                "outcome": 0.8,
                "timestamp": "2026-10-17T10:00:00Z",
                "session_id": "s1",
                "task_id": "go_no_go",
            },
            {
                "dimension": "sequential_visual_memory",
                "outcome": 0.6,
                "timestamp": "2026-10-17T10:05:00Z",
                "session_id": "s1",
                "task_id": "sequence_span",
            },
            {
                "dimension": "response_inhibition",
                "outcome": 1.0,
                "timestamp": "2026-10-17T11:00:00Z",
                "session_id": "s2",
                "task_id": "go_no_go",
            },
        ]
    }
    rows = build_history_rows(profile)
    assert len(rows) == 3
    assert rows[0] == {
        "session_id": "s2",
        "task_id": "go_no_go",
        "dimension": "response_inhibition",
        "outcome": 1.0,
        "timestamp": "2026-10-17T11:00:00Z",
    }
    assert rows[1] == {
        "session_id": "s1",
        "task_id": "sequence_span",
        "dimension": "sequential_visual_memory",
        "outcome": 0.6,
        "timestamp": "2026-10-17T10:05:00Z",
    }
    assert rows[2] == {
        "session_id": "s1",
        "task_id": "go_no_go",
        "dimension": "response_inhibition",
        "outcome": 0.8,
        "timestamp": "2026-10-17T10:00:00Z",
    }


def test_empty_profile_returns_empty_outputs() -> None:
    """Empty profile gives empty outputs, never an exception.

    Hand-derived:
      - empty dict {} -> radar_rows == [], series == {}, history_rows == []
    """
    empty_profile: dict[str, object] = {}
    assert build_radar_rows(empty_profile) == []
    assert build_dimension_series(empty_profile) == {}
    assert build_history_rows(empty_profile) == []


def test_radar_chart_layers_and_no_sorting() -> None:
    """Radar chart function returns chart object and preserves exact axis order across 3 layers.

    Hand-derived:
      - radar_rows passed in explicit non-alphabetical order:
        ["spatial_attention", "working_memory", "executive_control"]
      - build_radar_chart_data returns data for 3 layers: 'lower', 'mean', 'upper'
      - Order of dimensions in each layer must strictly match input:
        ["spatial_attention", "working_memory", "executive_control"] (no sorting!)
      - Hand-derived values:
        lower: [0.30, 0.40, 0.50]
        mean:  [0.50, 0.60, 0.70]
        upper: [0.70, 0.80, 0.90]
      - create_radar_chart returns a valid Altair chart object.
    """
    radar_rows = [
        {
            "dimension": "spatial_attention",
            "lower": 0.30,
            "mean": 0.50,
            "upper": 0.70,
            "n_sessions": 4,
        },
        {
            "dimension": "working_memory",
            "lower": 0.40,
            "mean": 0.60,
            "upper": 0.80,
            "n_sessions": 2,
        },
        {
            "dimension": "executive_control",
            "lower": 0.50,
            "mean": 0.70,
            "upper": 0.90,
            "n_sessions": 1,
        },
    ]

    chart_data = build_radar_chart_data(radar_rows)
    assert set(chart_data.keys()) == {"lower", "mean", "upper"}

    for layer_name in ("lower", "mean", "upper"):
        points = chart_data[layer_name]
        # First N points correspond to dimensions in input order
        dims = [p["dimension"] for p in points[:3]]
        assert dims == ["spatial_attention", "working_memory", "executive_control"]

    assert [p["value"] for p in chart_data["lower"][:3]] == [0.30, 0.40, 0.50]
    assert [p["value"] for p in chart_data["mean"][:3]] == [0.50, 0.60, 0.70]
    assert [p["value"] for p in chart_data["upper"][:3]] == [0.70, 0.80, 0.90]

    # Verify chart object creation
    chart = create_radar_chart(radar_rows)
    assert chart is not None


def test_progress_curve_and_history_data() -> None:
    """Progress curve data has 1 point per session per dimension with y in [0, 1].

    Hand-derived:
      - 2 sessions, 2 tasks/dimensions per session:
        Session 1: response_inhibition = 0.85, sequential_visual_memory = 0.50
        Session 2: response_inhibition = 0.95, sequential_visual_memory = 0.70
      - Progress rows for response_inhibition:
        [{session_index: 1, outcome: 0.85}, {session_index: 2, outcome: 0.95}]
      - Progress rows for sequential_visual_memory:
        [{session_index: 1, outcome: 0.50}, {session_index: 2, outcome: 0.70}]
      - All outcome values in [0, 1].
      - History rows are sorted most recent first (session 2 before session 1).
    """
    profile = {
        "evidence_history": [
            {
                "dimension": "response_inhibition",
                "outcome": 0.85,
                "timestamp": "2026-10-17T09:00:00Z",
                "session_id": "sess_1",
                "task_id": "go_no_go",
            },
            {
                "dimension": "sequential_visual_memory",
                "outcome": 0.50,
                "timestamp": "2026-10-17T09:05:00Z",
                "session_id": "sess_1",
                "task_id": "sequence_span",
            },
            {
                "dimension": "response_inhibition",
                "outcome": 0.95,
                "timestamp": "2026-10-17T14:00:00Z",
                "session_id": "sess_2",
                "task_id": "go_no_go",
            },
            {
                "dimension": "sequential_visual_memory",
                "outcome": 0.70,
                "timestamp": "2026-10-17T14:05:00Z",
                "session_id": "sess_2",
                "task_id": "sequence_span",
            },
        ]
    }

    progress_rows = build_progress_curve_data(profile)
    assert len(progress_rows) == 4

    ri_points = [r for r in progress_rows if r["dimension"] == "response_inhibition"]
    svm_points = [r for r in progress_rows if r["dimension"] == "sequential_visual_memory"]

    assert len(ri_points) == 2
    assert ri_points[0]["session_index"] == 1 and ri_points[0]["outcome"] == 0.85
    assert ri_points[1]["session_index"] == 2 and ri_points[1]["outcome"] == 0.95

    assert len(svm_points) == 2
    assert svm_points[0]["session_index"] == 1 and svm_points[0]["outcome"] == 0.50
    assert svm_points[1]["session_index"] == 2 and svm_points[1]["outcome"] == 0.70

    for pt in progress_rows:
        assert 0.0 <= pt["outcome"] <= 1.0

    # Chart creation
    chart = create_progress_curve(progress_rows)
    assert chart is not None
    projected_chart = create_progress_curve(
        progress_rows,
        [
            {
                "dimension": "response_inhibition",
                "session_index": 3,
                "mean": 0.9,
                "lower": 0.8,
                "upper": 1.0,
            }
        ],
    )
    assert "Possible trajectory (uncertain)" in projected_chart.to_json()

    # History rows: 4 items, most recent first
    hist_rows = build_history_rows(profile)
    assert len(hist_rows) == 4
    assert hist_rows[0]["session_id"] == "sess_2" and hist_rows[0]["task_id"] == "sequence_span"
    assert hist_rows[1]["session_id"] == "sess_2" and hist_rows[1]["task_id"] == "go_no_go"
    assert hist_rows[2]["session_id"] == "sess_1" and hist_rows[2]["task_id"] == "sequence_span"
    assert hist_rows[3]["session_id"] == "sess_1" and hist_rows[3]["task_id"] == "go_no_go"


@patch("coglayer.ui.page_views.dashboard.httpx.get")
@patch("coglayer.ui.page_views.dashboard.st")
def test_render_dashboard_page_empty_state(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """Dashboard displays friendly empty state when user has no completed sessions.

    Hand-derived:
      - Empty dimensions in profile JSON.
      - Displays friendly info prompt telling user to complete first session.
      - Contains fixed disclaimer: 'Based on the tasks completed so far
        — not a clinical assessment.'
    """
    mock_get.return_value = MagicMock(
        status_code=200, json=lambda: {"dimensions": {}, "evidence_history": []}
    )
    mock_st.button.return_value = False

    render_dashboard_page("http://testserver", "user_1")

    assert mock_st.info.called
    info_text = mock_st.info.call_args[0][0]
    assert "complete" in info_text.lower() and "first session" in info_text.lower()

    # Disclaimer check
    caption_calls = [call[0][0] for call in mock_st.caption.call_args_list if call[0]]
    disclaimer_found = any(
        "Based on the tasks completed so far — not a clinical assessment." in text
        for text in caption_calls
    )
    assert disclaimer_found


@patch("coglayer.ui.page_views.dashboard.httpx.get")
@patch("coglayer.ui.page_views.dashboard.st")
def test_render_dashboard_page_api_error(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """Dashboard handles API connection error gracefully with readable error and no stack trace.

    Hand-derived:
      - Connection exception raised by httpx.get.
      - Displays readable st.error message without raw traceback.
    """
    mock_get.side_effect = Exception("Connection refused by testserver")

    render_dashboard_page("http://testserver", "user_1")

    assert mock_st.error.called
    error_msg = mock_st.error.call_args[0][0]
    assert "Error connecting to assessment API" in error_msg
    assert "Traceback" not in error_msg


@patch("coglayer.ui.page_views.dashboard.httpx.get")
@patch("coglayer.ui.page_views.dashboard.st")
def test_render_dashboard_page_single_session(mock_st: MagicMock, mock_get: MagicMock) -> None:
    """Dashboard with 1 session renders radar and progress curve with note on trends.

    Hand-derived:
      - Profile with 1 completed session for 2 dimensions.
      - Radar and progress curve rendered via st.altair_chart.
      - Displays note explaining trends require at least two sessions.
    """
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "dimensions": {
                "response_inhibition": {
                    "dimension": "response_inhibition",
                    "lower": 0.5,
                    "mean": 0.7,
                    "upper": 0.9,
                    "n_evidence": 1,
                },
                "sequential_visual_memory": {
                    "dimension": "sequential_visual_memory",
                    "lower": 0.4,
                    "mean": 0.6,
                    "upper": 0.8,
                    "n_evidence": 1,
                },
            },
            "evidence_history": [
                {
                    "dimension": "response_inhibition",
                    "outcome": 0.7,
                    "timestamp": "2026-10-17T10:00:00Z",
                    "session_id": "s1",
                    "task_id": "go_no_go",
                },
                {
                    "dimension": "sequential_visual_memory",
                    "outcome": 0.6,
                    "timestamp": "2026-10-17T10:05:00Z",
                    "session_id": "s1",
                    "task_id": "sequence_span",
                },
            ],
        },
    )

    render_dashboard_page("http://testserver", "user_1")

    assert mock_st.altair_chart.called
    # Check note that trends need at least two sessions
    info_calls = [call[0][0] for call in mock_st.info.call_args_list if call[0]]
    trend_note_found = any(
        "trends" in str(text).lower() and "two" in str(text).lower() for text in info_calls
    )
    assert trend_note_found


@patch("coglayer.ui.page_views.dashboard.httpx.get")
@patch("coglayer.ui.page_views.dashboard.st")
def test_render_dashboard_page_multi_session_and_non_clinical(
    mock_st: MagicMock, mock_get: MagicMock
) -> None:
    """Dashboard page contains disclaimer, progress caption, and no forbidden words.

    Hand-derived:
      - 2 sessions, multi-dimension profile.
      - Fixed disclaimer: 'Based on the tasks completed so far — not a clinical assessment.'
      - Progress curve caption mentions practice or strategy, not necessarily gain in ability.
      - Forbidden words (diagnosis, disorder, deficit, impairment, IQ, patient) must not appear.
    """
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "dimensions": {
                "response_inhibition": {
                    "dimension": "response_inhibition",
                    "lower": 0.6,
                    "mean": 0.8,
                    "upper": 0.95,
                    "n_evidence": 2,
                },
                "sequential_visual_memory": {
                    "dimension": "sequential_visual_memory",
                    "lower": 0.5,
                    "mean": 0.7,
                    "upper": 0.85,
                    "n_evidence": 2,
                },
            },
            "evidence_history": [
                {
                    "dimension": "response_inhibition",
                    "outcome": 0.75,
                    "timestamp": "2026-10-17T10:00:00Z",
                    "session_id": "s1",
                    "task_id": "go_no_go",
                },
                {
                    "dimension": "sequential_visual_memory",
                    "outcome": 0.65,
                    "timestamp": "2026-10-17T10:05:00Z",
                    "session_id": "s1",
                    "task_id": "sequence_span",
                },
                {
                    "dimension": "response_inhibition",
                    "outcome": 0.85,
                    "timestamp": "2026-10-17T12:00:00Z",
                    "session_id": "s2",
                    "task_id": "go_no_go",
                },
                {
                    "dimension": "sequential_visual_memory",
                    "outcome": 0.75,
                    "timestamp": "2026-10-17T12:05:00Z",
                    "session_id": "s2",
                    "task_id": "sequence_span",
                },
            ],
        },
    )

    render_dashboard_page("http://testserver", "user_1")

    # Collect all text strings rendered by Streamlit
    all_rendered_text: list[str] = []
    for method in (
        "header",
        "subheader",
        "caption",
        "info",
        "warning",
        "error",
        "markdown",
        "write",
    ):
        mock_fn = getattr(mock_st, method)
        for call in mock_fn.call_args_list:
            if call[0]:
                all_rendered_text.append(str(call[0][0]))

    combined_text = " ".join(all_rendered_text)

    # 1. Fixed disclaimer
    assert "Based on the tasks completed so far — not a clinical assessment." in combined_text

    # 2. Progress curve caption mentions practice or strategy
    assert "practice" in combined_text.lower() or "strategy" in combined_text.lower()

    # 3. Non-clinical compliance: zero forbidden words
    import re

    forbidden_words = ["diagnosis", "disorder", "deficit", "impairment", "iq", "patient"]
    for word in forbidden_words:
        matches = re.findall(rf"\b{word}\b", combined_text, flags=re.IGNORECASE)
        assert len(matches) == 0, f"Forbidden word '{word}' found in rendered UI text: {matches}"


def test_chart_selection_and_interval_chart() -> None:
    """Selector returns interval chart for < 3 dimensions and radar for >= 3 dimensions.

    Hand-derived:
      - 2 dimensions input in alphabetical order:
        'response_inhibition' (mean=0.857, lower=0.62, upper=0.98, n_sessions=2)
        'sequential_visual_memory' (mean=0.650, lower=0.45, upper=0.85, n_sessions=1)
      - With 2 dimensions (< 3), selector returns chart type 'interval'.
      - In interval chart data, mean 0.857 with bounds 0.62 and 0.98 stays unchanged:
        Row 0: dimension='response_inhibition', label='Response Inhibition (2 sessions)',
               mean=0.857, lower=0.62, upper=0.98, n_sessions=2
        Row 1: dimension='sequential_visual_memory', label='Sequential Visual Memory (1 session)',
               mean=0.650, lower=0.45, upper=0.85, n_sessions=1
      - Interval chart Altair object is created.
      - With 3 dimensions (adding 'spatial_attention'), selector returns 'radar' chart.
    """
    two_dim_rows = [
        {
            "dimension": "response_inhibition",
            "lower": 0.62,
            "mean": 0.857,
            "upper": 0.98,
            "n_sessions": 2,
        },
        {
            "dimension": "sequential_visual_memory",
            "lower": 0.45,
            "mean": 0.650,
            "upper": 0.85,
            "n_sessions": 1,
        },
    ]

    # Test 2 dimensions -> interval chart
    chart_type, chart = select_overview_chart(two_dim_rows)
    assert chart_type == "interval"
    assert chart is not None
    assert create_interval_chart(two_dim_rows) is not None

    interval_data = build_interval_chart_data(two_dim_rows)
    assert len(interval_data) == 2
    assert interval_data[0] == {
        "dimension": "response_inhibition",
        "label": "Response Inhibition (2 sessions)",
        "lower": 0.62,
        "mean": 0.857,
        "upper": 0.98,
        "n_sessions": 2,
    }
    assert interval_data[1] == {
        "dimension": "sequential_visual_memory",
        "label": "Sequential Visual Memory (1 session)",
        "lower": 0.45,
        "mean": 0.650,
        "upper": 0.85,
        "n_sessions": 1,
    }

    # Test 3 dimensions -> radar chart
    three_dim_rows = [
        *two_dim_rows,
        {
            "dimension": "spatial_attention",
            "lower": 0.30,
            "mean": 0.50,
            "upper": 0.70,
            "n_sessions": 4,
        },
    ]
    chart_type_3, chart_3 = select_overview_chart(three_dim_rows)
    assert chart_type_3 == "radar"
    assert chart_3 is not None


@patch("coglayer.ui.page_views.dashboard.httpx.get")
@patch("coglayer.ui.page_views.dashboard.st")
def test_render_dashboard_page_fewer_than_three_dimensions_caption(
    mock_st: MagicMock, mock_get: MagicMock
) -> None:
    """When < 3 dimensions, dashboard displays caption that radar appears at >= 3 dimensions.

    Hand-derived:
      - 2 dimensions in profile.
      - Caption must state that the radar chart appears once at least 3 dimensions are profiled.
    """
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "dimensions": {
                "response_inhibition": {
                    "dimension": "response_inhibition",
                    "lower": 0.62,
                    "mean": 0.857,
                    "upper": 0.98,
                    "n_evidence": 2,
                },
                "sequential_visual_memory": {
                    "dimension": "sequential_visual_memory",
                    "lower": 0.45,
                    "mean": 0.65,
                    "upper": 0.85,
                    "n_evidence": 1,
                },
            },
            "evidence_history": [],
        },
    )

    render_dashboard_page("http://testserver", "user_1")

    caption_calls = [call[0][0] for call in mock_st.caption.call_args_list if call[0]]
    radar_threshold_caption = any(
        "radar" in text.lower() and "3 dimensions" in text.lower() for text in caption_calls
    )
    assert radar_threshold_caption, f"Caption about 3 dimensions not found in: {caption_calls}"


def test_progress_curve_chart_spec() -> None:
    """Progress curve Altair chart spec satisfies visual readability requirements.

    Hand-derived:
      - Y-scale domain must be [0.0, 1.05] so 1.0 outcomes are not clipped.
      - X-axis session labels must be horizontal (labelAngle == 0) with integer ticks
        (tickMinStep == 1, format == 'd').
      - Distinct visual encodings per dimension: color and shape (or strokeDash).
      - Tooltip must include 'session_index', 'dimension', and 'outcome'.
    """
    rows = [
        {"dimension": "response_inhibition", "session_index": 1, "outcome": 0.85},
        {"dimension": "response_inhibition", "session_index": 2, "outcome": 1.00},
        {"dimension": "sequential_visual_memory", "session_index": 1, "outcome": 0.60},
        {"dimension": "sequential_visual_memory", "session_index": 2, "outcome": 0.75},
    ]
    chart = create_progress_curve(rows)
    spec = chart.to_dict()
    encoding = spec["encoding"]

    # 1. Y scale domain [0, 1.05]
    assert encoding["y"]["scale"]["domain"] == [0.0, 1.05]

    # 2. X axis horizontal labels with integer ticks
    assert encoding["x"]["axis"]["labelAngle"] == 0
    assert encoding["x"]["axis"]["tickMinStep"] == 1
    assert encoding["x"]["axis"]["format"] == "d"

    # 3. Distinct encodings for dimension (color and shape/strokeDash)
    assert encoding["color"]["field"] == "dimension"
    assert "shape" in encoding or "strokeDash" in encoding
    if "shape" in encoding:
        assert encoding["shape"]["field"] == "dimension"
    if "strokeDash" in encoding:
        assert encoding["strokeDash"]["field"] == "dimension"

    # 4. Tooltip with session, dimension, and outcome
    tooltip_fields = [t["field"] for t in encoding["tooltip"]]
    assert "session_index" in tooltip_fields
    assert "dimension" in tooltip_fields
    assert "outcome" in tooltip_fields


@patch("coglayer.ui.page_views.dashboard.render_dashboard_page")
@patch("coglayer.ui.page_views.dashboard.render_profile_page")
@patch("coglayer.ui.page_views.dashboard.st")
def test_merged_profile_dashboard_reuses_existing_renderers(
    mock_st: MagicMock,
    mock_render_profile: MagicMock,
    mock_render_dashboard: MagicMock,
) -> None:
    """The merged page keeps one header and reuses profile plus dashboard renderers."""
    render_profile_dashboard_page("http://testserver", "user_1")

    mock_st.header.assert_called_once_with("Cognitive Profile & Dashboard")
    mock_render_profile.assert_called_once_with(
        "http://testserver",
        "user_1",
        heading=False,
    )
    mock_render_dashboard.assert_called_once_with(
        "http://testserver",
        "user_1",
        heading=False,
        show_empty_cta=False,
    )
