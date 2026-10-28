"""Streamlit demonstration of explicit IOI interaction opportunities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import streamlit as st

from coglayer.ui.api import get_ioi_score, record_ioi_event

_OPPORTUNITIES: tuple[tuple[str, str, str, str], ...] = (
    (
        "critical_verification",
        "verification_opportunity",
        "Critical verification",
        "When an answer is presented, did you verify an important claim before relying on it?",
    ),
    (
        "clarification",
        "clarification_opportunity",
        "Clarification",
        "When something was unclear, did you ask for clarification before continuing?",
    ),
    (
        "iteration",
        "iteration_opportunity",
        "Iteration",
        "When the first result was not enough, did you refine or revise the request?",
    ),
    (
        "autonomy",
        "autonomy_opportunity",
        "Autonomy",
        "When given a suggestion, did you make and record your own choice?",
    ),
    (
        "responsible_usage",
        "responsible_usage_opportunity",
        "Responsible usage",
        "Before using the result, did you check that it was appropriate for your purpose?",
    ),
)


def render_ioi_page(api_url: str, user_id: str, session_id: str) -> None:
    """Render explicit opportunities and the current IOI snapshot."""
    st.header("Experimental interaction index")
    st.caption(
        "This prototype records explicit choices in five interaction opportunities. "
        "It is not a validated measure of intelligence or general AI skill."
    )

    if not session_id:
        st.info("Start an assessment session before recording interaction observations.")
        return

    st.markdown(
        "An observation is recorded only when you submit a choice for an opportunity. "
        "Skipping an opportunity is not treated as a negative outcome."
    )
    for component, event_type, label, prompt in _OPPORTUNITIES:
        _render_opportunity(api_url, user_id, session_id, component, event_type, label, prompt)

    st.divider()
    st.subheader("Current score snapshot")
    try:
        snapshot = get_ioi_score(api_url, user_id, session_id)
    except (httpx.HTTPError, ValueError) as exc:
        st.error(f"Could not load the IOI snapshot: {exc}")
        return
    _render_snapshot(snapshot)


def _render_opportunity(
    api_url: str,
    user_id: str,
    session_id: str,
    component: str,
    event_type: str,
    label: str,
    prompt: str,
) -> None:
    """Render one opportunity and record only an explicit submitted outcome."""
    opportunity_key = f"ioi_opportunity_{session_id}_{component}"
    outcome_key = f"ioi_outcome_{session_id}_{component}"
    record_key = f"ioi_record_{session_id}_{component}"
    submitting_key = f"ioi_submitting_{session_id}_{component}"
    if opportunity_key not in st.session_state:
        st.session_state[opportunity_key] = str(uuid4())
    st.session_state.setdefault(submitting_key, False)
    opportunity_id = st.session_state[opportunity_key]

    with st.container(border=True):
        st.subheader(label)
        st.write(prompt)
        outcome = st.radio(
            "Your outcome",
            options=("Yes, I did this", "No, I did not do this"),
            key=outcome_key,
        )
        if st.button(
            "Record this opportunity",
            key=record_key,
            disabled=bool(st.session_state[submitting_key]),
        ):
            st.session_state[submitting_key] = True
            event: dict[str, Any] = {
                "event_id": str(uuid4()),
                "user_id": user_id,
                "session_id": session_id,
                "component": component,
                "event_type": event_type,
                "opportunity_id": opportunity_id,
                "behavior_observed": outcome == "Yes, I did this",
                "timestamp": datetime.now(UTC).isoformat(),
                "schema_version": "1.0",
                "metadata": {"source": "streamlit_ioi_page"},
            }
            try:
                result = record_ioi_event(api_url, event)
                if result.get("status") == "duplicate":
                    st.info("This opportunity was already recorded.")
                else:
                    st.session_state[opportunity_key] = str(uuid4())
                    st.success("Observation recorded.")
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 409:
                    st.info("This opportunity was already recorded.")
                else:
                    st.error(f"Could not record this observation: {exc}")
            except httpx.HTTPError as exc:
                st.error(f"Could not record this observation: {exc}")
            finally:
                st.session_state[submitting_key] = False


def _render_snapshot(snapshot: dict[str, Any]) -> None:
    """Render component evidence and the fixed-weight aggregate status."""
    status = snapshot.get("status")
    aggregate = snapshot.get("aggregate_score")
    if status == "AVAILABLE" and isinstance(aggregate, (int, float)):
        st.metric("Aggregate IOI", f"{aggregate * 100:.1f}%")
    else:
        st.warning("Overall score: INSUFFICIENT_EVIDENCE")

    components = snapshot.get("components", {})
    if not isinstance(components, dict):
        st.error("The IOI snapshot has an invalid component shape.")
        return
    for component, details in components.items():
        if not isinstance(details, dict):
            continue
        score = details.get("score")
        count = details.get("evidence_count", 0)
        sufficient = details.get("sufficient", False)
        score_text = (
            f"{float(score) * 100:.1f}%" if isinstance(score, (int, float)) else "unavailable"
        )
        suffix = "sufficient" if sufficient else "needs 3 valid observations"
        st.write(f"**{component.replace('_', ' ').title()}**: {score_text} — {count}/3, {suffix}")

    st.caption(
        "Weights are fixed product rules: critical verification 25%, clarification 20%, "
        "iteration 20%, autonomy 20%, responsible usage 15%. Results are experimental "
        "operational indicators and do not establish general ability."
    )
