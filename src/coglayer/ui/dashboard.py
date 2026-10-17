"""Pure data helpers and chart generation for the CogLayer cognitive dashboard.

Provides pure functions to process profile JSON into radar rows,
per-dimension outcome series, and history rows, satisfying non-clinical rules.

Requirements: Layer C Dashboard
"""

from __future__ import annotations

import math
from typing import Any, cast

import altair as alt


def build_interval_chart_data(radar_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build interval chart data with one row per dimension in fixed order.

    Each row includes:
    - dimension: dimension identifier
    - label: formatted dimension name with session count, e.g. 'Response Inhibition (2 sessions)'
    - lower: lower bound of 90% credible interval in [0, 1]
    - mean: posterior mean in [0, 1]
    - upper: upper bound of 90% credible interval in [0, 1]
    - n_sessions: integer count of completed sessions
    """
    rows: list[dict[str, Any]] = []
    for row in radar_rows:
        dim_name = str(row.get("dimension", "")).replace("_", " ").title()
        n_sess = int(row.get("n_sessions", 0))
        unit = "session" if n_sess == 1 else "sessions"
        label = f"{dim_name} ({n_sess} {unit})"
        rows.append(
            {
                "dimension": str(row.get("dimension", "")),
                "label": label,
                "lower": float(row.get("lower", 0.0)),
                "mean": float(row.get("mean", 0.0)),
                "upper": float(row.get("upper", 0.0)),
                "n_sessions": n_sess,
            }
        )
    return rows


def create_interval_chart(radar_rows: list[dict[str, Any]]) -> alt.LayerChart | alt.Chart:
    """Create a horizontal interval chart with a point at the mean and a bar for the 90% interval.

    Used when fewer than 3 dimensions are profiled. Fixed dimension order is preserved.
    """
    if not radar_rows:
        empty = alt.Chart({"values": [{"text": "No data"}]}).mark_text(
            text="No cognitive dimensions recorded yet."
        )
        return cast(alt.Chart, empty)

    data = build_interval_chart_data(radar_rows)
    dim_order = [d["label"] for d in data]

    # Horizontal bar from lower to upper (90% credible interval)
    bars = (
        alt.Chart({"values": data})
        .mark_bar(height=8, color="#93c5fd", cornerRadius=4)
        .encode(
            y=alt.Y("label:N", title=None, sort=dim_order),
            x=alt.X(
                "lower:Q",
                scale=alt.Scale(domain=[0.0, 1.0]),
                axis=alt.Axis(format="%", title="Estimate (0 - 100%)"),
            ),
            x2="upper:Q",
        )
    )

    # Point at the mean
    points = (
        alt.Chart({"values": data})
        .mark_point(filled=True, size=70, color="#2563eb")
        .encode(
            y=alt.Y("label:N", title=None, sort=dim_order),
            x="mean:Q",
        )
    )

    combined = (
        alt.layer(bars, points)
        .properties(width=480, height=max(120, len(data) * 60))
        .configure_view(strokeWidth=0)
    )
    return cast(alt.LayerChart | alt.Chart, combined)


def select_overview_chart(
    radar_rows: list[dict[str, Any]],
) -> tuple[str, alt.LayerChart | alt.Chart]:
    """Select the overview chart type and Altair chart based on dimension count.

    If fewer than 3 dimensions, returns ('interval', interval_chart).
    If 3 or more dimensions, returns ('radar', radar_chart).
    """
    if len(radar_rows) < 3:
        return ("interval", create_interval_chart(radar_rows))
    return ("radar", create_radar_chart(radar_rows))


def build_radar_rows(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Build radar rows from profile JSON in fixed alphabetical order.

    Each row contains dimension, lower bound, posterior mean, upper bound,
    and number of completed sessions. Uncertainty bounds are preserved.
    """
    dimensions = profile.get("dimensions", {})
    if not isinstance(dimensions, dict) or not dimensions:
        return []

    rows: list[dict[str, Any]] = []
    # Fixed order: alphabetical by dimension id (no sorting by performance)
    for dim_name in sorted(dimensions.keys()):
        est = dimensions[dim_name]
        if not isinstance(est, dict):
            continue
        raw_n = est.get("n_sessions")
        if raw_n is None:
            raw_n = est.get("n_evidence", 0)
        n_sessions = int(raw_n or 0)
        rows.append(
            {
                "dimension": dim_name,
                "lower": float(est.get("lower", 0.0)),
                "mean": float(est.get("mean", 0.0)),
                "upper": float(est.get("upper", 0.0)),
                "n_sessions": n_sessions,
            }
        )
    return rows


def build_dimension_series(profile: dict[str, Any]) -> dict[str, list[float]]:
    """Build per-dimension chronological outcome series from evidence history.

    An outcome is the primary metric of that task in that session
    (e.g. accuracy in Go/No-Go or normalized sequence span in [0, 1]).
    Outcomes are sorted chronologically by timestamp for each dimension.
    """
    history = profile.get("evidence_history", [])
    if not isinstance(history, list) or not history:
        return {}

    # Sort evidence chronologically by timestamp
    sorted_ev = sorted(
        [ev for ev in history if isinstance(ev, dict) and "outcome" in ev],
        key=lambda ev: str(ev.get("timestamp", "")),
    )

    series: dict[str, list[float]] = {}
    for ev in sorted_ev:
        dim = str(ev.get("dimension", ""))
        if not dim:
            continue
        outcome = float(ev["outcome"])
        series.setdefault(dim, []).append(outcome)

    return series


def build_history_rows(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Build history rows from profile JSON sorted most recent first.

    Each row contains session_id, task_id, dimension, outcome, and timestamp.
    """
    history = profile.get("evidence_history", [])
    if not isinstance(history, list) or not history:
        return []

    valid_ev = [ev for ev in history if isinstance(ev, dict)]
    # Sort reverse chronologically (most recent first)
    sorted_ev = sorted(
        valid_ev,
        key=lambda ev: str(ev.get("timestamp", "")),
        reverse=True,
    )

    rows: list[dict[str, Any]] = []
    for ev in sorted_ev:
        rows.append(
            {
                "session_id": str(ev.get("session_id", "")),
                "task_id": str(ev.get("task_id", "")),
                "dimension": str(ev.get("dimension", "")),
                "outcome": float(ev.get("outcome", 0.0)),
                "timestamp": str(ev.get("timestamp", "")),
            }
        )
    return rows


def build_radar_chart_data(radar_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Compute polygon coordinates for lower, mean, and upper layers without sorting axes.

    Technique: Cartesian trigonometric projection where theta_i = -pi/2 + 2*pi*i / N
    for the i-th dimension in radar_rows, preserving the exact axis order.
    To close the polygon for each layer, the first vertex is appended at the end.
    """
    n = len(radar_rows)
    if n == 0:
        return {"lower": [], "mean": [], "upper": []}

    result: dict[str, list[dict[str, Any]]] = {"lower": [], "mean": [], "upper": []}

    for layer_name in ("lower", "mean", "upper"):
        points: list[dict[str, Any]] = []
        for i, row in enumerate(radar_rows):
            angle = -math.pi / 2 + (2 * math.pi * i) / n
            val = float(row.get(layer_name, 0.0))
            x = val * math.cos(angle)
            y = val * math.sin(angle)
            points.append(
                {
                    "dimension": str(row.get("dimension", "")),
                    "value": val,
                    "x": x,
                    "y": y,
                    "order": i,
                    "layer": layer_name,
                }
            )
        # Close polygon by appending first point
        if points:
            first = points[0]
            points.append(
                {
                    "dimension": first["dimension"],
                    "value": first["value"],
                    "x": first["x"],
                    "y": first["y"],
                    "order": n,
                    "layer": layer_name,
                }
            )
        result[layer_name] = points

    return result


def create_radar_chart(radar_rows: list[dict[str, Any]]) -> alt.LayerChart | alt.Chart:
    """Create an Altair radar chart with 3 layers (lower, mean, upper) and grid.

    Uncertainty is explicitly visualized using two bounding polygons (lower and upper)
    around the posterior mean polygon. No numeric weights, no ranking.
    """
    n = len(radar_rows)
    if n == 0:
        empty = alt.Chart({"values": [{"text": "No data"}]}).mark_text(
            text="No cognitive dimensions recorded yet."
        )
        return cast(alt.Chart, empty)

    chart_data = build_radar_chart_data(radar_rows)

    # 1. Grid rings (0.25, 0.5, 0.75, 1.0)
    grid_rows: list[dict[str, Any]] = []
    for level in (0.25, 0.5, 0.75, 1.0):
        ring_pts: list[dict[str, Any]] = []
        for i in range(n):
            angle = -math.pi / 2 + (2 * math.pi * i) / n
            ring_pts.append(
                {
                    "x": level * math.cos(angle),
                    "y": level * math.sin(angle),
                    "order": i,
                    "level": str(level),
                }
            )
        if ring_pts:
            ring_pts.append(
                {
                    "x": ring_pts[0]["x"],
                    "y": ring_pts[0]["y"],
                    "order": n,
                    "level": str(level),
                }
            )
        grid_rows.extend(ring_pts)

    grid_chart = (
        alt.Chart({"values": grid_rows})
        .mark_line(color="#e2e8f0", strokeWidth=1, strokeDash=[2, 2])
        .encode(x="x:Q", y="y:Q", detail="level:N", order="order:Q")
    )

    # 2. Spoke lines and dimension labels (with session count)
    spoke_rows: list[dict[str, Any]] = []
    label_rows: list[dict[str, Any]] = []
    for i, row in enumerate(radar_rows):
        angle = -math.pi / 2 + (2 * math.pi * i) / n
        dim_name = str(row.get("dimension", "")).replace("_", " ").title()
        n_sess = int(row.get("n_sessions", 0))
        unit = "session" if n_sess == 1 else "sessions"
        label_text = f"{dim_name} ({n_sess} {unit})"

        spoke_rows.append({"x": 0.0, "y": 0.0, "spoke": i, "order": 0})
        spoke_rows.append({"x": math.cos(angle), "y": math.sin(angle), "spoke": i, "order": 1})

        label_rows.append(
            {
                "x": 1.15 * math.cos(angle),
                "y": 1.15 * math.sin(angle),
                "label": label_text,
            }
        )

    spoke_chart = (
        alt.Chart({"values": spoke_rows})
        .mark_line(color="#cbd5e1", strokeWidth=1)
        .encode(x="x:Q", y="y:Q", detail="spoke:N", order="order:Q")
    )

    label_chart = (
        alt.Chart({"values": label_rows})
        .mark_text(fontSize=11, fontWeight="bold", color="#475569")
        .encode(x="x:Q", y="y:Q", text="label:N")
    )

    # 3. Uncertainty layers (upper and lower)
    upper_chart = (
        alt.Chart({"values": chart_data["upper"]})
        .mark_line(color="#93c5fd", strokeWidth=1.5, strokeDash=[4, 4], point=True)
        .encode(x="x:Q", y="y:Q", order="order:Q")
    )

    lower_chart = (
        alt.Chart({"values": chart_data["lower"]})
        .mark_line(color="#fca5a5", strokeWidth=1.5, strokeDash=[4, 4], point=True)
        .encode(x="x:Q", y="y:Q", order="order:Q")
    )

    # 4. Posterior mean layer
    mean_chart = (
        alt.Chart({"values": chart_data["mean"]})
        .mark_line(
            color="#2563eb",
            strokeWidth=2.5,
            point=alt.OverlayMarkDef(filled=True, size=50, color="#2563eb"),
        )
        .encode(x="x:Q", y="y:Q", order="order:Q")
    )

    # Combine all layers
    combined = (
        alt.layer(grid_chart, spoke_chart, label_chart, upper_chart, lower_chart, mean_chart)
        .properties(width=420, height=420)
        .configure_axis(grid=False, labels=False, ticks=False, domain=False, title=None)
        .configure_view(strokeWidth=0)
    )

    return cast(alt.LayerChart | alt.Chart, combined)


def build_progress_curve_data(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Build progress curve points per dimension across completed sessions.

    Outcomes are sorted chronologically. Each point contains:
    - dimension: dimension identifier
    - session_index: 1-indexed session count for this dimension
    - outcome: normalized primary metric of the task in that session in [0, 1]
    - timestamp: ISO timestamp
    """
    history = profile.get("evidence_history", [])
    if not isinstance(history, list) or not history:
        return []

    sorted_ev = sorted(
        [ev for ev in history if isinstance(ev, dict) and "outcome" in ev],
        key=lambda ev: str(ev.get("timestamp", "")),
    )

    counts: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for ev in sorted_ev:
        dim = str(ev.get("dimension", ""))
        if not dim:
            continue
        counts[dim] = counts.get(dim, 0) + 1
        rows.append(
            {
                "dimension": dim,
                "session_index": counts[dim],
                "outcome": float(ev["outcome"]),
                "timestamp": str(ev.get("timestamp", "")),
            }
        )
    return rows


def create_progress_curve(progress_rows: list[dict[str, Any]]) -> alt.Chart:
    """Create an Altair line chart showing raw outcome progress across sessions.

    One line per dimension, x = session index, y in [0, 1].
    Uncertainty intervals are NOT drawn because these are individual raw session outcomes.
    """
    if not progress_rows:
        empty = alt.Chart({"values": [{"text": "No data"}]}).mark_text(
            text="No assessment session history available yet."
        )
        return cast(alt.Chart, empty)

    chart = (
        alt.Chart({"values": progress_rows})
        .mark_line(point=True)
        .encode(
            x=alt.X("session_index:O", title="Session"),
            y=alt.Y(
                "outcome:Q",
                scale=alt.Scale(domain=[0.0, 1.0]),
                title="Outcome Score (0 - 1)",
            ),
            color=alt.Color("dimension:N", title="Dimension"),
        )
        .properties(width=500, height=280)
    )
    return cast(alt.Chart, chart)
