"""Central entry point for CogLayer's interactive cognitive experiences."""

from __future__ import annotations

from typing import Any, Literal

import httpx
import streamlit as st

from coglayer.ui.api import (
    get_assessment_session,
    get_daily_plan,
    update_daily_plan_status,
)
from coglayer.ui.design import activity_card_html, lab_hero_html

# Each entry: (task_id, label, emoji, description, focus, page_key | None)
# page_key is the app.py dispatch key; None means no interactive page yet.
# Kept as metadata for recommended-session cards; not rendered as a catalog.
_GAME_CARDS: tuple[tuple[str, str, str, str, str, str | None], ...] = (
    (
        "go_no_go",
        "Go / No-Go",
        "🟢",
        "Respond to green targets and inhibit responses to red targets.",
        "Response inhibition",
        "go_no_go",
    ),
    (
        "sequence_span",
        "Sequence Span",
        "🔢",
        "Watch a spatial sequence, then reproduce it in the same order.",
        "Sequential visual memory",
        "sequence_span",
    ),
    (
        "digit_span",
        "Digit Span",
        "🔠",
        "Memorize and reproduce digit sequences forward or backward.",
        "Short-term verbal working memory",
        "digit_span",
    ),
    (
        "stroop",
        "Stroop",
        "🎨",
        "Name the ink colour while ignoring the printed word.",
        "Cognitive flexibility · selective attention",
        "stroop",
    ),
    (
        "corsi_blocks",
        "Corsi Blocks",
        "🧩",
        "Reproduce tapped spatial sequences in forward or reverse order.",
        "Visuospatial working memory",
        "corsi_blocks",
    ),
    (
        "n_back",
        "N-Back",
        "🔁",
        "Indicate when the current stimulus matches the one N items ago.",
        "Working memory updating",
        "n_back",
    ),
    (
        "letter_number_sequencing",
        "Letter-Number Sequencing",
        "🔤",
        "Reorder a mix of letters and numbers: numbers ascending, then letters alphabetically.",
        "Active mental manipulation",
        "letter_number_sequencing",
    ),
    (
        "perception_lab",
        "Perception Lab",
        "👁️",
        "Observe ambiguous figures and report perceptual switches.",
        "Perceptual stability",
        "perception_lab",
    ),
)

_CARD_BY_ID = {item[0]: item for item in _GAME_CARDS}

TaskDisplayState = Literal["completed", "in_progress", "pending"]


def _http_error_detail(exc: httpx.HTTPStatusError) -> str:
    """Return a short API detail string when the response body is a JSON object."""
    try:
        payload = exc.response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    detail = payload.get("detail")
    return detail if isinstance(detail, str) else ""


