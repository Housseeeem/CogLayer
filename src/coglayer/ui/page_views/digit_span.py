"""Digit Span task page for CogLayer UI.

Renders an interactive browser-side HTML/JS component capturing verbal
working memory via forward and backward digit span reproduction.

Non-clinical statement: This task measures performance on sequential digit recall
under standardized conditions. It is not a clinical assessment.
"""

from __future__ import annotations

import httpx
import streamlit as st
import streamlit.components.v1 as components


def render_digit_span_page(api_url: str, user_id: str, session_id: str) -> None:
    """Render Digit Span interactive cognitive task page."""
    st.header("Cognitive Lab: Digit Span")

    st.markdown(
        """
        > **Non-clinical statement**: This task measures performance on sequential digit
        > recall under standardized conditions. It is used as a proxy for verbal working-memory
        > capacity and is not a clinical assessment.

        **Instructions**:
        - A sequence of digits will appear on screen **one by one**.
        - Watch and memorize the sequence carefully.
        - Once the sequence disappears, enter the digits:
          - **Forward mode**: enter digits in the **exact same order** shown.
          - **Backward mode**: enter digits in **reverse order** (from last to first).
        - Sequences start short and increase in length.
        """
    )

    # Return button to Cognitive Lab
    if st.button("← Back to Cognitive Lab", key="ds_back_top"):
        st.session_state["page"] = "lab"
        st.rerun()

    # Check if session already completed digit_span
    if session_id:
        try:
            sess_resp = httpx.get(f"{api_url}/v1/assessment/sessions/{session_id}", timeout=5.0)
            if sess_resp.status_code == 200:
                session_data = sess_resp.json()
                if "digit_span" in session_data.get("completed_tasks", []):
                    st.success("✅ Digit Span task is already completed for this session.")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Return to Cognitive Lab", key="ds_ret_comp", type="primary"):
                            st.session_state["page"] = "lab"
                            st.rerun()
                    with col2:
                        if st.button("View Cognitive Profile", key="ds_view_prof"):
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
        #display-box {{
          width: 280px;
          height: 160px;
          background: #1f2937;
          border: 2px solid #374151;
          border-radius: 16px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          margin: 15px auto;
          box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        }}
        #digit-text {{
          font-size: 64px;
          font-weight: 800;
          color: #60a5fa;
          letter-spacing: 2px;
        }}
        #condition-badge {{
          font-size: 14px;
          font-weight: 600;
          text-transform: uppercase;
          padding: 4px 12px;
          border-radius: 20px;
          margin-bottom: 8px;
          background: #374151;
          color: #9ca3af;
        }}
        #condition-badge.forward {{
          background: rgba(16, 185, 129, 0.2);
          color: #34d399;
          border: 1px solid #10b981;
        }}
        #condition-badge.backward {{
          background: rgba(245, 158, 11, 0.2);
          color: #fbbf24;
          border: 1px solid #f59e0b;
        }}
        #input-container {{
          display: none;
          flex-direction: column;
          align-items: center;
          margin-top: 10px;
        }}
        #response-display {{
          width: 260px;
          height: 48px;
          background: #111827;
          border: 2px solid #4b5563;
          border-radius: 8px;
          font-size: 26px;
          letter-spacing: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #f3f4f6;
          margin-bottom: 12px;
          font-family: monospace;
        }}
        .keypad {{
          display: grid;
          grid-template-columns: repeat(3, 60px);
          gap: 8px;
        }}
        .key-btn {{
          background: #374151;
          color: white;
          border: 1px solid #4b5563;
          border-radius: 8px;
          padding: 12px 0;
          font-size: 20px;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.1s;
        }}
        .key-btn:hover {{ background: #4b5563; }}
        .key-btn.action {{ background: #2563eb; font-size: 15px; border-color: #3b82f6; }}
        .key-btn.action:hover {{ background: #1d4ed8; }}
        .key-btn.clear {{ background: #ef4444; font-size: 15px; border-color: #dc2626; }}
        .key-btn.clear:hover {{ background: #dc2626; }}
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
      <div id="display-box">
        <span id="condition-badge" class="forward">FORWARD</span>
        <div id="digit-text">READY</div>
      </div>

      <div id="input-container">
        <div id="response-display"></div>
        <div class="keypad">
          <button class="key-btn" onclick="pressKey('1')">1</button>
          <button class="key-btn" onclick="pressKey('2')">2</button>
          <button class="key-btn" onclick="pressKey('3')">3</button>
          <button class="key-btn" onclick="pressKey('4')">4</button>
          <button class="key-btn" onclick="pressKey('5')">5</button>
          <button class="key-btn" onclick="pressKey('6')">6</button>
          <button class="key-btn" onclick="pressKey('7')">7</button>
          <button class="key-btn" onclick="pressKey('8')">8</button>
          <button class="key-btn" onclick="pressKey('9')">9</button>
          <button class="key-btn clear" onclick="pressKey('C')">CLR</button>
          <button class="key-btn" onclick="pressKey('0')">0</button>
          <button class="key-btn action" onclick="submitResponse()">OK</button>
        </div>
      </div>

      <button id="action-btn" onclick="startTask()">Start Digit Span</button>
      <div id="status-msg">Press Start when you are ready.</div>
      <div id="progress"></div>

      <script>
        const API_URL = "{api_url}";
        const USER_ID = "{user_id}";
        const SESSION_ID = "{session_id}";

        const displayBox = document.getElementById("display-box");
        const digitText = document.getElementById("digit-text");
        const conditionBadge = document.getElementById("condition-badge");
        const inputContainer = document.getElementById("input-container");
        const responseDisplay = document.getElementById("response-display");
        const actionBtn = document.getElementById("action-btn");
        const statusMsg = document.getElementById("status-msg");
        const progressDiv = document.getElementById("progress");

        // Trial battery: practice (2 trials: 1 forward len 3, 1 backward len 3)
        // followed by scored trials (forward: 3, 4, 5, 6, 7; backward: 3, 4, 5, 6)
        const trialsSequence = [
          {{ digits: "482", condition: "forward", isPractice: true }},
          {{ digits: "619", condition: "backward", isPractice: true }},
          // Scored Forward
          {{ digits: "582", condition: "forward" }},
          {{ digits: "3947", condition: "forward" }},
          {{ digits: "62851", condition: "forward" }},
          {{ digits: "173942", condition: "forward" }},
          {{ digits: "8251936", condition: "forward" }},
          // Scored Backward
          {{ digits: "729", condition: "backward" }},
          {{ digits: "5184", condition: "backward" }},
          {{ digits: "29416", condition: "backward" }},
          {{ digits: "837251", condition: "backward" }}
        ];

        let currentIdx = -1;
        let enteredDigits = "";
        let responseStartTime = 0;
        let responseAllowed = false;
        const recordedTrials = [];

        function startTask() {{
          actionBtn.style.display = "none";
          currentIdx = -1;
          runNextTrial();
        }}

        function runNextTrial() {{
          currentIdx++;
          if (currentIdx >= trialsSequence.length) {{
            finishTask();
            return;
          }}

          const trial = trialsSequence[currentIdx];
          enteredDigits = "";
          responseDisplay.innerText = "";
          responseAllowed = false;
          inputContainer.style.display = "none";
          displayBox.style.display = "flex";

          conditionBadge.className = trial.condition;
          const pracSuffix = trial.isPractice ? " (PRACTICE)" : "";
          conditionBadge.innerText = trial.condition.toUpperCase() + pracSuffix;
          const totalScored = trialsSequence.length - 2;
          progressDiv.innerText = trial.isPractice
            ? `Practice trial ${{currentIdx + 1}} of 2`
            : `Trial ${{currentIdx - 1}}/${{totalScored}} (Len: ${{trial.digits.length}})`;

          statusMsg.innerText = trial.condition === "forward"
            ? "Memorize digits. You will reproduce them in FORWARD order."
            : "Memorize digits. You will reproduce them in REVERSE order.";

          digitText.innerText = "+";
          setTimeout(() => {{
            playDigits(trial.digits, 0);
          }}, 800);
        }}

        function playDigits(digitsStr, charIdx) {{
          if (charIdx >= digitsStr.length) {{
            // Digits finished: mask completely
            digitText.innerText = "• • •";
            setTimeout(() => {{
              beginInputPhase();
            }}, 600);
            return;
          }}

          digitText.innerText = digitsStr[charIdx];
          setTimeout(() => {{
            // brief blank between digits
            digitText.innerText = "";
            setTimeout(() => {{
              playDigits(digitsStr, charIdx + 1);
            }}, 200);
          }}, 900);
        }}

        function beginInputPhase() {{
          const trial = trialsSequence[currentIdx];
          digitText.innerText = "?";
          inputContainer.style.display = "flex";
          responseAllowed = true;
          responseStartTime = performance.now();
          statusMsg.innerText = trial.condition === "forward"
            ? "Enter digits in the SAME order as shown:"
            : "Enter digits in REVERSE order (from last to first):";
        }}

        function pressKey(key) {{
          if (!responseAllowed) return;
          if (key === "C") {{
            enteredDigits = "";
          }} else {{
            if (enteredDigits.length < 12) {{
              enteredDigits += key;
            }}
          }}
          responseDisplay.innerText = enteredDigits;
        }}

        window.addEventListener("keydown", (e) => {{
          if (!responseAllowed) return;
          if (e.key >= "0" && e.key <= "9") {{
            pressKey(e.key);
          }} else if (e.key === "Backspace") {{
            enteredDigits = enteredDigits.slice(0, -1);
            responseDisplay.innerText = enteredDigits;
          }} else if (e.key === "Enter") {{
            submitResponse();
          }}
        }});

        function submitResponse() {{
          if (!responseAllowed) return;
          responseAllowed = false;
          const rt = performance.now() - responseStartTime;
          const trial = trialsSequence[currentIdx];

          const expectedDigits = trial.condition === "backward"
            ? trial.digits.split("").reverse().join("")
            : trial.digits;

          if (!trial.isPractice) {{
            recordedTrials.push({{
              stimulus: trial.digits,
              condition: trial.condition,
              expected: expectedDigits,
              response: enteredDigits,
              length: trial.digits.length,
              rt_ms: rt,
              timestamp: new Date().toISOString(),
              valid: true
            }});
          }}

          inputContainer.style.display = "none";
          digitText.innerText = "✓";
          statusMsg.innerText = "Answer recorded.";

          setTimeout(runNextTrial, 600);
        }}

        function finishTask() {{
          displayBox.style.display = "flex";
          inputContainer.style.display = "none";
          conditionBadge.style.display = "none";
          digitText.innerText = "DONE";
          progressDiv.innerText = "";
          statusMsg.innerText = "Saving results to CogLayer...";

          fetch(`${{API_URL}}/v1/assessment/tasks/digit_span/submit`, {{
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

    col1, col2 = st.columns([2, 3])
    with col1:
        if st.button("Check Status & Return to Lab", key="ds_check_btn", type="primary"):
            st.session_state["page"] = "lab"
            st.rerun()
