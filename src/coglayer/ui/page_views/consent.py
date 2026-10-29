"""Consent page for CogLayer UI.

Displays informed consent screen and non-clinical disclaimer.
For minors (child/teen), requires guardian consent before proceeding.
Advances to onboarding upon consent.

Requirements: R-001.1, R-001.4, R-010.2
"""

from __future__ import annotations

import httpx
import streamlit as st


def render_consent_page(api_url: str, user_id: str) -> None:
    """Render the user consent screen with guardian consent for minors."""
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
                _check_experience_profile_and_redirect(api_url, user_id)
                return
    except Exception as exc:
        st.warning(f"Could not connect to API to verify consent status: {exc}")

    # Age group selection for guardian consent
    st.write("**Step 1: Select Age Group**")
    age_group = st.radio(
        "Which age group describes you best?",
        options=["adult_31_60", "young_adult_18_30", "senior_60_plus", "teen_13_17", "child_7_12"],
        format_func=lambda x: {
            "child_7_12": "Child (7-12 years)",
            "teen_13_17": "Teen (13-17 years)",
            "young_adult_18_30": "Young Adult (18-30 years)",
            "adult_31_60": "Adult (31-60 years)",
            "senior_60_plus": "Senior (60+ years)",
        }[x],
        key="consent_age_group",
    )

    # Guardian consent for minors
    if age_group in ("child_7_12", "teen_13_17"):
        st.warning("Guardian consent is required for minors.")
        guardian_id = st.text_input("Parent/Guardian Name or ID", key="guardian_id")
        guardian_consent = st.checkbox(
            "I am the parent/guardian and I consent to data collection for this minor",
            key="guardian_consent",
        )

        if not guardian_consent:
            st.error("Guardian consent is required to proceed.")
            return

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
            consent_payload: dict[str, object] = {"user_id": user_id}
            if age_group in ("child_7_12", "teen_13_17"):
                consent_payload["guardian_consent"] = True
                consent_payload["guardian_id"] = guardian_id or ""

            try:
                post_resp = httpx.post(
                    f"{api_url}/v1/assessment/consent",
                    json=consent_payload,
                    timeout=5.0,
                )
                if post_resp.status_code in (200, 201):
                    _check_experience_profile_and_redirect(api_url, user_id)
                else:
                    st.error(f"Failed to record consent: {post_resp.text}")
            except httpx.HTTPError as e:
                st.error(f"Error connecting to assessment API: {e}")


def _check_experience_profile_and_redirect(api_url: str, user_id: str) -> None:
    """Check if experience profile exists, redirect to onboarding if not."""
    try:
        profile_resp = httpx.get(
            f"{api_url}/v1/assessment/onboarding/profile/{user_id}",
            params={"user_id": user_id},
            timeout=5.0,
        )
        if profile_resp.status_code == 200:
            # Profile exists, go to lab
            st.session_state["page"] = "lab"
            st.session_state["pending_page_selector"] = "lab"
            st.rerun()
        elif profile_resp.status_code == 404:
            # No profile, go to onboarding
            st.session_state["page"] = "onboarding"
            st.rerun()
        else:
            st.error(f"Error checking profile: {profile_resp.text}")
    except Exception as e:
        st.warning(f"Could not check profile status: {e}")
        # Default to lab on error
        if st.button("Continue to Assessment", type="primary"):
            st.session_state["page"] = "lab"
            st.session_state["pending_page_selector"] = "lab"
            st.rerun()
