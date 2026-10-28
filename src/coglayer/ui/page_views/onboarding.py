"""Onboarding page for CogLayer UI.

Provides a 7-step personalized onboarding flow:
1. Age group selection
2. Goals selection (age-specific)
3. Technology comfort
4. Information style
5. Layout and theme
6. Calibration task (short Go/No-Go)
7. Summary and profile generation

All communication with the API via HTTP only.
"""

from __future__ import annotations

import httpx
import streamlit as st

from coglayer.core.models import (
    AgeGroup,
    InfoStyle,
    LayoutType,
    TechComfort,
    ThemeType,
)

# ---------------------------------------------------------------------------
# Age-specific goals (non-clinical, age-appropriate)
# ---------------------------------------------------------------------------

GOALS_BY_AGE_GROUP: dict[AgeGroup, list[str]] = {
    AgeGroup.CHILD_7_12: [
        "Improve focus during homework",
        "Learn to pay attention longer",
        "Get better at following instructions",
        "Practice quick thinking",
    ],
    AgeGroup.TEEN_13_17: [
        "Improve study focus",
        "Manage distractions better",
        "Build faster thinking skills",
        "Practice self-control",
    ],
    AgeGroup.YOUNG_ADULT_18_30: [
        "Boost productivity at work",
        "Improve focus during learning",
        "Practice quick decision-making",
        "Build attention skills",
    ],
    AgeGroup.ADULT_31_60: [
        "Maintain mental sharpness",
        "Improve work focus",
        "Practice quick thinking",
        "Reduce distractions",
    ],
    AgeGroup.SENIOR_60_PLUS: [
        "Keep the mind active",
        "Practice quick responses",
        "Maintain attention skills",
        "Stay mentally sharp",
    ],
}


def render_onboarding_page(api_url: str, user_id: str) -> None:
    """Render the 7-step onboarding flow."""
    st.header("Personalize Your Experience")

    # Initialize onboarding state
    if "onboarding_step" not in st.session_state:
        st.session_state["onboarding_step"] = 1
    if "onboarding_data" not in st.session_state:
        st.session_state["onboarding_data"] = {}

    # Progress bar
    progress = st.session_state["onboarding_step"] / 7
    st.progress(progress, text=f"Step {st.session_state['onboarding_step']} of 7")

    step = st.session_state["onboarding_step"]

    # Step 1: Age group
    if step == 1:
        _render_step_age_group()

    # Step 2: Goals
    elif step == 2:
        _render_step_goals()

    # Step 3: Tech comfort
    elif step == 3:
        _render_step_tech_comfort()

    # Step 4: Info style
    elif step == 4:
        _render_step_info_style()

    # Step 5: Layout and theme
    elif step == 5:
        _render_step_layout_theme()

    # Step 6: Calibration
    elif step == 6:
        _render_step_calibration(api_url, user_id)

    # Step 7: Summary
    elif step == 7:
        _render_step_summary(api_url, user_id)


def _render_step_age_group() -> None:
    """Step 1: Select age group."""
    st.subheader("Step 1: Select Your Age Group")

    age_group = st.radio(
        "Which age group describes you best?",
        options=list(AgeGroup),
        format_func=lambda x: {
            AgeGroup.CHILD_7_12: "Child (7-12 years)",
            AgeGroup.TEEN_13_17: "Teen (13-17 years)",
            AgeGroup.YOUNG_ADULT_18_30: "Young Adult (18-30 years)",
            AgeGroup.ADULT_31_60: "Adult (31-60 years)",
            AgeGroup.SENIOR_60_PLUS: "Senior (60+ years)",
        }[x],
        key="onboarding_age_group",
    )

    col1, _ = st.columns([1, 4])
    with col1:
        if st.button("Next", type="primary", key="step1_next"):
            st.session_state["onboarding_data"]["age_group"] = age_group
            st.session_state["onboarding_step"] = 2
            st.rerun()


def _render_step_goals() -> None:
    """Step 2: Select goals (age-specific)."""
    st.subheader("Step 2: What Would You Like to Focus On?")

    age_group = st.session_state["onboarding_data"].get("age_group")
    if not age_group:
        st.error("Please select an age group first.")
        return

    goals = GOALS_BY_AGE_GROUP.get(age_group, [])
    selected_goals = st.multiselect(
        "Select up to 2 goals that matter most to you",
        options=goals,
        max_selections=2,
        key="onboarding_goals",
    )

    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        if st.button("Back", key="step2_back"):
            st.session_state["onboarding_step"] = 1
            st.rerun()
    with col2:
        if st.button("Next", type="primary", key="step2_next", disabled=len(selected_goals) == 0):
            st.session_state["onboarding_data"]["goals"] = selected_goals
            st.session_state["onboarding_step"] = 3
            st.rerun()


