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

from typing import Final

import httpx
import streamlit as st
import streamlit.components.v1 as components

from coglayer.core.models import (
    AgeGroup,
    GuidanceLevel,
    InfoStyle,
    LayoutType,
    TechComfort,
    ThemeType,
)
from coglayer.ui.api import create_assessment_session
from coglayer.ui.design import activity_frame_html

# ---------------------------------------------------------------------------
# Calibration parameters (matches onboarding.calibration.CALIBRATION_N_TRIALS)
# ---------------------------------------------------------------------------

CALIBRATION_N_TRIALS: Final[int] = 5

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


def _build_calibration_go_no_go_html(api_url: str, user_id: str, session_id: str) -> str:
    """Build interactive HTML/JS component for the 5-trial calibration Go/No-Go variant.

    Reuses the layout, styling, and timing mechanism from ui/page_views/go_no_go.py.
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          background: #0e1117;
          color: #ffffff;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          min-height: 480px;
          margin: 0;
          user-select: none;
        }}
        #stimulus-box {{
          width: 200px;
          height: 200px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 28px;
          font-weight: bold;
          margin: 20px auto;
          box-shadow: 0 4px 20px rgba(0,0,0,0.5);
          transition: transform 0.05s ease;
        }}
        .go {{ background: #10b981; color: #ffffff; }}
        .nogo {{ background: #ef4444; color: #ffffff; }}
        .blank {{ background: #1f2937; border: 2px dashed #4b5563; }}
        .fixation {{ background: #1f2937; color: #9ca3af; font-size: 40px; }}
        #action-btn {{
          background: #3b82f6;
          color: white;
          border: none;
          padding: 14px 40px;
          font-size: 20px;
          font-weight: 600;
          border-radius: 8px;
          cursor: pointer;
          margin-top: 20px;
        }}
        #action-btn:hover {{ background: #2563eb; }}
        #status-msg {{
          margin-top: 15px;
          font-size: 16px;
          color: #9ca3af;
          min-height: 24px;
        }}
        #progress {{
          margin-top: 10px;
          font-size: 14px;
          color: #6b7280;
        }}
      </style>
    </head>
    <body>
      <div id="stimulus-box" class="blank">READY</div>
      <button id="action-btn">Start Calibration</button>
      <div id="status-msg">Press Start or hit Spacebar to begin.</div>
      <div id="progress"></div>

      <script>
        const API_URL = "{api_url}";
        const USER_ID = "{user_id}";
        const SESSION_ID = "{session_id}";

        const stimulusBox = document.getElementById("stimulus-box");
        const actionBtn = document.getElementById("action-btn");
        const statusMsg = document.getElementById("status-msg");
        const progressDiv = document.getElementById("progress");

        // Exactly 5 scored trials for calibration (4 Go, 1 No-Go)
        const trials = [];
        const trialSequence = [
          {{ type: "go" }},
          {{ type: "go" }},
          {{ type: "nogo" }},
          {{ type: "go" }},
          {{ type: "go" }}
        ];

        let state = "idle";
        let currentTrialIndex = -1;
        let stimulusOnset = 0;
        let responseRecorded = false;
        let currentTrialTimer = null;

        function recordResponse() {{
          if (state !== "stimulus" || responseRecorded) return;
          responseRecorded = true;
          const rt = performance.now() - stimulusOnset;
          const trial = trialSequence[currentTrialIndex];
          trials.push({{
            stimulus: trial.type,
            expected: trial.type === "go" ? "press" : "inhibit",
            response: "press",
            rt_ms: rt,
            timestamp: new Date().toISOString()
          }});
          stimulusBox.style.transform = "scale(0.95)";
          setTimeout(() => {{ stimulusBox.style.transform = "scale(1)"; }}, 100);
        }}

        window.addEventListener("keydown", (e) => {{
          if (e.code === "Space") {{
            e.preventDefault();
            if (state === "idle") startExperiment();
            else recordResponse();
          }}
        }});

        actionBtn.addEventListener("click", () => {{
          if (state === "idle") startExperiment();
          else recordResponse();
        }});

        function startExperiment() {{
          state = "running";
          actionBtn.innerText = "PRESS (SPACE)";
          currentTrialIndex = -1;
          nextTrial();
        }}

        function nextTrial() {{
          currentTrialIndex++;
          if (currentTrialIndex >= trialSequence.length) {{
            finishExperiment();
            return;
          }}

          const trial = trialSequence[currentTrialIndex];
          progressDiv.innerText = `Calibration trial ${{currentTrialIndex + 1}} of 5`;

          state = "fixation";
          stimulusBox.className = "fixation";
          stimulusBox.innerText = "+";
          statusMsg.innerText = "Watch carefully...";

          setTimeout(() => {{
            showStimulus(trial);
          }}, 500);
        }}

        function showStimulus(trial) {{
          state = "stimulus";
          responseRecorded = false;
          stimulusOnset = performance.now();

          stimulusBox.className = trial.type;
          stimulusBox.innerText = trial.type === "go" ? "GO" : "NO-GO";

          // Stimulus visible for 900ms
          currentTrialTimer = setTimeout(() => {{
            if (!responseRecorded) {{
              trials.push({{
                stimulus: trial.type,
                expected: trial.type === "go" ? "press" : "inhibit",
                response: null,
                rt_ms: 0.0,
                timestamp: new Date().toISOString()
              }});
            }}
            state = "isi";
            stimulusBox.className = "blank";
            stimulusBox.innerText = "";
            setTimeout(nextTrial, 800);
          }}, 900);
        }}

        function finishExperiment() {{
          state = "finished";
          stimulusBox.className = "blank";
          stimulusBox.innerText = "DONE";
          actionBtn.style.display = "none";
          statusMsg.innerText = "Computing calibration metrics...";

          // Calculate accuracy and mean_rt_ms from the 5 trials
          let correctCount = 0;
          let goRtSum = 0;
          let correctGoCount = 0;

          for (let i = 0; i < trials.length; i++) {{
            const t = trials[i];
            const isCorrect = (t.stimulus === "go" && t.response === "press") ||
              (t.stimulus === "nogo" && t.response === null);
            if (isCorrect) {{
              correctCount++;
              if (t.stimulus === "go" && t.rt_ms > 0) {{
                goRtSum += t.rt_ms;
                correctGoCount++;
              }}
            }}
          }}

          const accuracy = trials.length > 0 ? (correctCount / trials.length) : 0.0;
          const meanRtMs = correctGoCount > 0 ? (goRtSum / correctGoCount) : 0.0;

          // 1. Send accuracy and mean_rt_ms to POST /onboarding/calibration/{user_id}
          const calUrl = `${{API_URL}}/v1/assessment/onboarding/calibration/${{USER_ID}}` +
            `?user_id=${{USER_ID}}`;
          fetch(calUrl, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              accuracy: accuracy,
              mean_rt_ms: meanRtMs
            }})
          }})
          .then(res => {{
            if (!res.ok) {{
              return res.text().then(t => {{ throw new Error(t); }});
            }}
            return res.json();
          }})
          .then(data => {{
            // 2. Also record trials in the assessment session
            fetch(`${{API_URL}}/v1/assessment/tasks/go_no_go/submit`, {{
              method: "POST",
              headers: {{ "Content-Type": "application/json" }},
              body: JSON.stringify({{
                session_id: SESSION_ID,
                user_id: USER_ID,
                raw_result: {{ trials: trials }}
              }})
            }}).catch(() => {{}});

            statusMsg.innerText = "✅ Calibration complete! Click 'Check Status & Continue' below.";
            progressDiv.innerText = "";
          }})
          .catch(err => {{
            statusMsg.innerText = "Calibration error: " + err.message;
          }});
        }}
      </script>
    </body>
    </html>
    """


