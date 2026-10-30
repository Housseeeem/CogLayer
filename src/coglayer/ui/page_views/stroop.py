"""Stroop task page for CogLayer UI.

Renders an interactive browser-side HTML/JS component capturing cognitive
flexibility and selective attention (interference control) under congruent
and incongruent color-naming conditions.

Non-clinical statement: This task measures reaction times and interference
resolution under standardized visual color-naming conditions. It is not
a clinical assessment.
"""

from __future__ import annotations

import httpx
import streamlit as st
import streamlit.components.v1 as components

from coglayer.ui.design import activity_frame_html


def render_stroop_page(api_url: str, user_id: str, session_id: str) -> None:
    """Render Stroop interactive cognitive task page."""
    st.header("Cognitive Lab: Stroop Task")

    st.markdown(
        """
        > **Non-clinical statement**: This task measures selective attention and
        > interference resolution (Stroop effect) under standardized visual conditions.
        > It is not a clinical assessment.

        **Instructions**:
        - You will see color names displayed on the screen.
        - **Your goal**: Identify the **INK COLOR** of the text, **NOT** what the word spells.
        - For example: if **RED** is written in **BLUE** ink, select **BLUE**.
        - Respond as quickly and accurately as possible. Timing is measured precisely.
        """
    )

    if st.button("← Back to Cognitive Lab", key="stroop_back_top"):
        st.session_state["page"] = "lab"
        st.rerun()

    # Check if session already completed stroop
    if session_id:
        try:
            sess_resp = httpx.get(f"{api_url}/v1/assessment/sessions/{session_id}", timeout=5.0)
            if sess_resp.status_code == 200:
                session_data = sess_resp.json()
                if "stroop" in session_data.get("completed_tasks", []):
                    st.success("✅ Stroop task is already completed for this session.")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(
                            "Return to Cognitive Lab", key="stroop_ret_comp", type="primary"
                        ):
                            st.session_state["page"] = "lab"
                            st.rerun()
                    with col2:
                        if st.button("View Cognitive Profile", key="stroop_view_prof"):
                            st.session_state["page"] = "profile"
                            st.rerun()
                    return
        except Exception as e:
            st.warning(f"Could not reach API to check session status: {e}")

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
          min-height: 520px;
          margin: 0;
          user-select: none;
        }}
        #stimulus-box {{
          width: 320px;
          height: 180px;
          background: #1f2937;
          border: 2px solid #374151;
          border-radius: 16px;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 20px auto;
          font-size: 52px;
          font-weight: 900;
          letter-spacing: 3px;
          box-shadow: 0 4px 20px rgba(0,0,0,0.4);
          transition: transform 0.05s ease;
        }}
        .color-palette {{
          display: grid;
          grid-template-columns: repeat(2, 140px);
          gap: 12px;
          margin-top: 10px;
        }}
        .color-btn {{
          padding: 16px;
          font-size: 18px;
          font-weight: 700;
          border-radius: 10px;
          border: none;
          cursor: pointer;
          color: #ffffff;
          transition: transform 0.1s, opacity 0.1s;
        }}
        .color-btn:hover {{ transform: scale(1.03); }}
        .color-btn:active {{ transform: scale(0.97); }}
        .btn-red {{ background: #ef4444; }}
        .btn-green {{ background: #10b981; }}
        .btn-blue {{ background: #3b82f6; }}
        .btn-yellow {{ background: #f59e0b; color: #111827; }}
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
          margin-top: 14px;
          font-size: 15px;
          color: #9ca3af;
          min-height: 22px;
        }}
        #progress {{
          margin-top: 6px;
          font-size: 13px;
          color: #6b7280;
        }}
      </style>
    </head>
    <body>
      <div id="stimulus-box">READY</div>

      <div class="color-palette" id="palette" style="display: none;">
        <button class="color-btn btn-red" onclick="handleColorClick('RED')">RED (R)</button>
        <button class="color-btn btn-green" onclick="handleColorClick('GREEN')">GREEN (G)</button>
        <button class="color-btn btn-blue" onclick="handleColorClick('BLUE')">BLUE (B)</button>
        <button class="color-btn btn-yellow" onclick="handleColorClick('YELLOW')">
          YELLOW (Y)
        </button>
      </div>

      <button id="action-btn" onclick="startStroop()">Start Stroop Task</button>
      <div id="status-msg">Click Start to begin practice.</div>
      <div id="progress"></div>

      <script>
        const API_URL = "{api_url}";
        const USER_ID = "{user_id}";
        const SESSION_ID = "{session_id}";

        const stimulusBox = document.getElementById("stimulus-box");
        const palette = document.getElementById("palette");
        const actionBtn = document.getElementById("action-btn");
        const statusMsg = document.getElementById("status-msg");
        const progressDiv = document.getElementById("progress");

        const colorMap = {{
          "RED": "#ef4444",
          "GREEN": "#10b981",
          "BLUE": "#3b82f6",
          "YELLOW": "#f59e0b"
        }};

        // Practice (4 trials: 2 congruent, 2 incongruent)
        // Scored (16 trials: 8 congruent, 8 incongruent, balanced)
        const trialsSequence = [
          // Practice
          {{ word: "RED", ink: "RED", condition: "congruent", isPractice: true }},
          {{ word: "BLUE", ink: "GREEN", condition: "incongruent", isPractice: true }},
          {{ word: "YELLOW", ink: "YELLOW", condition: "congruent", isPractice: true }},
          {{ word: "GREEN", ink: "RED", condition: "incongruent", isPractice: true }},
          // Scored Trials
          {{ word: "RED", ink: "RED", condition: "congruent" }},
          {{ word: "BLUE", ink: "YELLOW", condition: "incongruent" }},
          {{ word: "GREEN", ink: "GREEN", condition: "congruent" }},
          {{ word: "YELLOW", ink: "BLUE", condition: "incongruent" }},
          {{ word: "BLUE", ink: "BLUE", condition: "congruent" }},
          {{ word: "RED", ink: "GREEN", condition: "incongruent" }},
          {{ word: "YELLOW", ink: "YELLOW", condition: "congruent" }},
          {{ word: "GREEN", ink: "RED", condition: "incongruent" }},
          {{ word: "RED", ink: "BLUE", condition: "incongruent" }},
          {{ word: "GREEN", ink: "GREEN", condition: "congruent" }},
          {{ word: "YELLOW", ink: "RED", condition: "incongruent" }},
          {{ word: "BLUE", ink: "BLUE", condition: "congruent" }},
          {{ word: "RED", ink: "RED", condition: "congruent" }},
          {{ word: "GREEN", ink: "YELLOW", condition: "incongruent" }},
          {{ word: "BLUE", ink: "GREEN", condition: "incongruent" }},
          {{ word: "YELLOW", ink: "YELLOW", condition: "congruent" }}
        ];

        let currentIdx = -1;
        let stimulusOnset = 0;
        let waitingForResponse = false;
        let trialTimer = null;
        const recordedTrials = [];

        function startStroop() {{
          actionBtn.style.display = "none";
          palette.style.display = "grid";
          currentIdx = -1;
          runNextTrial();
        }}

        function runNextTrial() {{
          currentIdx++;
          if (currentIdx >= trialsSequence.length) {{
            finishStroop();
            return;
          }}

          const trial = trialsSequence[currentIdx];
          progressDiv.innerText = trial.isPractice
            ? `Practice trial ${{currentIdx + 1}} of 4`
            : `Scored trial ${{currentIdx - 3}} of ${{trialsSequence.length - 4}}`;

          // Fixation cross (500ms)
          waitingForResponse = false;
          stimulusBox.style.color = "#9ca3af";
          stimulusBox.innerText = "+";
          statusMsg.innerText = "Focus on the ink color...";

          setTimeout(() => {{
            showStimulus(trial);
          }}, 500);
        }}

        function showStimulus(trial) {{
          stimulusBox.style.color = colorMap[trial.ink];
          stimulusBox.innerText = trial.word;
          stimulusOnset = performance.now();
          waitingForResponse = true;

          // Max timeout per trial: 3000ms
          trialTimer = setTimeout(() => {{
            if (waitingForResponse) {{
              // Timed out omission
              recordResponse(null, 3000.0, true);
            }}
          }}, 3000);
        }}

        function handleColorClick(selectedColor) {{
          if (!waitingForResponse) return;
          clearTimeout(trialTimer);
          const rt = performance.now() - stimulusOnset;
          recordResponse(selectedColor, rt, false);
        }}

        window.addEventListener("keydown", (e) => {{
          if (!waitingForResponse) return;
          const key = e.key.toUpperCase();
          if (key === "R" || key === "1") handleColorClick("RED");
          else if (key === "G" || key === "2") handleColorClick("GREEN");
          else if (key === "B" || key === "3") handleColorClick("BLUE");
          else if (key === "Y" || key === "4") handleColorClick("YELLOW");
        }});

        function recordResponse(color, rt, isTimeout) {{
          waitingForResponse = false;
          const trial = trialsSequence[currentIdx];

          if (!trial.isPractice) {{
            recordedTrials.push({{
              stimulus: trial.word,
              expected: trial.ink,
              response: color,
              condition: trial.condition,
              rt_ms: rt,
              timestamp: new Date().toISOString(),
              valid: !isTimeout
            }});
          }}

          stimulusBox.style.color = "#9ca3af";
          stimulusBox.innerText = "";
          statusMsg.innerText = "";

          // 400ms inter-stimulus interval
          setTimeout(runNextTrial, 400);
        }}

        function finishStroop() {{
          palette.style.display = "none";
          stimulusBox.style.color = "#ffffff";
          stimulusBox.innerText = "DONE";
          progressDiv.innerText = "";
          statusMsg.innerText = "Uploading results to CogLayer...";

          fetch(`${{API_URL}}/v1/assessment/tasks/stroop/submit`, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              session_id: SESSION_ID,
              user_id: USER_ID,
              raw_result: {{ trials: recordedTrials }}
            }})
          }})
          .then(res => {{
            if (res.ok) {{
              statusMsg.innerText = "✅ Task completed and results saved! Click below to return.";
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

    components.html(activity_frame_html(html_code), height=560)

    col1, _ = st.columns([2, 3])
    with col1:
        if st.button("Check Status & Return to Lab", key="stroop_check_btn", type="primary"):
            st.session_state["page"] = "lab"
            st.rerun()
