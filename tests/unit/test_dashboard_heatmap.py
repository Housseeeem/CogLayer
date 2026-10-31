"""Unit tests for the Performance Heatmap helpers in the CogLayer dashboard.

Tests cover build_heatmap_data (pure, no Streamlit/Altair dependency) and
create_heatmap (Altair chart construction).  No existing tests are modified.

Requirements: Layer C Dashboard - Performance Heatmap
"""

from __future__ import annotations

from typing import Any

from coglayer.ui.dashboard import build_heatmap_data, create_heatmap

# ---------------------------------------------------------------------------
# build_heatmap_data - pure helper
# ---------------------------------------------------------------------------


def test_build_heatmap_data_empty_history() -> None:
    """Empty evidence list returns empty dimensions, session labels, and rows.

    Hand-derived: no input -> no output; no exception raised.
    """
    dims, sessions, rows = build_heatmap_data([])
    assert dims == []
    assert sessions == []
    assert rows == []


def test_build_heatmap_data_entries_without_session_id_are_ignored() -> None:
    """Entries missing session_id or with empty session_id are silently dropped.

    Hand-derived:
      - entry A: session_id missing entirely -> ignored.
      - entry B: session_id="" -> ignored.
      - entry C: session_id="s1", dimension="working_memory", outcome=0.7 -> included.
    Result: exactly 1 valid row, 1 session, 1 dimension.
    """
    history = [
        {
            "dimension": "response_inhibition",
            "outcome": 0.8,
            "timestamp": "2026-10-01T09:00:00Z",
            "task_id": "go_no_go",
        },
        {
            "session_id": "",
            "dimension": "response_inhibition",
            "outcome": 0.75,
            "timestamp": "2026-10-01T09:01:00Z",
            "task_id": "go_no_go",
        },
        {
            "session_id": "s1",
            "dimension": "working_memory",
            "outcome": 0.7,
            "timestamp": "2026-10-01T10:00:00Z",
            "task_id": "n_back",
        },
    ]
    dims, sessions, rows = build_heatmap_data(history)
    assert dims == ["working_memory"]
    assert sessions == ["1"]
    assert len(rows) == 1
    assert rows[0]["dimension"] == "working_memory"
    assert rows[0]["session_label"] == "1"
    assert abs(rows[0]["mean_outcome"] - 0.7) < 1e-9


def test_build_heatmap_data_entries_without_outcome_are_ignored() -> None:
    """Entries with missing or non-numeric outcome are silently dropped.

    Hand-derived:
      - entry A: no 'outcome' key -> ignored.
      - entry B: outcome=None -> ignored.
      - entry C: outcome="invalid" -> ignored.
      - entry D: valid session_id="s1", dimension="focus", outcome=0.6 -> kept.
    Result: 1 row, mean_outcome=0.6.
    """
    history: list[dict[str, Any]] = [
        {
            "session_id": "s1",
            "dimension": "focus",
            "timestamp": "2026-10-01T09:00:00Z",
            "task_id": "t1",
        },
        {
            "session_id": "s1",
            "dimension": "focus",
            "outcome": None,
            "timestamp": "2026-10-01T09:01:00Z",
            "task_id": "t1",
        },
        {
            "session_id": "s1",
            "dimension": "focus",
            "outcome": "invalid",
            "timestamp": "2026-10-01T09:02:00Z",
            "task_id": "t1",
        },
        {
            "session_id": "s1",
            "dimension": "focus",
            "outcome": 0.6,
            "timestamp": "2026-10-01T09:03:00Z",
            "task_id": "t1",
        },
    ]
    dims, sessions, rows = build_heatmap_data(history)
    assert dims == ["focus"]
    assert sessions == ["1"]
    assert len(rows) == 1
    assert abs(rows[0]["mean_outcome"] - 0.6) < 1e-9


