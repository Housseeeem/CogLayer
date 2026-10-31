"""Cognitive Dashboard page for CogLayer UI.

Displays a radar chart with credible intervals, a longitudinal progress curve,
and a read-only assessment history table. Strictly non-clinical.

Requirements: Layer C Dashboard
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from coglayer.ui.dashboard import (
    build_heatmap_data,
    build_history_rows,
    build_progress_curve_data,
    build_radar_rows,
    create_heatmap,
    create_progress_curve,
    select_overview_chart,
)
from coglayer.ui.page_views.profile import render_profile_page

DISCLAIMER_TEXT = "Based on these two tasks only — not a clinical assessment."


def render_profile_dashboard_page(api_url: str, user_id: str) -> None:
    """Render profile estimates together with dashboard charts and history."""
    st.header("Cognitive Profile & Dashboard")
    render_profile_page(api_url, user_id, heading=False)
    st.divider()
    render_dashboard_page(api_url, user_id, heading=False, show_empty_cta=False)


def render_dashboard_page(
    api_url: str,
    user_id: str,
    *,
    heading: bool = True,
    show_empty_cta: bool = True,
) -> None:
    """Render Brain Twin status, charts, progress, and assessment history."""
    if heading:
        st.header("Cognitive Dashboard")
    st.caption(DISCLAIMER_TEXT)

    _render_brain_twin(api_url, user_id)
    st.divider()

    # 1. Fetch profile from API
    try:
        resp = httpx.get(f"{api_url}/v1/assessment/profile/{user_id}", timeout=5.0)
        if resp.status_code == 403:
            st.info(
                "Please provide informed consent and complete your first session "
                "to view the dashboard."
            )
            if st.button("Go to Consent"):
                st.session_state["page"] = "consent"
                st.rerun()
            return
        if resp.status_code != 200:
            st.error(f"Failed to load dashboard data: HTTP {resp.status_code}")
            return
        profile = resp.json()
    except Exception as exc:
        st.error(f"Error connecting to assessment API: {exc}")
        return

    # 2. Extract rows
    radar_rows = build_radar_rows(profile)
    history_rows = build_history_rows(profile)
    progress_rows = build_progress_curve_data(profile)

    # Empty state check
    if not radar_rows:
        st.info(
            "No assessment evidence has been recorded yet. "
            "Please complete your first session to view your cognitive dashboard."
        )
        if show_empty_cta and st.button("Start First Task"):
            st.session_state["page"] = "lab"
            st.session_state["pending_page_selector"] = "lab"
            st.rerun()
        return

    # Check total sessions count across dimensions
    total_sessions = max((r.get("n_sessions", 0) for r in radar_rows), default=0)

    # 3. Overview chart section
    st.subheader("Cognitive Dimensions Overview")
    chart_type, overview_chart = select_overview_chart(radar_rows)
    if chart_type == "interval":
        st.markdown("Posterior estimates and 90% credible intervals in fixed alphabetical order.")
        st.altair_chart(overview_chart, use_container_width=True)
        st.caption("The radar chart appears once at least 3 dimensions are profiled.")
    else:
        st.markdown(
            "The radar chart displays Bayesian posterior estimates in fixed alphabetical order. "
            "The dashed outer and inner bounds visualize 90% credible intervals."
        )
        st.altair_chart(overview_chart, use_container_width=True)

    st.divider()

    # 4. Longitudinal progress curve section
    st.subheader("Performance Across Sessions")
    if total_sessions <= 1:
        st.info("Trends require at least two completed sessions to show changes over time.")

    curve_chart = create_progress_curve(progress_rows)
    st.altair_chart(curve_chart, use_container_width=True)
    st.caption(
        "Note: A rise on the same task can reflect practice or strategy, "
        "not necessarily a gain in ability."
    )

    # Performance heatmap
    st.subheader("Performance Heatmap")
    evidence_history: list[dict[str, Any]] = profile.get("evidence_history", [])
    heatmap_dims, heatmap_sessions, heatmap_rows = build_heatmap_data(evidence_history)
    if not heatmap_rows:
        st.info("Complete at least one session to see the heatmap.")
    else:
        heatmap_chart = create_heatmap(heatmap_dims, heatmap_sessions, heatmap_rows)
        st.altair_chart(heatmap_chart, use_container_width=True)
        st.caption("Dimensions use different measurement scales and are not directly comparable.")

    st.divider()

    # 5. History table section
    st.subheader("Assessment History")
    if history_rows:
        display_rows = [
            {
                "Session": r["session_id"],
                "Task": r["task_id"].replace("_", " ").title(),
                "Dimension": r["dimension"].replace("_", " ").title(),
                "Outcome Score": f"{round(r['outcome'] * 100)}%",
                "Timestamp": r["timestamp"][:19].replace("T", " ")
                if len(r["timestamp"]) >= 19
                else r["timestamp"],
            }
            for r in history_rows
        ]
        st.dataframe(display_rows, hide_index=True, use_container_width=True)
    else:
        st.caption("No history records available.")


def _render_brain_twin(api_url: str, user_id: str) -> None:
    """Display the EMA status without making a clinical claim."""
    st.subheader("Brain Twin Fast-Track")
    st.caption(
        "A transparent baseline for comparable Go / No-Go outcomes. "
        "A flag means variation worth reviewing, not a cause or conclusion."
    )
    try:
        response = httpx.get(f"{api_url}/v1/assessment/brain-twin/{user_id}", timeout=5.0)
        if response.status_code == 403:
            st.info("Give consent before viewing the baseline signal.")
            return
        response.raise_for_status()
        result = response.json()
    except Exception as exc:
        st.warning(f"Brain Twin status is unavailable: {exc}")
        return

    status = result.get("status")
    points = result.get("points", [])
    if status != "AVAILABLE":
        st.info("Not enough comparable observations to establish a baseline yet.")
        return
    flagged = [point for point in points if isinstance(point, dict) and point.get("flagged")]
    if flagged:
        st.warning(
            "A recent result differs from this user's transparent baseline. "
            "Consider reviewing the context or repeating the activity."
        )
    else:
        st.success("No unusual variation was flagged in the available comparable results.")