def _plan_fetch_error_message(exc: BaseException) -> str:
    """Return a user-facing message for a failed daily-plan request."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = _http_error_detail(exc)
        detail_lower = detail.lower()
        if status == 403 and "consent" in detail_lower:
            return "Active consent is required to generate a daily recommended session."
        if status == 403:
            return "This daily recommended session is not available for the current user."
        return "The daily recommended session could not be loaded. Please try again."
    if isinstance(exc, httpx.HTTPError):
        return "Could not reach the assessment service to load today's recommended session."
    return "The daily recommended session response was invalid."


def _completed_task_ids_from_session(
    session: dict[str, Any],
    user_id: str,
    session_id: str,
) -> set[str]:
    """Return completed task ids only when the payload matches the active session."""
    payload_session = session.get("session_id")
    payload_user = session.get("user_id")
    if payload_session != session_id or payload_user != user_id:
        return set()
    completed = session.get("completed_tasks", [])
    if not isinstance(completed, list):
        return set()
    return {item for item in completed if isinstance(item, str) and item}


def _load_completed_task_ids(
    api_url: str,
    user_id: str,
    session_id: str,
) -> set[str]:
    """Fetch completed tasks for the active session; empty on lookup failure."""
    try:
        session = get_assessment_session(api_url, user_id, session_id)
    except (httpx.HTTPError, ValueError):
        return set()
    return _completed_task_ids_from_session(session, user_id, session_id)


def _recommendation_display_state(plan_status: object, task_completed: bool) -> TaskDisplayState:
    """Derive a display-only status for one recommended task.

    In-progress is a plan-level approximation (the daily plan is started and
    this task is not in the active session's completed list). It is not proof
    of task-level progress.
    """
    if task_completed:
        return "completed"
    if plan_status == "started":
        return "in_progress"
    return "pending"


def render_cognitive_lab_page(
    api_url: str | None = None,
    user_id: str | None = None,
) -> None:
    """Render today's recommended Cognitive Lab session."""
    session_id = st.session_state.get("session_id")
    has_session = isinstance(session_id, str) and bool(session_id)
    target_user = user_id or st.session_state.get("user_id") or ""
    active_api = api_url or "http://localhost:8000"

    st.header("Cognitive Lab")
    st.caption(
        "Short, interactive activities for exploring attention and sequential memory. "
        "They are educational proxies, not clinical measurements."
    )

    if not (isinstance(target_user, str) and target_user and active_api):
        st.info("A user ID is required to load today's recommended session.")
        if not has_session:
            st.warning("Start or resume an assessment session before opening an activity.")
        return

    with st.container(border=True, key="cog_daily_plan"):
        st.subheader("Daily recommended session")
        try:
            force_regen = bool(st.session_state.pop("force_regenerate_daily_plan", False))
            user_feedback = st.session_state.get("daily_subjective_feedback")
            feedback = user_feedback if isinstance(user_feedback, str) else None
            plan = get_daily_plan(
                api_url=active_api,
                user_id=target_user,
                force_regenerate=force_regen,
                subjective_feedback=feedback,
            )
        except (httpx.HTTPError, ValueError) as exc:
            message = _plan_fetch_error_message(exc)
            if "consent" in message.lower():
                st.warning(message)
            else:
                st.error(message)
            if not has_session:
                st.warning("Start or resume an assessment session before opening an activity.")
            return

        if "recommendations" not in plan:
            st.error("The daily recommended session response was invalid.")
            if not has_session:
                st.warning("Start or resume an assessment session before opening an activity.")
            return

        if plan.get("is_personalized", False):
            st.info("Personalized recommendation — tailored to your activity history.")
        else:
            st.caption("Initial discovery session — a balanced selection across varied domains.")

        completed_ids: set[str] = set()
        if has_session and isinstance(session_id, str):
            completed_ids = _load_completed_task_ids(active_api, target_user, session_id)

        recs = plan.get("recommendations", [])
        if not isinstance(recs, list):
            recs = []
        recommended_ids = {
            rec["task_id"]
            for rec in recs
            if isinstance(rec, dict) and isinstance(rec.get("task_id"), str) and rec["task_id"]
        }
        st.markdown(
            lab_hero_html(
                completed=len(completed_ids & recommended_ids),
                total=len(recommended_ids),
            ),
            unsafe_allow_html=True,
        )
        cols = st.columns(len(recs)) if recs else []
        plan_status = plan.get("status", "generated")
        for idx, rec in enumerate(recs):
            if not isinstance(rec, dict):
                continue
            task_id = rec.get("task_id", "")
            if not isinstance(task_id, str) or not task_id:
                continue
            rationale = rec.get("rationale", "")
            diff_raw = rec.get("difficulty_level", "standard")
            diff = diff_raw.title() if isinstance(diff_raw, str) else "Standard"
            dim_raw = rec.get("target_dimension", "")
            dim = dim_raw.replace("_", " ").title() if isinstance(dim_raw, str) else ""

            card_info = _CARD_BY_ID.get(task_id)
            label = card_info[1] if card_info else task_id
            description = card_info[3] if card_info else "Explore this recommended activity."
            page_key = card_info[5] if card_info else task_id
            display_state = _recommendation_display_state(plan_status, task_id in completed_ids)

            with cols[idx]:
                with st.container(border=True, key=f"cog_activity_{task_id}"):
                    st.markdown(
                        activity_card_html(
                            task_id=task_id,
                            label=label,
                            dimension=dim,
                            level=diff,
                            description=description,
                        ),
                        unsafe_allow_html=True,
                    )
                    if display_state == "completed":
                        st.caption("Status: completed")
                    elif display_state == "in_progress":
                        st.caption(
                            "Status: in progress (plan-level estimate — this activity "
                            "is not marked complete)."
                        )
                    else:
                        st.caption("Status: pending")
                    if isinstance(rationale, str) and rationale:
                        st.write(rationale)

                    if display_state == "completed":
                        st.button(
                            "Completed",
                            key=f"daily_rec_{task_id}",
                            disabled=True,
                        )
                    elif st.button(
                        f"Start {label}",
                        key=f"daily_rec_{task_id}",
                        type="primary",
                        disabled=not has_session,
                    ):
                        try:
                            update_daily_plan_status(
                                api_url=active_api,
                                user_id=target_user,
                                plan_date=str(plan.get("plan_date", "")),
                                status="started",
                                session_id=session_id if has_session else None,
                            )
                        except (httpx.HTTPError, ValueError) as exc:
                            st.error(
                                "Could not mark the daily session as started. "
                                f"{_plan_fetch_error_message(exc)}"
                            )
                            continue
                        if page_key:
                            st.session_state["page"] = page_key
                            st.rerun()

        col_feed, col_btn = st.columns([3, 1])
        with col_feed:
            feedback_choice = st.selectbox(
                "Energy & Readiness",
                options=["Ready & Focused", "Slightly Fatigued"],
                key="daily_feedback_selector",
            )
            st.session_state["daily_subjective_feedback"] = (
                "fatigue" if "Fatigued" in str(feedback_choice) else "focused"
            )
        with col_btn:
            if st.button("Refresh Plan", key="btn_refresh_plan"):
                st.session_state["force_regenerate_daily_plan"] = True
                st.rerun()

    if not has_session:
        st.warning("Start or resume an assessment session before opening an activity.")
