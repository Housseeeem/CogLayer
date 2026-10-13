"""Cognitive Coach feedback page for CogLayer UI.

Displays personalized, non-clinical supportive feedback from the coach endpoint.

Requirements: R-008.1, R-008.3
"""

from __future__ import annotations

import httpx
import streamlit as st


def render_coach_page(api_url: str, user_id: str) -> None:
    """Render the cognitive coach feedback page."""
    st.header("Supportive Cognitive Coach")

    with st.spinner("Generating personalized coaching feedback..."):
        try:
            resp = httpx.post(f"{api_url}/v1/assessment/coach/{user_id}", timeout=15.0)
            if resp.status_code == 403:
                st.warning("Assessment not yet complete. Please finish all tasks first.")
                col1, _ = st.columns([2, 3])
                with col1:
                    if st.button("Return to Tasks"):
                        st.session_state["page"] = "go_no_go"
                        st.rerun()
                return
            elif resp.status_code != 200:
                st.error(f"Error from coach service: {resp.text}")
                return

            feedback_text = resp.text
        except Exception as e:
            st.error(f"Error connecting to coach endpoint: {e}")
            return

    st.markdown("### Feedback & Suggestions")
    st.info(feedback_text)

    st.divider()
    col1, col2 = st.columns([2, 3])
    with col1:
        if st.button("Start Another Session"):
            st.session_state["session_id"] = None
            st.session_state["page"] = "go_no_go"
            st.rerun()
    with col2:
        if st.button("Back to Profile View"):
            st.session_state["page"] = "profile"
            st.rerun()
