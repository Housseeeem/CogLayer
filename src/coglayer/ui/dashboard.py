"""Pure data helpers and chart generation for the CogLayer cognitive dashboard.

Provides pure functions to process profile JSON into radar rows,
per-dimension outcome series, and history rows, satisfying non-clinical rules.

Requirements: Layer C Dashboard
"""

from __future__ import annotations

from typing import Any


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