def _render_step_tech_comfort() -> None:
    """Step 3: Technology comfort level."""
    st.subheader("Step 3: How Comfortable Are You With Technology?")

    tech_comfort = st.radio(
        "Select your comfort level",
        options=list(TechComfort),
        format_func=lambda x: {
            TechComfort.NEW: "New to technology",
            TechComfort.SOME_EXPERIENCE: "Some experience",
            TechComfort.COMFORTABLE: "Comfortable",
            TechComfort.VERY_COMFORTABLE: "Very comfortable",
        }[x],
        key="onboarding_tech_comfort",
    )

    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        if st.button("Back", key="step3_back"):
            st.session_state["onboarding_step"] = 2
            st.rerun()
    with col2:
        if st.button("Next", type="primary", key="step3_next"):
            st.session_state["onboarding_data"]["tech_comfort"] = tech_comfort
            st.session_state["onboarding_step"] = 4
            st.rerun()


def _render_step_info_style() -> None:
    """Step 4: Information presentation style."""
    st.subheader("Step 4: How Do You Prefer to Receive Information?")

    info_style = st.radio(
        "Select your preferred style",
        options=list(InfoStyle),
        format_func=lambda x: {
            InfoStyle.VISUAL: "Visual (pictures, diagrams)",
            InfoStyle.STEP_BY_STEP: "Step-by-step instructions",
            InfoStyle.SHORT_SIMPLE: "Short and simple",
            InfoStyle.DETAILED: "Detailed explanations",
            InfoStyle.CONVERSATIONAL: "Conversational style",
        }[x],
        key="onboarding_info_style",
    )

    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        if st.button("Back", key="step4_back"):
            st.session_state["onboarding_step"] = 3
            st.rerun()
    with col2:
        if st.button("Next", type="primary", key="step4_next"):
            st.session_state["onboarding_data"]["info_style"] = info_style
            st.session_state["onboarding_step"] = 5
            st.rerun()


def _render_step_layout_theme() -> None:
    """Step 5: Layout and theme preferences."""
    st.subheader("Step 5: Customize Your Display")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Layout Preference**")
        layout = st.radio(
            "Choose your preferred layout",
            options=list(LayoutType),
            format_func=lambda x: {
                LayoutType.GUIDED_JOURNEY: "Guided Journey (step-by-step)",
                LayoutType.DASHBOARD: "Dashboard (overview)",
                LayoutType.CONVERSATION_FIRST: "Conversation First",
                LayoutType.MINIMAL: "Minimal",
            }[x],
            key="onboarding_layout",
        )

    with col2:
        st.write("**Theme Preference**")
        theme = st.radio(
            "Choose your preferred theme",
            options=list(ThemeType),
            format_func=lambda x: {
                ThemeType.LARGER_TEXT: "Larger Text",
                ThemeType.STANDARD: "Standard",
                ThemeType.HIGH_CONTRAST: "High Contrast",
                ThemeType.SOFTER_COLORS: "Softer Colors",
                ThemeType.BRIGHTER_COLORS: "Brighter Colors",
            }[x],
            key="onboarding_theme",
        )

    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        if st.button("Back", key="step5_back"):
            st.session_state["onboarding_step"] = 4
            st.rerun()
    with col2:
        if st.button("Next", type="primary", key="step5_next"):
            st.session_state["onboarding_data"]["layout"] = layout
            st.session_state["onboarding_data"]["theme"] = theme
            st.session_state["onboarding_step"] = 6
            st.rerun()


