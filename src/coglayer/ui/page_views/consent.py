"""Consent page for CogLayer UI.

Displays informed consent screen and non-clinical disclaimer.
Advances to the Cognitive Lab upon user agreement.

Requirements: R-001.1, R-001.4, R-010.2
"""

from __future__ import annotations

import httpx
import streamlit as st


def render_consent_page(api_url: str, user_id: str) -> None:
    """Render the user consent screen."""
    st.header("Informed Consent & Privacy")

    # Check if user has already consented
    try:
        resp = httpx.get(f"{api_url}/v1/assessment/consent/{user_id}", timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            has_consented = (
                data.get("has_consented", False) if isinstance(data, dict) else bool(data)
            )
            if has_consented:
                st.success(f"User '{user_id}' has already granted consent.")
                if st.button("Continue to Assessment", type="primary"):
                    st.session_state["page"] = "lab"
                    st.session_state["pending_page_selector"] = "lab"
                    st.rerun()
                return
    except Exception as exc:
        st.warning(f"Could not connect to API to verify consent status: {exc}")

    st.markdown(
        """
        Welcome to **CogLayer**, a provider-agnostic cognitive coaching layer.

        ### What is stored
        - Response times and accuracy on interactive cognitive reflection tasks.
        - High-level Bayesian profile estimates and data quality indicators.
        - **No raw conversation transcripts or sensitive personal documents are stored.**

        ### Local Privacy
        - All task processing and profile updates are stored locally on your machine.
        - Data never leaves your computer in local mode.

        ### Non-Clinical Statement
        - CogLayer is an educational and supportive coaching tool.
        - **It does not diagnose, treat, or evaluate clinical conditions.**
        - The metrics reflect performance on specific micro-tasks only.
        """
    )

    col1, _ = st.columns([1, 4])
    with col1:
        if st.button("I Consent", type="primary"):
            try:
                post_resp = httpx.post(
                    f"{api_url}/v1/assessment/consent",
                    json={"user_id": user_id},
                    timeout=5.0,
                )
                if post_resp.status_code in (200, 201):
                    st.session_state["page"] = "lab"
                    st.session_state["pending_page_selector"] = "lab"
                    st.rerun()
                else:
                    st.error(f"Failed to record consent: {post_resp.text}")
            except Exception as e:
                st.error(f"Error connecting to assessment API: {e}")
