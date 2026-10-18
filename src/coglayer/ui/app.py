"""Streamlit application entry point for CogLayer.

Orchestrates the decision-driven multi-page user assessment flow.

Requirements: R-010.1, R-010.2, R-010.5
"""

from __future__ import annotations

import os
from collections.abc import Mapping

import httpx
import streamlit as st

from coglayer.ui.api import get_decision
from coglayer.ui.navigation import navigate_decision
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
        pages = ["consent", "next", "profile", "dashboard", "coach"]
        page_labels = {
            "consent": "1. Informed Consent",
            "next": "2. Next Assessment Task",
            "profile": "3. Cognitive Profile",
            "dashboard": "4. Cognitive Dashboard",
            "coach": "5. Cognitive Coach",
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
            st.session_state["page"] = "next"
            st.rerun()

    user_id = st.session_state["user_id"]
    page = st.session_state["page"]

    if page == "next":
        _handle_next_page(user_id)
        page = st.session_state.get("page", "next")

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


def _route_decision(decision: Mapping[str, object]) -> None:
    """Store the navigation target produced by an assessment decision."""
    target = navigate_decision(decision)
    st.session_state["page"] = target.page
    if target.message:
        st.session_state["decision_reason"] = target.message
    else:
        st.session_state.pop("decision_reason", None)
    if target.reset_session:
        st.session_state["session_id"] = None
        st.info(target.message or "Starting a new assessment session.")
    st.rerun()


def _handle_next_page(user_id: str) -> None:
    """Create an assessment session when needed and route its next decision."""
    session_id = st.session_state.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        try:
            response = httpx.post(
                f"{API_URL}/v1/assessment/sessions",
                json={"user_id": user_id},
                timeout=5.0,
            )
            if response.status_code == 403:
                st.session_state["page"] = "consent"
                st.error("Please provide informed consent before starting an assessment.")
                return
            if response.status_code != 201:
                st.error(f"Failed to create assessment session: HTTP {response.status_code}")
                return
            session_data = response.json()
            session_id = session_data.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                st.error("Assessment session response did not include a session ID.")
                return
            st.session_state["session_id"] = session_id
        except (httpx.HTTPError, ValueError) as exc:
            st.error(f"Error creating assessment session: {exc}")
            return

    try:
        decision = get_decision(API_URL, session_id)
    except (httpx.HTTPError, ValueError) as exc:
        st.error(f"Error loading assessment decision: {exc}")
        return
    _route_decision(decision)


if __name__ == "__main__":
    main()