def test_build_heatmap_data_multiple_tasks_same_session_averaged() -> None:
    """Multiple tasks for the same dimension in the same session are averaged.

    Hand-derived:
      - session "s1", dimension "response_inhibition":
        task A outcome=0.80, task B outcome=0.60.
        Expected mean = (0.80 + 0.60) / 2 = 0.70.
      - session "s1", dimension "working_memory":
        single task outcome=0.50.
        Expected mean = 0.50.
    Result: 1 session label, 2 dimensions, 2 rows.
    """
    history = [
        {
            "session_id": "s1",
            "dimension": "response_inhibition",
            "outcome": 0.80,
            "timestamp": "2026-10-01T09:00:00Z",
            "task_id": "go_no_go_a",
        },
        {
            "session_id": "s1",
            "dimension": "response_inhibition",
            "outcome": 0.60,
            "timestamp": "2026-10-01T09:05:00Z",
            "task_id": "go_no_go_b",
        },
        {
            "session_id": "s1",
            "dimension": "working_memory",
            "outcome": 0.50,
            "timestamp": "2026-10-01T09:10:00Z",
            "task_id": "n_back",
        },
    ]
    dims, sessions, rows = build_heatmap_data(history)

    assert dims == ["response_inhibition", "working_memory"]  # alphabetical
    assert sessions == ["1"]
    assert len(rows) == 2

    ri_row = next(r for r in rows if r["dimension"] == "response_inhibition")
    wm_row = next(r for r in rows if r["dimension"] == "working_memory")

    assert abs(ri_row["mean_outcome"] - 0.70) < 1e-9
    assert ri_row["session_label"] == "1"

    assert abs(wm_row["mean_outcome"] - 0.50) < 1e-9
    assert wm_row["session_label"] == "1"


def test_build_heatmap_data_single_session() -> None:
    """Single session produces exactly one session label '1'.

    Hand-derived:
      - 2 dimensions, 1 session each.
      - session_labels == ["1"].
      - dimensions are alphabetically sorted.
      - 2 rows total, one per dimension.
    """
    history = [
        {
            "session_id": "abc",
            "dimension": "sustained_attention",
            "outcome": 0.72,
            "timestamp": "2026-10-05T11:00:00Z",
            "task_id": "perception",
        },
        {
            "session_id": "abc",
            "dimension": "executive_control",
            "outcome": 0.65,
            "timestamp": "2026-10-05T11:10:00Z",
            "task_id": "stroop",
        },
    ]
    dims, sessions, rows = build_heatmap_data(history)

    assert dims == ["executive_control", "sustained_attention"]  # alphabetical
    assert sessions == ["1"]
    assert len(rows) == 2


def test_build_heatmap_data_chronological_session_ordering() -> None:
    """Sessions are numbered in chronological order by the oldest timestamp in each session.

    Hand-derived:
      - session "sB" has first seen timestamp 2026-10-02T08:00:00Z.
      - session "sA" has first seen timestamp 2026-10-01T08:00:00Z (earlier).
      - Expected session_labels order: sA -> "1", sB -> "2".
    """
    history = [
        {
            "session_id": "sB",
            "dimension": "working_memory",
            "outcome": 0.55,
            "timestamp": "2026-10-02T08:00:00Z",
            "task_id": "n_back",
        },
        {
            "session_id": "sA",
            "dimension": "working_memory",
            "outcome": 0.45,
            "timestamp": "2026-10-01T08:00:00Z",
            "task_id": "n_back",
        },
    ]
    _dims, sessions, rows = build_heatmap_data(history)

    assert sessions == ["1", "2"]

    sa_row = next(r for r in rows if r["session_label"] == "1")
    sb_row = next(r for r in rows if r["session_label"] == "2")

    # sA (oldest) -> label "1", outcome 0.45
    assert abs(sa_row["mean_outcome"] - 0.45) < 1e-9
    # sB (newer) -> label "2", outcome 0.55
    assert abs(sb_row["mean_outcome"] - 0.55) < 1e-9