def _render_step_calibration(api_url: str, user_id: str) -> None:
    """Step 6: Calibration task (short Go/No-Go variant)."""
    st.subheader("Step 6: Quick Calibration Task")

    st.markdown(
        """
        **Instructions**:
        - This is a short version of the Go/No-Go task (5 trials, ~30 seconds).
        - Press **Spacebar** or click **Press** as fast as possible on **GREEN circle (Go)**.
        - **Do NOT press** anything when you see a **RED circle (No-Go)**.
        - This helps personalize your coaching guidance level.
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

    # Create a calibration session with session_type="calibration"
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

    session_id = st.session_state["calibration_session_id"]
    age_group = st.session_state.get("onboarding_data", {}).get("age_group")
    is_adult = age_group in (
        AgeGroup.YOUNG_ADULT_18_30,
        AgeGroup.ADULT_31_60,
        AgeGroup.SENIOR_60_PLUS,
        "young_adult_18_30",
        "adult_31_60",
        "senior_60_plus",
    )

    if "calibration_completed" not in st.session_state:
        # Adults can skip calibration; default guidance level is "some"
        if is_adult:
            if st.button("Skip Calibration (Default: Balanced Guidance)", key="skip_calibration"):
                try:
                    put_resp = httpx.put(
                        f"{api_url}/v1/assessment/onboarding/profile/{user_id}",
                        params={"user_id": user_id},
                        json={
                            **st.session_state["onboarding_data"],
                            "guidance_level": GuidanceLevel.SOME.value,
                        },
                        timeout=5.0,
                    )
                    if put_resp.status_code == 200:
                        st.session_state["onboarding_data"]["guidance_level"] = (
                            GuidanceLevel.SOME.value
                        )
                        st.session_state["calibration_completed"] = True
                        st.rerun()
                    else:
                        st.error(f"Failed to update profile: {put_resp.text}")
                except Exception as e:
                    st.error(f"Error updating profile: {e}")

        # Note on reaction time precision in Streamlit:
        # Reaction time (RT) measurements are captured client-side in JavaScript using
        # performance.now(), which provides sub-millisecond precision. When rendered inside
        # Streamlit via components.html iframe, browser display refresh rates (~16.6ms at 60Hz)
        # and inter-frame event dispatching may introduce slight timing variability compared
        # to native desktop environments. In accordance with the non-clinical coaching protocol,
        # thresholds in calibration.py remain unchanged.
        html_code = _build_calibration_go_no_go_html(
            api_url=api_url,
            user_id=user_id,
            session_id=session_id,
        )
        components.html(activity_frame_html(html_code), height=520)

        col_check, _, _ = st.columns([2, 2, 2])
        with col_check:
            if st.button("Check Status & Continue", type="primary", key="check_cal_status"):
                try:
                    profile_resp = httpx.get(
                        f"{api_url}/v1/assessment/onboarding/profile/{user_id}",
                        params={"user_id": user_id},
                        timeout=5.0,
                    )
                    if profile_resp.status_code == 200:
                        profile_data = profile_resp.json()
                        guidance_level = profile_data.get("guidance_level")
                        if guidance_level:
                            st.session_state["calibration_completed"] = True
                            st.session_state["onboarding_data"]["guidance_level"] = guidance_level
                            st.rerun()
                        else:
                            st.info(
                                "Calibration submission is not yet detected. "
                                "Please complete the trials above."
                            )
                    else:
                        st.error(f"Could not retrieve profile: {profile_resp.text}")
                except Exception as e:
                    st.error(f"Error communicating with API: {e}")
    else:
        # Display obtained guidance level in non-clinical language
        guidance_level = st.session_state["onboarding_data"].get("guidance_level", "some")
        guidance_labels: dict[str, str] = {
            GuidanceLevel.MORE.value: "Supported Guidance (detailed step-by-step assistance)",
            GuidanceLevel.SOME.value: "Balanced Guidance (helpful pointers and structured prompts)",
            GuidanceLevel.MINIMAL.value: (
                "Autonomous Guidance (lightweight nudges and self-directed pacing)"
            ),
        }
        level_str = (
            guidance_level.value if hasattr(guidance_level, "value") else str(guidance_level)
        )
        label = guidance_labels.get(
            level_str, "Balanced Guidance (helpful pointers and structured prompts)"
        )
        st.success(f"Calibration completed! Assigned coaching style: **{label}**")

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
    """Save the onboarding profile via API and create an assessment session."""
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

            # Create an assessment session if one does not already exist
            existing_session_id = st.session_state.get("session_id")
            if not (isinstance(existing_session_id, str) and existing_session_id):
                try:
                    session_id = create_assessment_session(api_url, user_id)
                    if session_id:
                        st.session_state["session_id"] = session_id
                except httpx.HTTPError:
                    st.warning(
                        "Profile saved, but could not create an assessment session. "
                        "Use 'New Assessment Session' in the sidebar to start."
                    )

            # Redirect to lab
            st.session_state["page"] = "lab"
            st.session_state["pending_page_selector"] = "lab"
            st.rerun()
        else:
            st.error(f"Failed to save profile: {response.text}")
    except Exception as e:
        st.error(f"Error saving profile: {e}")
