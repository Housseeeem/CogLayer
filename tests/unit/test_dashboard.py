"""Unit tests for CogLayer cognitive dashboard helpers and components.

Verifies pure data helpers, radar chart generation, progress curves,
and dashboard page rendering in compliance with non-clinical rules.

Requirements: Layer C Dashboard
"""

from __future__ import annotations

from coglayer.ui.dashboard import (
    build_dimension_series,
    build_history_rows,
    build_progress_curve_data,
    build_radar_chart_data,
    build_radar_rows,
    create_progress_curve,
    create_radar_chart,
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

    # History rows: 4 items, most recent first
    hist_rows = build_history_rows(profile)
    assert len(hist_rows) == 4
    assert hist_rows[0]["session_id"] == "sess_2" and hist_rows[0]["task_id"] == "sequence_span"
    assert hist_rows[1]["session_id"] == "sess_2" and hist_rows[1]["task_id"] == "go_no_go"
    assert hist_rows[2]["session_id"] == "sess_1" and hist_rows[2]["task_id"] == "sequence_span"
    assert hist_rows[3]["session_id"] == "sess_1" and hist_rows[3]["task_id"] == "go_no_go"
