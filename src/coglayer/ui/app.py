"""Streamlit application entry point for CogLayer.

Orchestrates multi-page user assessment flow:
consent -> go_no_go -> sequence_span -> profile -> coach

Requirements: R-010.1, R-010.2, R-010.5
"""

from __future__ import annotations

import os

import httpx
import streamlit as st

from coglayer.ui.pages.coach import render_coach_page
from coglayer.ui.pages.consent import render_consent_page
from coglayer.ui.pages.dashboard import render_dashboard_page
from coglayer.ui.pages.go_no_go import render_go_no_go_page
from coglayer.ui.pages.profile import render_profile_page
from coglayer.ui.pages.sequence_span import render_sequence_span_page

# Default API URL from environment
API_URL = os.environ.get("COGLAYER_API_URL", "http://localhost:8000")


def main() -> None:
    st.set_page_config(
        page_title="CogLayer Cognitive Coaching",
        page_icon="🧠",
        layout="centered",
    )

    # Initialize session state variables
    if "user_id" not in st.session_state:
        st.session_state["user_id"] = "user_default"
    if "page" not in st.session_state:
        st.session_state["page"] = "consent"
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = None

    # Sidebar controls
    with st.sidebar:
        st.title("🧠 CogLayer")
        st.caption("Non-clinical Cognitive Coaching")

        user_input = st.text_input("User ID", value=st.session_state["user_id"])
        if user_input != st.session_state["user_id"]:
            st.session_state["user_id"] = user_input
            st.session_state["session_id"] = None
            st.session_state["page"] = "consent"
            st.rerun()

        st.divider()
        st.write("**Navigation**")
        pages = ["consent", "go_no_go", "sequence_span", "profile", "dashboard", "coach"]
        page_labels = {
            "consent": "1. Informed Consent",
            "go_no_go": "2. Go / No-Go",
            "sequence_span": "3. Sequence Span",
            "profile": "4. Cognitive Profile",
            "dashboard": "5. Cognitive Dashboard",
            "coach": "6. Cognitive Coach",
        }
        current_page = st.session_state.get("page", "consent")
        current_idx = pages.index(current_page) if current_page in pages else 0
        selected_page = st.radio(
            "Go to page",
            options=pages,
            index=current_idx,
            format_func=lambda p: page_labels.get(p, p),
        )
        if selected_page != current_page:
            st.session_state["page"] = selected_page
            st.rerun()

        st.divider()
        if st.button("New Assessment Session"):
            st.session_state["session_id"] = None
            st.session_state["page"] = "go_no_go"
            st.rerun()

    user_id = st.session_state["user_id"]
    page = st.session_state["page"]

    # Ensure active session exists when running task pages
    if page in ("go_no_go", "sequence_span") and not st.session_state.get("session_id"):
        try:
            sess_resp = httpx.post(
                f"{API_URL}/v1/assessment/sessions",
                json={"user_id": user_id},
                timeout=5.0,
            )
            if sess_resp.status_code == 201:
                st.session_state["session_id"] = sess_resp.json()["session_id"]
            elif sess_resp.status_code == 403:
                # Consent needed first
                st.session_state["page"] = "consent"
        except Exception as exc:
            import logging

            logging.getLogger(__name__).debug("Session check deferred: %s", exc)

    session_id = st.session_state.get("session_id", "")

    # Page dispatch
    if page == "consent":
        render_consent_page(API_URL, user_id)
    elif page == "go_no_go":
        render_go_no_go_page(API_URL, user_id, session_id)
    elif page == "sequence_span":
        render_sequence_span_page(API_URL, user_id, session_id)
    elif page == "profile":
        render_profile_page(API_URL, user_id)
    elif page == "dashboard":
        render_dashboard_page(API_URL, user_id)
    elif page == "coach":
        render_coach_page(API_URL, user_id)
    else:
        render_consent_page(API_URL, user_id)


if __name__ == "__main__":
    main()
