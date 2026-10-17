"""Cognitive Dashboard page for CogLayer UI.

Displays a radar chart with credible intervals, a longitudinal progress curve,
and a read-only assessment history table. Strictly non-clinical.

Requirements: Layer C Dashboard
"""

from __future__ import annotations

import httpx
import streamlit as st

from coglayer.ui.dashboard import (
    build_history_rows,
    build_progress_curve_data,
    build_radar_rows,
    create_progress_curve,
    create_radar_chart,
)

DISCLAIMER_TEXT = "Based on these two tasks only — not a clinical assessment."


def render_dashboard_page(api_url: str, user_id: str) -> None:
    """Render the cognitive dashboard page with radar chart, progress curve, and history."""
    st.header("Cognitive Dashboard")
    st.caption(DISCLAIMER_TEXT)

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
        if st.button("Start First Task"):
            st.session_state["page"] = "go_no_go"
            st.rerun()
        return

    # Check total sessions count across dimensions
    total_sessions = max((r.get("n_sessions", 0) for r in radar_rows), default=0)

    # 3. Radar chart section
    st.subheader("Cognitive Dimensions Overview")
    st.markdown(
        "The radar chart displays Bayesian posterior estimates in fixed alphabetical order. "
        "The dashed outer and inner bounds visualize 90% credible intervals."
    )
    radar_chart = create_radar_chart(radar_rows)
    st.altair_chart(radar_chart, use_container_width=True)

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
