"""Cognitive Profile page for CogLayer UI.

Displays Bayesian estimates per dimension with 90% credible intervals,
data quality, and cross-task disclaimer note.

Requirements: R-006.4, R-010.4
"""

from __future__ import annotations

import httpx
import streamlit as st


def format_observations(n_sessions: int) -> str:
    """Format observations label to clearly state it counts sessions, not individual trials."""
    unit = "session" if n_sessions == 1 else "sessions"
    return f"{n_sessions} {unit}"


def format_uncertainty_interval(lower: float, upper: float) -> str:
    """Format uncertainty as a two-sided lower-upper interval using stored bounds."""
    lower_pct = round(lower * 100)
    upper_pct = round(upper * 100)
    return f"{lower_pct}% - {upper_pct}%"


def render_profile_page(api_url: str, user_id: str, *, heading: bool = True) -> None:
    """Render Bayesian profile estimates and data-quality captions."""
    if heading:
        st.header("Cognitive Profile")

    try:
        resp = httpx.get(f"{api_url}/v1/assessment/profile/{user_id}", timeout=5.0)
        if resp.status_code != 200:
            st.error(f"Failed to fetch profile: {resp.text}")
            return
        profile = resp.json()
    except Exception as e:
        st.error(f"Error connecting to assessment API: {e}")
        return

    dimensions = profile.get("dimensions", {})
    if not dimensions:
        st.info("No assessment evidence has been collected for this user yet.")
        if st.button("Start First Task"):
            st.session_state["page"] = "lab"
            st.session_state["pending_page_selector"] = "lab"
            st.rerun()
        return

    st.markdown(
        """
        Below are the Bayesian estimates for your cognitive performance metrics.
        Estimates update dynamically with each completed session.
        """
    )

    # Note on multiple dimensions (R-006.4, R-010.4)
    if len(dimensions) > 1:
        st.warning("⚠️ different measurement scales — dimensions are not directly comparable")

    cols = st.columns(len(dimensions))
    for i, (dim_name, est) in enumerate(dimensions.items()):
        mean_pct = round(est["mean"] * 100)
        n_obs = est.get("n_evidence", 1)

        dq = profile.get("data_quality", {}).get(dim_name, {})
        comp_pct = round(dq.get("completeness", 1.0) * 100)

        pretty_name = dim_name.replace("_", " ").title()

        with cols[i]:
            st.subheader(pretty_name)
            st.metric(
                label="Uncertainty (90% CI)",
                value=format_uncertainty_interval(est["lower"], est["upper"]),
            )
            st.caption(f"Posterior Mean: **{mean_pct}%**")
            st.caption(f"Observations (completed sessions): **{format_observations(n_obs)}**")
            st.caption(f"Data Completeness: **{comp_pct}%**")

    st.divider()

    col1, _ = st.columns([2, 3])
    with col1:
        if st.button("View Supportive Coaching Feedback", type="primary"):
            st.session_state["page"] = "coach"
            st.rerun()