def test_build_heatmap_data_multi_session_multi_dimension() -> None:
    """Multiple sessions and dimensions produce correct cell averages and labels.

    Hand-derived:
      - 3 sessions (s1 oldest, s2 middle, s3 newest), 2 dimensions.
      - dimension "response_inhibition": present in s1 (0.6) and s3 (0.9), absent in s2.
      - dimension "working_memory": present in all 3 sessions: s1(0.5), s2(0.7), s3(0.8).
      - session_labels = ["1", "2", "3"].
      - rows for response_inhibition: labels "1" and "3" only (2 rows).
      - rows for working_memory: labels "1", "2", "3" (3 rows).
      - Total rows = 5.
    """
    history = [
        {
            "session_id": "s1",
            "dimension": "response_inhibition",
            "outcome": 0.6,
            "timestamp": "2026-10-01T09:00:00Z",
            "task_id": "go_no_go",
        },
        {
            "session_id": "s1",
            "dimension": "working_memory",
            "outcome": 0.5,
            "timestamp": "2026-10-01T09:05:00Z",
            "task_id": "n_back",
        },
        {
            "session_id": "s2",
            "dimension": "working_memory",
            "outcome": 0.7,
            "timestamp": "2026-10-08T10:00:00Z",
            "task_id": "n_back",
        },
        {
            "session_id": "s3",
            "dimension": "response_inhibition",
            "outcome": 0.9,
            "timestamp": "2026-10-15T09:00:00Z",
            "task_id": "go_no_go",
        },
        {
            "session_id": "s3",
            "dimension": "working_memory",
            "outcome": 0.8,
            "timestamp": "2026-10-15T09:05:00Z",
            "task_id": "n_back",
        },
    ]
    dims, sessions, rows = build_heatmap_data(history)

    assert dims == ["response_inhibition", "working_memory"]  # alphabetical
    assert sessions == ["1", "2", "3"]
    assert len(rows) == 5

    def _cell(dim: str, lbl: str) -> dict[str, Any] | None:
        for r in rows:
            if r["dimension"] == dim and r["session_label"] == lbl:
                return r
        return None

    cell_ri_1 = _cell("response_inhibition", "1")
    assert cell_ri_1 is not None
    assert abs(float(cell_ri_1["mean_outcome"]) - 0.6) < 1e-9

    assert _cell("response_inhibition", "2") is None  # absent

    cell_ri_3 = _cell("response_inhibition", "3")
    assert cell_ri_3 is not None
    assert abs(float(cell_ri_3["mean_outcome"]) - 0.9) < 1e-9

    cell_wm_1 = _cell("working_memory", "1")
    assert cell_wm_1 is not None
    assert abs(float(cell_wm_1["mean_outcome"]) - 0.5) < 1e-9

    cell_wm_2 = _cell("working_memory", "2")
    assert cell_wm_2 is not None
    assert abs(float(cell_wm_2["mean_outcome"]) - 0.7) < 1e-9

    cell_wm_3 = _cell("working_memory", "3")
    assert cell_wm_3 is not None
    assert abs(float(cell_wm_3["mean_outcome"]) - 0.8) < 1e-9


# ---------------------------------------------------------------------------
# create_heatmap - Altair chart construction
# ---------------------------------------------------------------------------


def test_create_heatmap_empty_returns_chart_object() -> None:
    """create_heatmap with empty rows returns a valid (non-None) Altair chart object.

    Hand-derived: the chart is used in the UI, so it must never be None even when
    there is no data.
    """
    chart = create_heatmap([], [], [])
    assert chart is not None


