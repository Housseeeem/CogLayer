"""N-Back task page for CogLayer UI.

Renders an interactive browser-side HTML/JS component capturing continuous
working memory updating and monitoring using the N-back paradigm.

Non-clinical statement: This task measures performance on continuous stimulus
comparison under standardized timing. It is not a clinical assessment.
"""

from __future__ import annotations

import httpx
import streamlit as st
import streamlit.components.v1 as components


def render_n_back_page(api_url: str, user_id: str, session_id: str) -> None:
    """Render N-Back interactive cognitive task page."""
    st.header("Cognitive Lab: N-Back Task")

    st.markdown(
        """
        > **Non-clinical statement**: This task measures continuous stimulus
        > comparison and working memory updating. It is not a clinical assessment.

        **Instructions**:
        - A stream of letters will be shown one at a time.
        - For each letter, indicate whether it **matches the letter seen exactly N steps ago**.
        - Standard test level is **2-Back** (compare current letter with the one 2 steps earlier).
        - Example in 2-Back:
          - Letter 1: **B** (observe)
          - Letter 2: **K** (observe)
          - Letter 3: **B** → **MATCH!** (matches Letter 1, 2 steps ago)
          - Letter 4: **L** → **NO MATCH**
        - Press **MATCH** (or Spacebar) when it matches; click **NO MATCH** (or wait) otherwise.
        """
    )

    if st.button("← Back to Cognitive Lab", key="nback_back_top"):
        st.session_state["page"] = "lab"
        st.rerun()

    # Check if session already completed n_back
    if session_id:
        try:
            sess_resp = httpx.get(f"{api_url}/v1/assessment/sessions/{session_id}", timeout=5.0)
            if sess_resp.status_code == 200:
                session_data = sess_resp.json()
                if "n_back" in session_data.get("completed_tasks", []):
                    st.success("✅ N-Back task is already completed for this session.")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(
                            "Return to Cognitive Lab", key="nback_ret_comp", type="primary"
                        ):
                            st.session_state["page"] = "lab"
                            st.rerun()
                    with col2:
                        if st.button("View Cognitive Profile", key="nback_view_prof"):
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
          width: 220px;
          height: 180px;
          background: #1f2937;
          border: 2px solid #374151;
          border-radius: 16px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          margin: 15px auto;
          box-shadow: 0 4px 20px rgba(0,0,0,0.4);
          transition: border-color 0.1s ease;
        }}
        #letter-char {{
          font-size: 72px;
          font-weight: 900;
          color: #60a5fa;
        }}
        #n-badge {{
          font-size: 13px;
          font-weight: 700;
          letter-spacing: 1px;
          padding: 4px 12px;
          border-radius: 12px;
          background: rgba(96, 165, 250, 0.15);
          color: #93c5fd;
          border: 1px solid #3b82f6;
          margin-bottom: 4px;
        }}
        .button-bar {{
          display: flex;
          gap: 16px;
          margin-top: 15px;
        }}
        .resp-btn {{
          padding: 14px 28px;
          font-size: 18px;
          font-weight: 700;
          border-radius: 8px;
          border: none;
          cursor: pointer;
          transition: transform 0.08s, background 0.1s;
        }}
        .resp-btn:active {{ transform: scale(0.96); }}
        .btn-match {{
          background: #10b981;
          color: white;
        }}
        .btn-match:hover {{ background: #059669; }}
        .btn-nomatch {{
          background: #374151;
          color: #d1d5db;
          border: 1px solid #4b5563;
        }}
        .btn-nomatch:hover {{ background: #4b5563; }}
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
          text-align: center;
        }}
        #progress {{
          margin-top: 6px;
          font-size: 13px;
          color: #6b7280;
        }}
      </style>
    </head>
    <body>
      <div id="stimulus-box">
        <span id="n-badge">2-BACK</span>
        <div id="letter-char">READY</div>
      </div>

      <div class="button-bar" id="button-bar" style="display: none;">
        <button class="resp-btn btn-match" id="btn-match" onclick="handleResponse('MATCH')">
          MATCH (Space)
        </button>
        <button class="resp-btn btn-nomatch" id="btn-nomatch" onclick="handleResponse('NO_MATCH')">
          NO MATCH
        </button>
      </div>

      <button id="action-btn" onclick="startNBack()">Start 2-Back Task</button>
      <div id="status-msg">Click Start to begin continuous 2-Back testing.</div>
      <div id="progress"></div>

      <script>
        const API_URL = "{api_url}";
        const USER_ID = "{user_id}";
        const SESSION_ID = "{session_id}";
        const N = 2; // Default 2-back

        const stimulusBox = document.getElementById("stimulus-box");
        const letterChar = document.getElementById("letter-char");
        const buttonBar = document.getElementById("button-bar");
        const actionBtn = document.getElementById("action-btn");
        const statusMsg = document.getElementById("status-msg");
        const progressDiv = document.getElementById("progress");

        // Sequence of letters designed for 2-back:
        // Trial 0: B (first, cannot be target)
        // Trial 1: K (second, cannot be target)
        // Trial 2: B (target: matches trial 0!)
        // Trial 3: M (non-target)
        // Trial 4: B (non-target)
        // Trial 5: M (target: matches trial 3!)
        // Trial 6: T (non-target)
        // Trial 7: M (non-target)
        // Trial 8: T (target: matches trial 6!)
        // Trial 9: L (non-target)
        // Trial 10: X (non-target)
        // Trial 11: L (target: matches trial 9!)
        // Trial 12: H (non-target)
        // Trial 13: X (non-target)
        // Trial 14: H (target: matches trial 12!)
        // Trial 15: P (non-target)
        // Trial 16: Q (non-target)
        // Trial 17: P (target: matches trial 15!)
        // Trial 18: R (non-target)
        // Trial 19: R (lure 1-back: non-target for 2-back)
        // Trial 20: R (target: matches trial 18!)
        const stimuliSequence = [
          "B", "K", "B", "M", "B", "M", "T", "M", "T", "L",
          "X", "L", "H", "X", "H", "P", "Q", "P", "R", "R", "R"
        ];

        let currentIdx = -1;
        let stimulusOnset = 0;
        let responseGiven = false;
        let trialTimer = null;
        const recordedTrials = [];

        function startNBack() {{
          actionBtn.style.display = "none";
          buttonBar.style.display = "flex";
          currentIdx = -1;
          runNextTrial();
        }}

        function runNextTrial() {{
          currentIdx++;
          if (currentIdx >= stimuliSequence.length) {{
            finishNBack();
            return;
          }}

          const char = stimuliSequence[currentIdx];
          const isTarget = currentIdx >= N && char === stimuliSequence[currentIdx - N];

          progressDiv.innerText = currentIdx < N
            ? `Observation ${{currentIdx + 1}} of ${{N}} (memorize)`
            : `Trial ${{currentIdx - N + 1}} of ${{stimuliSequence.length - N}}`;

          // Brief fixation/blank (400ms)
          letterChar.innerText = "";
          stimulusBox.style.borderColor = "#374151";
          responseGiven = false;

          setTimeout(() => {{
            showStimulus(char, isTarget);
          }}, 400);
        }}

        function showStimulus(char, isTarget) {{
          letterChar.innerText = char;
          stimulusOnset = performance.now();
          responseGiven = false;

          if (currentIdx < N) {{
            statusMsg.innerText = `Memorizing letter ${{currentIdx + 1}} of ${{N}}...`;
          }} else {{
            statusMsg.innerText = `Does this match the letter from 2 steps ago?`;
          }}

          // Stimulus duration: 1800ms
          trialTimer = setTimeout(() => {{
            if (!responseGiven && currentIdx >= N) {{
              // No response -> record omission / NO_MATCH
              recordResult(isTarget, null, 1800.0, true);
            }}
            runNextTrial();
          }}, 1800);
        }}

        function handleResponse(respType) {{
          if (responseGiven || currentIdx < N) return;
          responseGiven = true;
          clearTimeout(trialTimer);

          const rt = performance.now() - stimulusOnset;
          const char = stimuliSequence[currentIdx];
          const isTarget = currentIdx >= N && char === stimuliSequence[currentIdx - N];

          recordResult(isTarget, respType, rt, false);

          stimulusBox.style.borderColor = respType === "MATCH" ? "#10b981" : "#3b82f6";
          setTimeout(runNextTrial, 200);
        }}

        window.addEventListener("keydown", (e) => {{
          if (e.code === "Space") {{
            e.preventDefault();
            handleResponse("MATCH");
          }}
        }});

        function recordResult(isTarget, response, rt, isOmission) {{
          const char = stimuliSequence[currentIdx];
          const expected = isTarget ? "MATCH" : "NO_MATCH";

          recordedTrials.push({{
            stimulus: char,
            is_target: isTarget,
            expected: expected,
            response: response,
            rt_ms: rt,
            timestamp: new Date().toISOString(),
            valid: !isOmission || !isTarget // Valid trial unless omission on target
          }});
        }}

        function finishNBack() {{
          buttonBar.style.display = "none";
          letterChar.innerText = "DONE";
          progressDiv.innerText = "";
          statusMsg.innerText = "Uploading results to CogLayer...";

          fetch(`${{API_URL}}/v1/assessment/tasks/n_back/submit`, {{
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

    components.html(html_code, height=560)

    col1, _ = st.columns([2, 3])
    with col1:
        if st.button("Check Status & Return to Lab", key="nback_check_btn", type="primary"):
            st.session_state["page"] = "lab"
            st.rerun()
