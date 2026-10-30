"""Perception Lab task page for CogLayer UI.

Renders an interactive browser-side HTML/JS component capturing perceptual
bistability and switching rates on the Necker Cube, while explicitly documenting
unavailable experiments due to missing media assets.

Non-clinical statement: This task measures subjective perceptual report dynamics
and visual search times. It is not a clinical assessment.
"""

from __future__ import annotations

import httpx
import streamlit as st
import streamlit.components.v1 as components

from coglayer.ui.design import activity_frame_html


def render_perception_lab_page(api_url: str, user_id: str, session_id: str) -> None:
    """Render Perception Lab task page and stimuli audit."""
    st.header("Cognitive Lab: Perception Lab")

    st.markdown(
        """
        > **Non-clinical statement**: This task measures subjective perceptual report
        > dynamics under standardized observation epochs. It is not a clinical assessment.
        """
    )

    if st.button("← Back to Cognitive Lab", key="perc_back_top"):
        st.session_state["page"] = "lab"
        st.rerun()

    # Check if session already completed perception_lab
    if session_id:
        try:
            sess_resp = httpx.get(f"{api_url}/v1/assessment/sessions/{session_id}", timeout=5.0)
            if sess_resp.status_code == 200:
                session_data = sess_resp.json()
                if "perception_lab" in session_data.get("completed_tasks", []):
                    st.success("✅ Perception Lab task is already completed for this session.")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(
                            "Return to Cognitive Lab", key="perc_ret_comp", type="primary"
                        ):
                            st.session_state["page"] = "lab"
                            st.rerun()
                    with col2:
                        if st.button("View Cognitive Profile", key="perc_view_prof"):
                            st.session_state["page"] = "profile"
                            st.rerun()
                    return
        except Exception as e:
            st.warning(f"Could not reach API to check session status: {e}")

    tab_play, tab_audit = st.tabs(["Necker Cube Experiment", "Stimuli & Asset Audit"])

    with tab_audit:
        st.subheader("Perceptual Stimuli Status & Incomplete Experiments")
        st.caption(
            "Experiments lacking legally licensed media assets in the repository "
            "are disabled and not presented as fully functional."
        )

        st.table(
            [
                {
                    "Experiment": "Necker Cube Bistability",
                    "Status": "Available (Fully Functional)",
                    "Stimulus Type": "Vector SVG wireframe geometry",
                    "Asset Path": "Inline procedural SVG (legal, no external file)",
                    "Scoring Contract": "switch_rate, perceptual_stability",
                },
                {
                    "Experiment": "Rubin Vase Illusion",
                    "Status": "Unavailable (Missing Media Asset)",
                    "Stimulus Type": "Figure-ground bistable visual image",
                    "Asset Path": "src/coglayer/ui/static/rubin_vase.svg",
                    "Scoring Contract": "switch_rate (unscored in MVP)",
                },
                {
                    "Experiment": "Duck-Rabbit Illusion",
                    "Status": "Unavailable (Missing Media Asset)",
                    "Stimulus Type": "Ambiguous semantic drawing",
                    "Asset Path": "src/coglayer/ui/static/duck_rabbit.svg",
                    "Scoring Contract": "perceptual_switching (unscored in MVP)",
                },
                {
                    "Experiment": "My Wife and My Mother-in-Law",
                    "Status": "Unavailable (Missing Media Asset)",
                    "Stimulus Type": "Ambiguous age-perception figure",
                    "Asset Path": "src/coglayer/ui/static/wife_mother_in_law.png",
                    "Scoring Contract": "perceptual_stability (unscored in MVP)",
                },
                {
                    "Experiment": "Change Blindness (Flicker)",
                    "Status": "Unavailable (Missing Media Assets)",
                    "Stimulus Type": "Alternating scene pair with blank ISI",
                    "Asset Path": "src/coglayer/ui/static/flicker_a.png & flicker_b.png",
                    "Scoring Contract": "detection_rate, mean_rt_ms",
                },
            ]
        )

    with tab_play:
        st.markdown(
            """
            **Necker Cube Bistability Instructions**:
            - Look steadily at the wireframe cube below.
            - The Necker cube is an ambiguous figure whose 3D perspective flips spontaneously:
              either the lower-left face or the upper-right face appears in front.
            - Focus on the cube for **30 seconds**.
            - Every time your perception spontaneously **switches perspective**,
              click **Report Switch** (or press Spacebar).
            - Do not force switches intentionally; observe your spontaneous dynamics.
            """
        )

        html_code = f"""
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
            #cube-container {{
              width: 280px;
              height: 280px;
              background: #111827;
              border: 2px solid #374151;
              border-radius: 16px;
              display: flex;
              align-items: center;
              justify-content: center;
              margin: 15px auto;
              box-shadow: 0 4px 20px rgba(0,0,0,0.5);
              position: relative;
            }}
            svg {{
              stroke: #60a5fa;
              stroke-width: 3.5;
              fill: none;
              stroke-linecap: round;
              stroke-linejoin: round;
              filter: drop-shadow(0 0 8px rgba(96, 165, 250, 0.4));
            }}
            .switch-btn {{
              background: #2563eb;
              color: white;
              border: 2px solid #3b82f6;
              padding: 14px 36px;
              font-size: 18px;
              font-weight: 700;
              border-radius: 8px;
              cursor: pointer;
              transition: transform 0.08s, background 0.1s;
              margin-top: 10px;
            }}
            .switch-btn:hover {{ background: #1d4ed8; }}
            .switch-btn:active {{ transform: scale(0.96); }}
            #action-btn {{
              background: #3b82f6;
              color: white;
              border: none;
              padding: 12px 36px;
              font-size: 18px;
              font-weight: 600;
              border-radius: 8px;
              cursor: pointer;
              margin-top: 15px;
            }}
            #action-btn:hover {{ background: #2563eb; }}
            #status-msg {{
              margin-top: 12px;
              font-size: 15px;
              color: #9ca3af;
              min-height: 22px;
              text-align: center;
            }}
            #counter-badge {{
              font-size: 16px;
              font-weight: 700;
              color: #fbbf24;
              margin-top: 6px;
            }}
            #timer-display {{
              font-size: 14px;
              color: #6b7280;
              margin-top: 4px;
            }}
          </style>
        </head>
        <body>
          <div id="cube-container">
            <!-- Necker Cube: 2 overlapping squares (offset by 60px) + 4 connecting edges -->
            <svg width="220" height="220" viewBox="0 0 220 220">
              <!-- Front square: (30,70) to (150,190) -->
              <rect x="30" y="70" width="120" height="120" />
              <!-- Back square: (70,30) to (190,150) -->
              <rect x="70" y="30" width="120" height="120" stroke="#93c5fd" />
              <!-- Connecting edges -->
              <line x1="30" y1="70" x2="70" y2="30" />
              <line x1="150" y1="70" x2="190" y2="30" />
              <line x1="30" y1="190" x2="70" y2="150" />
              <line x1="150" y1="190" x2="190" y2="150" />
              <!-- Central fixation dot -->
              <circle cx="110" cy="110" r="4" fill="#fbbf24" stroke="none" />
            </svg>
          </div>

          <button id="switch-btn" class="switch-btn" style="display: none;"
                  onclick="reportSwitch()">
            ⚡ Report Perceptual Switch (Space)
          </button>

          <button id="action-btn" onclick="startObservation()">Start 30-Second Observation</button>
          <div id="counter-badge"></div>
          <div id="timer-display"></div>
          <div id="status-msg">Click Start to begin.</div>

          <script>
            const API_URL = "{api_url}";
            const USER_ID = "{user_id}";
            const SESSION_ID = "{session_id}";
            const TOTAL_DURATION_SEC = 30;

            const switchBtn = document.getElementById("switch-btn");
            const actionBtn = document.getElementById("action-btn");
            const statusMsg = document.getElementById("status-msg");
            const counterBadge = document.getElementById("counter-badge");
            const timerDisplay = document.getElementById("timer-display");

            let switchCount = 0;
            let remainingSec = TOTAL_DURATION_SEC;
            let intervalTimer = null;
            let observationActive = false;

            function startObservation() {{
              actionBtn.style.display = "none";
              switchBtn.style.display = "inline-block";
              switchCount = 0;
              remainingSec = TOTAL_DURATION_SEC;
              observationActive = true;

              counterBadge.innerText = "Switches reported: 0";
              timerDisplay.innerText = `Time remaining: ${{remainingSec}}s`;
              statusMsg.innerText = "Observe the cube. Tap Report Switch on perspective flip.";

              intervalTimer = setInterval(() => {{
                remainingSec--;
                timerDisplay.innerText = `Time remaining: ${{remainingSec}}s`;
                if (remainingSec <= 0) {{
                  clearInterval(intervalTimer);
                  finishObservation();
                }}
              }}, 1000);
            }}

            function reportSwitch() {{
              if (!observationActive) return;
              switchCount++;
              counterBadge.innerText = `Switches reported: ${{switchCount}}`;

              // Quick visual pulse
              switchBtn.style.transform = "scale(0.95)";
              setTimeout(() => {{ switchBtn.style.transform = "scale(1)"; }}, 80);
            }}

            window.addEventListener("keydown", (e) => {{
              if (e.code === "Space" && observationActive) {{
                e.preventDefault();
                reportSwitch();
              }}
            }});

            function finishObservation() {{
              observationActive = false;
              switchBtn.style.display = "none";
              timerDisplay.innerText = "Observation epoch complete.";
              statusMsg.innerText = "Uploading results to CogLayer...";

              const trials = [{{
                stimulus: "necker_cube",
                expected: "REPORT",
                response: String(switchCount),
                rt_ms: TOTAL_DURATION_SEC * 1000.0,
                timestamp: new Date().toISOString(),
                valid: true
              }}];

              fetch(`${{API_URL}}/v1/assessment/tasks/perception_lab/submit`, {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify({{
                  session_id: SESSION_ID,
                  user_id: USER_ID,
                  raw_result: {{ trials: trials }}
                }})
              }})
              .then(res => {{
                if (res.ok) {{
                  statusMsg.innerText = `✅ Task completed! Switches: ${{switchCount}}. Saved.`;
                }} else {{
                  return res.text().then(t => {{ throw new Error(t); }});
                }}
              }})
              .catch(err => {{
                statusMsg.innerText = "Submission error: " + err.message;
              }});
            }}
          </script>
        </body>
        </html>
        """

        components.html(activity_frame_html(html_code), height=540)

        col1, _ = st.columns([2, 3])
        with col1:
            if st.button("Check Status & Return to Lab", key="perc_check_btn", type="primary"):
                st.session_state["page"] = "lab"
                st.rerun()
