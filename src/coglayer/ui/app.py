"""Streamlit application entry point for CogLayer.

Orchestrates the decision-driven multi-page user assessment flow.

Requirements: R-010.1, R-010.2, R-010.5
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlsplit

import httpx
import streamlit as st

from coglayer.core.adaptation import get_theme_css
from coglayer.ui.api import (
    create_assessment_session,
    get_assessment_session,
    get_assessment_sessions,
    get_decision,
)
from coglayer.ui.design import (
    brand_html,
    design_css,
    footer_html,
    sidebar_note_html,
    theme_overrides,
    workspace_header_html,
)
from coglayer.ui.navigation import navigate_decision
from coglayer.ui.page_views.coach import render_coach_page
from coglayer.ui.page_views.cognitive_lab import render_cognitive_lab_page
from coglayer.ui.page_views.consent import render_consent_page
from coglayer.ui.page_views.corsi_blocks import render_corsi_blocks_page
from coglayer.ui.page_views.dashboard import render_profile_dashboard_page
from coglayer.ui.page_views.digit_span import render_digit_span_page
from coglayer.ui.page_views.go_no_go import render_go_no_go_page
from coglayer.ui.page_views.ioi import render_ioi_page
from coglayer.ui.page_views.letter_number import render_letter_number_page
from coglayer.ui.page_views.n_back import render_n_back_page
from coglayer.ui.page_views.onboarding import render_onboarding_page
from coglayer.ui.page_views.perception import render_perception_lab_page
from coglayer.ui.page_views.sequence_span import render_sequence_span_page
from coglayer.ui.page_views.stroop import render_stroop_page

# Default API URL from environment
API_URL = os.environ.get("COGLAYER_API_URL", "http://localhost:8000")
_SIDEBAR_PAGES: tuple[str, ...] = (
    "consent",
    "onboarding",
    "lab",
    "profile",
    "coach",
    "ioi",
)
_SIDEBAR_LABELS: Mapping[str, str] = {
    "consent": "1. Informed Consent",
    "onboarding": "2. Onboarding",
    "lab": "3. Cognitive Lab",
    "profile": "4. Cognitive Profile & Dashboard",
    "coach": "5. Cognitive Coach",
    "ioi": "6. AI Collaboration Score",
}
_SIDEBAR_ALIASES: Mapping[str, str] = {
    "dashboard": "profile",
    "next": "lab",
}
_RESUMABLE_SESSION_STATUSES = frozenset({"pending", "in_progress"})
_SESSION_QUERY_PARAM = "session_id"


def _page_from_url(url: str) -> str | None:
    """Return the registered page represented by a browser URL."""
    path = urlsplit(url).path.rstrip("/")
    return "ioi" if path == "/ioi" else None


def _navigate_from_sidebar() -> None:
    """Use a valid sidebar selection as the canonical page."""
    selected_page = st.session_state.get("page_selector")
    if selected_page in _SIDEBAR_PAGES:
        st.session_state["page"] = selected_page


def _sidebar_selection_for(page: str | None) -> str:
    """Return the visible sidebar option that represents an internal page."""
    if page in _SIDEBAR_PAGES:
        return page
    aliased = _SIDEBAR_ALIASES.get(page or "")
    if aliased in _SIDEBAR_PAGES:
        return aliased
    return "lab"


def _request_navigation(page: str) -> None:
    """Set the canonical page and queue sidebar synchronization when applicable."""
    st.session_state["page"] = page
    if page in _SIDEBAR_PAGES:
        st.session_state["pending_page_selector"] = page
    else:
        st.session_state.pop("pending_page_selector", None)


def _session_id_from_query_params() -> str | None:
    """Return the exact assessment session ID from the browser URL."""
    value = st.query_params.get(_SESSION_QUERY_PARAM)
    return value if isinstance(value, str) and value else None


def _set_session_query_param(session_id: str | None) -> None:
    """Synchronize or clear the active assessment session in the browser URL."""
    if session_id is None:
        st.query_params.pop(_SESSION_QUERY_PARAM, None)
    else:
        st.query_params[_SESSION_QUERY_PARAM] = session_id


def _restore_session_from_url(user_id: str) -> str | None:
    """Restore an owned pending assessment session from the browser URL."""
    session_id = _session_id_from_query_params()
    if session_id is None:
        return None
    try:
        session = get_assessment_session(API_URL, user_id, session_id)
    except (httpx.HTTPError, ValueError):
        _set_session_query_param(None)
        st.warning("The session in the URL is unavailable and was not activated.")
        return None
    if (
        session.get("user_id") != user_id
        or session.get("session_id") != session_id
        or session.get("status") not in _RESUMABLE_SESSION_STATUSES
    ):
        _set_session_query_param(None)
        st.warning("The session in the URL is not resumable for this user.")
        return None
    st.session_state["session_id"] = session_id
    _set_session_query_param(session_id)
    return session_id


def _select_session(session: Mapping[str, object]) -> None:
    """Activate a session after it has been explicitly selected by the user."""
    session_id = session.get("session_id")
    user_id = session.get("user_id")
    status = session.get("status")
    if (
        not isinstance(session_id, str)
        or not session_id
        or user_id != st.session_state.get("user_id")
        or status not in _RESUMABLE_SESSION_STATUSES
    ):
        st.error("The selected session is invalid or cannot be resumed.")
        return
    st.session_state["session_id"] = session_id
    _set_session_query_param(session_id)
    _request_navigation("lab")
    st.success("Assessment session selected.")


def _render_session_picker(user_id: str) -> None:
    """Render explicit controls for resuming or creating an assessment session."""
    st.info("Select an existing assessment session, or create a new one below.")
    try:
        sessions = get_assessment_sessions(API_URL, user_id)
    except (httpx.HTTPError, ValueError) as exc:
        st.error(f"Could not load assessment sessions: {exc}")
        return

    if sessions:
        session_by_id = {
            session["session_id"]: session
            for session in sessions
            if isinstance(session.get("session_id"), str)
        }
        if session_by_id:
            selected_id = st.selectbox(
                "Assessment session",
                options=tuple(session_by_id),
                format_func=lambda value: (
                    f"{value} ({session_by_id[value].get('status', 'unknown')})"
                ),
                key="session_picker",
            )
            if st.button("Resume selected session", key="resume_selected_session"):
                _select_session(session_by_id[selected_id])
                st.rerun()
    else:
        st.caption("No pending or in-progress assessment sessions are available.")

    st.divider()
    if st.button(
        "Create New Session",
        key="create_session_from_picker",
        type="primary",
    ):
        _create_new_session(user_id)


def _create_new_session(user_id: str) -> None:
    """Create and activate a new assessment session after explicit user action."""
    try:
        session_id = create_assessment_session(API_URL, user_id)
        if session_id is None:
            raise ValueError("Assessment session response did not include a session ID.")
    except (httpx.HTTPError, ValueError) as exc:
        st.error(f"Error creating assessment session: {exc}")
        return
    st.session_state["session_id"] = session_id
    _set_session_query_param(session_id)
    _request_navigation("lab")
    st.rerun()


def _prepare_navigation_state(current_url: str | None) -> None:
    """Apply one URL or pending route before sidebar widgets are created."""
    url_page = _page_from_url(current_url) if current_url is not None else None
    last_seen_url = st.session_state.get("last_seen_url")
    is_new_url = current_url is not None and current_url != last_seen_url
    if current_url is not None:
        st.session_state["last_seen_url"] = current_url

    pending_page = st.session_state.pop("pending_page_selector", None)
    if isinstance(pending_page, str):
        pending_page = _SIDEBAR_ALIASES.get(pending_page, pending_page)
    if is_new_url and url_page in _SIDEBAR_PAGES:
        st.session_state["page"] = url_page
        pending_page = url_page

    current_page = st.session_state.get("page")
    if current_page == "dashboard":
        st.session_state["page"] = "profile"
        current_page = "profile"

    if pending_page in _SIDEBAR_PAGES:
        st.session_state.pop("page_selector", None)
        st.session_state["page_selector"] = pending_page
    else:
        selector = st.session_state.get("page_selector")
        if selector not in _SIDEBAR_PAGES:
            st.session_state.pop("page_selector", None)
            st.session_state["page_selector"] = _sidebar_selection_for(
                current_page if isinstance(current_page, str) else None
            )


def _apply_user_theme(api_url: str, user_id: str) -> None:
    """Fetch user's onboarding profile and inject theme CSS."""
    try:
        resp = httpx.get(
            f"{api_url}/v1/assessment/onboarding/profile/{user_id}",
            params={"user_id": user_id},
            timeout=3.0,
        )
        if resp.status_code == 200:
            profile_data = resp.json()
            if isinstance(profile_data, dict):
                theme_str = profile_data.get("theme")
                css = get_theme_css(theme_str)
                if css:
                    st.markdown(
                        f"<style>{css}{theme_overrides(theme_str)}</style>",
                        unsafe_allow_html=True,
                    )
    except (httpx.HTTPError, ValueError):
        pass


