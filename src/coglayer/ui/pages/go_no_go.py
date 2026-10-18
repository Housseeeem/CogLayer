"""Go/No-Go task page for CogLayer UI.

Renders an interactive browser-side HTML/JS component capturing sub-10ms RT
using performance.now() and posting directly to the FastAPI API.

Requirements: R-003.1, R-003.2, R-010.3
"""

from __future__ import annotations

import httpx
import streamlit as st
import streamlit.components.v1 as components


def render_go_no_go_page(api_url: str, user_id: str, session_id: str) -> None:
    """Render Go/No-Go interactive task page."""
    st.header("Task 1: Go / No-Go (Response Inhibition)")

    st.markdown(
        """
        **Instructions**:
        - Press **Spacebar** or click **Press** as fast as possible on **GREEN circle (Go)**.
        - **Do NOT press anything** when you see a **RED circle (No-Go)**.
        - The task will run a brief practice set, followed by the scored session.
        - All timing is recorded with sub-millisecond precision in your browser.
        """
    )

    # Check if session already completed go_no_go
    try:
        sess_resp = httpx.get(f"{api_url}/v1/assessment/sessions/{session_id}", timeout=5.0)
        if sess_resp.status_code == 200:
            session_data = sess_resp.json()
            if "go_no_go" in session_data.get("completed_tasks", []):
                st.success("✅ Go/No-Go task is completed for this session.")
                if st.button("Proceed to Task 2: Sequence Span", type="primary"):
                    st.session_state["page"] = "next"
                    st.rerun()
                return
    except Exception as e:
        st.warning(f"Could not reach API to check session status: {e}")

    decision_reason = st.session_state.get("decision_reason")
    if isinstance(decision_reason, str):
        st.info(decision_reason)

    # Self-contained HTML/JS task runner
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
      <button id="action-btn">Start Practice</button>
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

        // 5 practice trials, 20 scored trials (15 Go, 5 No-Go)
        const trials = [];
        const trialSequence = [
          // Practice
          {{ type: "go", isPractice: true }},
          {{ type: "go", isPractice: true }},
          {{ type: "nogo", isPractice: true }},
          {{ type: "go", isPractice: true }},
          {{ type: "nogo", isPractice: true }},
          // Scored
          {{ type: "go" }}, {{ type: "go" }}, {{ type: "nogo" }}, {{ type: "go" }},
          {{ type: "go" }}, {{ type: "nogo" }}, {{ type: "go" }}, {{ type: "go" }},
          {{ type: "go" }}, {{ type: "nogo" }}, {{ type: "go" }}, {{ type: "go" }},
          {{ type: "nogo" }}, {{ type: "go" }}, {{ type: "go" }}, {{ type: "go" }},
          {{ type: "nogo" }}, {{ type: "go" }}, {{ type: "go" }}, {{ type: "go" }}
        ];

        let state = "idle"; // idle, fixation, stimulus, isi, finished
        let currentTrialIndex = -1;
        let stimulusOnset = 0;
        let responseRecorded = false;
        let currentTrialTimer = null;

        function recordResponse() {{
          if (state !== "stimulus" || responseRecorded) return;
          responseRecorded = true;
          const rt = performance.now() - stimulusOnset;
          const trial = trialSequence[currentTrialIndex];
          if (!trial.isPractice) {{
            trials.push({{
              stimulus: trial.type,
              expected: trial.type === "go" ? "press" : "inhibit",
              response: "press",
              rt_ms: rt,
              timestamp: new Date().toISOString()
            }});
          }}
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
          progressDiv.innerText = trial.isPractice
            ? `Practice trial ${{currentTrialIndex + 1}} of 5`
            : `Scored trial ${{currentTrialIndex - 4}} of 20`;

          // Fixation cross (500ms)
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
            // Trial timed out
            if (!responseRecorded && !trial.isPractice) {{
              trials.push({{
                stimulus: trial.type,
                expected: trial.type === "go" ? "press" : "inhibit",
                response: null,
                rt_ms: 0.0,
                timestamp: new Date().toISOString()
              }});
            }}
            // ISI (800ms)
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
          statusMsg.innerText = "Uploading results to CogLayer...";

          fetch(`${{API_URL}}/v1/assessment/tasks/go_no_go/submit`, {{
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
              statusMsg.innerText = "✅ Task completed and results saved! Click Continue below.";
              progressDiv.innerText = "";
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

    components.html(html_code, height=520)

    # Polling / continuation control
    col1, _ = st.columns([2, 3])
    with col1:
        if st.button("Check Status & Continue", type="primary"):
            try:
                check_resp = httpx.get(
                    f"{api_url}/v1/assessment/sessions/{session_id}", timeout=5.0
                )
                if check_resp.status_code == 200:
                    session_info = check_resp.json()
                    if "go_no_go" in session_info.get("completed_tasks", []):
                        st.session_state["page"] = "next"
                        st.rerun()
                    else:
                        st.info(
                            "Task submission is not yet detected. Please complete the trials above."
                        )
            except Exception as e:
                st.error(f"Error communicating with API: {e}")