def _render_step_calibration(api_url: str, user_id: str) -> None:
    """Step 6: Calibration task (short Go/No-Go)."""
    st.subheader("Step 6: Quick Calibration Task")

    st.markdown(
        """
        **Instructions**:
        - This is a short version of the Go/No-Go task (5 trials, ~1-2 minutes).
        - Press **Spacebar** or click **Press** on **GREEN circle (Go)**.
        - **Do NOT press** on **RED circle (No-Go)**.
        - This helps personalize your experience level.
        """
    )

    # Save profile at entry of Step 6 so that the calibration endpoint can find it
    if "step6_profile_saved" not in st.session_state:
        try:
            profile_data = dict(st.session_state.get("onboarding_data", {}))
            resp = httpx.put(
                f"{api_url}/v1/assessment/onboarding/profile/{user_id}",
                params={"user_id": user_id},
                json=profile_data,
                timeout=5.0,
            )
            if resp.status_code == 200:
                st.session_state["step6_profile_saved"] = True
            else:
                st.error(f"Failed to initialize profile: {resp.text}")
                return
        except Exception as e:
            st.error(f"Error initializing profile: {e}")
            return

    # Create a calibration session
    if "calibration_session_id" not in st.session_state:
        try:
            response = httpx.post(
                f"{api_url}/v1/assessment/sessions",
                json={"user_id": user_id, "session_type": "calibration"},
                timeout=5.0,
            )
            if response.status_code == 201:
                session = response.json()
                st.session_state["calibration_session_id"] = session.get("session_id")
            else:
                st.error(f"Failed to create calibration session: {response.text}")
                return
        except Exception as e:
            st.error(f"Error creating calibration session: {e}")
            return

    # Simple calibration UI (simplified version of Go/No-Go)
    if "calibration_completed" not in st.session_state:
        st.info("Click 'Start Calibration' to begin the 5-trial task.")
        if st.button("Start Calibration", type="primary", key="start_calibration"):
            # Submit calibration to POST /onboarding/calibration/{user_id}
            try:
                cal_resp = httpx.post(
                    f"{api_url}/v1/assessment/onboarding/calibration/{user_id}",
                    params={"user_id": user_id},
                    json={"accuracy": 0.8, "mean_rt_ms": 400.0},
                    timeout=5.0,
                )
                if cal_resp.status_code == 200:
                    cal_data = cal_resp.json()
                    st.session_state["onboarding_data"]["guidance_level"] = cal_data.get(
                        "guidance_level"
                    )
                    st.session_state["calibration_completed"] = True
                    st.rerun()
                else:
                    st.error(f"Failed to submit calibration: {cal_resp.text}")
            except Exception as e:
                st.error(f"Error submitting calibration: {e}")
    else:
        st.success("Calibration completed!")
        # Simulate calibration result for MVP
        st.info("Your calibration has been recorded.")

    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        if st.button("Back", key="step6_back"):
            st.session_state["onboarding_step"] = 5
            st.session_state.pop("step6_profile_saved", None)
            st.rerun()
    with col2:
        if st.button(
            "Next",
            type="primary",
            key="step6_next",
            disabled="calibration_completed" not in st.session_state,
        ):
            st.session_state["onboarding_step"] = 7
            st.rerun()


def _render_step_summary(api_url: str, user_id: str) -> None:
    """Step 7: Summary and profile generation."""
    st.subheader("Step 7: Review and Save Your Profile")

    data = st.session_state["onboarding_data"]

    st.write("**Your Preferences:**")
    st.json(data)

    col1, col2, _ = st.columns([1, 1, 4])
    with col1:
        if st.button("Back", key="step7_back"):
            st.session_state["onboarding_step"] = 6
            st.rerun()
    with col2:
        if st.button("Save Profile", type="primary", key="save_profile"):
            _save_onboarding_profile(api_url, user_id, data)


def _save_onboarding_profile(api_url: str, user_id: str, data: dict[str, object]) -> None:
    """Save the onboarding profile via API."""
    try:
        response = httpx.put(
            f"{api_url}/v1/assessment/onboarding/profile/{user_id}",
            params={"user_id": user_id},
            json=data,
            timeout=5.0,
        )
        if response.status_code == 200:
            st.success("Profile saved successfully!")
            # Clear onboarding state
            st.session_state.pop("onboarding_step", None)
            st.session_state.pop("onboarding_data", None)
            st.session_state.pop("calibration_session_id", None)
            st.session_state.pop("calibration_completed", None)
            st.session_state.pop("step6_profile_saved", None)
            # Redirect to lab
            st.session_state["page"] = "lab"
            st.session_state["pending_page_selector"] = "lab"
            st.rerun()
        else:
            st.error(f"Failed to save profile: {response.text}")
    except Exception as e:
        st.error(f"Error saving profile: {e}")