def main() -> None:
    st.set_page_config(
        page_title="CogLayer Cognitive Coaching",
        page_icon="🧠",
        layout="wide",
    )
    st.markdown(f"<style>{design_css()}</style>", unsafe_allow_html=True)

    # Initialize session state variables
    if "user_id" not in st.session_state:
        st.session_state["user_id"] = "user_default"
    if "page" not in st.session_state:
        st.session_state["page"] = "consent"
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = None

    user_id = st.session_state.get("user_id", "user_default")
    _apply_user_theme(API_URL, user_id)

    current_url = st.context.url
    _prepare_navigation_state(current_url if isinstance(current_url, str) else None)

    # Sidebar controls
    with st.sidebar:
        st.markdown(brand_html(), unsafe_allow_html=True)
        st.caption("Non-clinical Cognitive Coaching")

        user_input = st.text_input("User ID", value=st.session_state["user_id"])
        if user_input != st.session_state["user_id"]:
            st.session_state["user_id"] = user_input
            st.session_state["session_id"] = None
            _set_session_query_param(None)
            _request_navigation("consent")
            st.rerun()

        st.divider()
        st.write("**Navigation**")
        st.radio(
            "Go to page",
            options=_SIDEBAR_PAGES,
            format_func=lambda p: _SIDEBAR_LABELS.get(p, p),
            key="page_selector",
            on_change=_navigate_from_sidebar,
        )

        st.divider()
        if st.button("New Assessment Session"):
            _create_new_session(st.session_state["user_id"])
        st.markdown(sidebar_note_html(), unsafe_allow_html=True)

    user_id = st.session_state["user_id"]
    if (
        not isinstance(st.session_state.get("session_id"), str)
        or not st.session_state["session_id"]
    ):
        _restore_session_from_url(user_id)
    page = st.session_state["page"]

    if page == "next":
        _handle_next_page(user_id)
        page = st.session_state.get("page", "next")

    session_id = st.session_state.get("session_id", "")
    if isinstance(session_id, str) and session_id:
        _set_session_query_param(session_id)

    page_label = _SIDEBAR_LABELS[_sidebar_selection_for(page)].partition(". ")[2]
    st.markdown(workspace_header_html(page_label), unsafe_allow_html=True)

    # Page dispatch
    if page == "consent":
        render_consent_page(API_URL, user_id)
    elif page == "onboarding":
        render_onboarding_page(API_URL, user_id)
    elif page == "lab":
        render_cognitive_lab_page(API_URL, user_id)
    elif page == "go_no_go":
        render_go_no_go_page(API_URL, user_id, session_id)
    elif page == "sequence_span":
        render_sequence_span_page(API_URL, user_id, session_id)
    elif page == "digit_span":
        render_digit_span_page(API_URL, user_id, session_id)
    elif page == "stroop":
        render_stroop_page(API_URL, user_id, session_id)
    elif page == "corsi_blocks":
        render_corsi_blocks_page(API_URL, user_id, session_id)
    elif page == "n_back":
        render_n_back_page(API_URL, user_id, session_id)
    elif page == "letter_number_sequencing":
        render_letter_number_page(API_URL, user_id, session_id)
    elif page == "perception_lab":
        render_perception_lab_page(API_URL, user_id, session_id)
    elif page in {"profile", "dashboard"}:
        render_profile_dashboard_page(API_URL, user_id)
    elif page == "coach":
        render_coach_page(API_URL, user_id)
    elif page == "ioi":
        render_ioi_page(API_URL, user_id, session_id)
    else:
        render_consent_page(API_URL, user_id)

    st.markdown(footer_html(), unsafe_allow_html=True)


def _route_decision(decision: Mapping[str, object]) -> None:
    """Store the navigation target produced by an assessment decision."""
    target = navigate_decision(decision)
    _request_navigation(target.page)
    if target.message:
        st.session_state["decision_reason"] = target.message
    else:
        st.session_state.pop("decision_reason", None)
    if target.page == "next" and not target.reset_session:
        st.warning(target.message or "The assessment could not determine the next step.")
        return
    if target.reset_session:
        st.session_state["session_id"] = None
        st.info(target.message or "Starting a new assessment session.")
    st.rerun()


def _handle_next_page(user_id: str) -> None:
    """Route the active assessment session without creating one implicitly."""
    session_id = st.session_state.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        _render_session_picker(user_id)
        return

    try:
        decision = get_decision(API_URL, session_id)
    except (httpx.HTTPError, ValueError) as exc:
        st.error(f"Error loading assessment decision: {exc}")
        return
    _route_decision(decision)


if __name__ == "__main__":
    main()