def test_create_heatmap_with_data_returns_chart_object() -> None:
    """create_heatmap with valid data returns a non-None Altair chart.

    Hand-derived: 2 dimensions x 2 sessions -> chart object is created.
    """
    dims = ["response_inhibition", "working_memory"]
    sessions = ["1", "2"]
    rows = [
        {
            "dimension": "response_inhibition",
            "session_label": "1",
            "mean_outcome": 0.65,
            "task_ids": ["go_no_go"],
        },
        {
            "dimension": "response_inhibition",
            "session_label": "2",
            "mean_outcome": 0.75,
            "task_ids": ["go_no_go"],
        },
        {
            "dimension": "working_memory",
            "session_label": "1",
            "mean_outcome": 0.50,
            "task_ids": ["n_back"],
        },
        {
            "dimension": "working_memory",
            "session_label": "2",
            "mean_outcome": 0.70,
            "task_ids": ["n_back"],
        },
    ]
    chart = create_heatmap(dims, sessions, rows)
    assert chart is not None


def test_create_heatmap_spec_color_domain_fixed() -> None:
    """Heatmap color scale domain is fixed at [0.0, 1.0] regardless of data values.

    Hand-derived: even if all outcomes are 0.2-0.4, the domain must stay [0, 1].
    """
    dims = ["focus"]
    sessions = ["1"]
    rows = [
        {
            "dimension": "focus",
            "session_label": "1",
            "mean_outcome": 0.30,
            "task_ids": ["perception"],
        },
    ]
    chart = create_heatmap(dims, sessions, rows)
    spec = chart.to_dict()

    # Traverse into the layer spec to find the color encoding
    layers = spec.get("layer", [spec])
    color_domain: list[float] | None = None
    for layer in layers:
        enc = layer.get("encoding", {})
        color_enc = enc.get("color", {})
        scale = color_enc.get("scale", {})
        if "domain" in scale:
            color_domain = scale["domain"]
            break

    assert color_domain == [0.0, 1.0], f"Expected [0.0, 1.0], got {color_domain}"


def test_create_heatmap_spec_has_text_layer() -> None:
    """Heatmap spec includes a text layer that displays cell values.

    Hand-derived: the chart uses alt.layer(rects, text_layer), so the spec
    must contain a layer with mark type 'text'.
    """
    dims = ["working_memory"]
    sessions = ["1"]
    rows = [
        {
            "dimension": "working_memory",
            "session_label": "1",
            "mean_outcome": 0.72,
            "task_ids": [],
        },
    ]
    chart = create_heatmap(dims, sessions, rows)
    spec = chart.to_dict()

    layers = spec.get("layer", [])
    mark_types = []
    for layer in layers:
        mark = layer.get("mark", {})
        if isinstance(mark, dict):
            mark_types.append(mark.get("type"))
        elif isinstance(mark, str):
            mark_types.append(mark)

    assert "text" in mark_types, f"No text mark found in layers: {mark_types}"


def test_create_heatmap_spec_tooltip_fields() -> None:
    """Heatmap tooltip includes Dimension, Session, Mean Outcome, and Tasks.

    Hand-derived: tooltip is declared on the rect mark layer.
    """
    dims = ["response_inhibition"]
    sessions = ["1"]
    rows = [
        {
            "dimension": "response_inhibition",
            "session_label": "1",
            "mean_outcome": 0.80,
            "task_ids": ["go_no_go"],
        },
    ]
    chart = create_heatmap(dims, sessions, rows)
    spec = chart.to_dict()

    layers = spec.get("layer", [spec])
    tooltip_fields: set[str] = set()
    for layer in layers:
        enc = layer.get("encoding", {})
        for tt in enc.get("tooltip", []):
            tooltip_fields.add(tt.get("field", ""))

    assert "Dimension" in tooltip_fields, f"Missing Dimension in tooltip: {tooltip_fields}"
    assert "Session" in tooltip_fields, f"Missing Session in tooltip: {tooltip_fields}"
    assert "Mean Outcome" in tooltip_fields, f"Missing Mean Outcome in tooltip: {tooltip_fields}"
    assert "Tasks" in tooltip_fields, f"Missing Tasks in tooltip: {tooltip_fields}"
