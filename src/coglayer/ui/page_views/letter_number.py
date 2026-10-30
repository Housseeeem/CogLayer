"""Letter-Number Sequencing task page for CogLayer UI.

Renders an interactive browser-side HTML/JS component capturing active mental
manipulation and working memory capacity by presenting mixed letters and numbers
that must be reorganized (numbers ascending first, letters alphabetically).

Non-clinical statement: This task measures performance on mental manipulation
under standardized rules. It is not a clinical assessment.
"""

from __future__ import annotations

import httpx
import streamlit as st
import streamlit.components.v1 as components

from coglayer.ui.design import activity_frame_html


def render_letter_number_page(api_url: str, user_id: str, session_id: str) -> None:
    """Render Letter-Number Sequencing interactive cognitive task page."""
    st.header("Cognitive Lab: Letter-Number Sequencing")

    st.markdown(
        """
        > **Non-clinical statement**: This task measures active mental manipulation
        > in working memory. It is not a clinical assessment.

        **Instructions**:
        - You will be shown a mixed sequence of letters and numbers (e.g. **D 7 B 2**).
        - Memorize the items carefully while they are on screen.
        - When the input opens, reorganize and enter the sequence according to two strict rules:
          1. **Numbers first**, in **ascending order** (from smallest to largest: 1, 2, 3...)
          2. **Letters next**, in **alphabetical order** (A, B, C...)
        - *Example*: if the sequence is **C 4 A 1**, the correct answer is **1 4 A C**.
        """
    )

    if st.button("← Back to Cognitive Lab", key="lns_back_top"):
        st.session_state["page"] = "lab"
        st.rerun()

    # Check if session already completed letter_number_sequencing
    if session_id:
        try:
            sess_resp = httpx.get(f"{api_url}/v1/assessment/sessions/{session_id}", timeout=5.0)
            if sess_resp.status_code == 200:
                session_data = sess_resp.json()
                if "letter_number_sequencing" in session_data.get("completed_tasks", []):
                    st.success(
                        "✅ Letter-Number Sequencing task is already completed for this session."
                    )
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Return to Cognitive Lab", key="lns_ret_comp", type="primary"):
                            st.session_state["page"] = "lab"
                            st.rerun()
                    with col2:
                        if st.button("View Cognitive Profile", key="lns_view_prof"):
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
        #display-card {{
          width: 320px;
          height: 150px;
          background: #1f2937;
          border: 2px solid #374151;
          border-radius: 16px;
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 15px auto;
          box-shadow: 0 4px 20px rgba(0,0,0,0.4);
        }}
        #items-text {{
          font-size: 38px;
          font-weight: 800;
          letter-spacing: 12px;
          color: #60a5fa;
          font-family: monospace;
        }}
        #input-box-wrapper {{
          display: none;
          flex-direction: column;
          align-items: center;
          margin-top: 10px;
        }}
        #user-text-input {{
          width: 280px;
          height: 48px;
          background: #111827;
          border: 2px solid #4b5563;
          border-radius: 8px;
          font-size: 24px;
          letter-spacing: 6px;
          text-align: center;
          color: #ffffff;
          font-family: monospace;
          text-transform: uppercase;
          outline: none;
          margin-bottom: 12px;
        }}
        #user-text-input:focus {{
          border-color: #3b82f6;
        }}
        .control-btns {{
          display: flex;
          gap: 10px;
        }}
        .ctrl-btn {{
          padding: 10px 24px;
          font-size: 16px;
          font-weight: 600;
          border-radius: 6px;
          border: none;
          cursor: pointer;
        }}
        .btn-submit {{ background: #2563eb; color: white; }}
        .btn-submit:hover {{ background: #1d4ed8; }}
        .btn-clear {{ background: #ef4444; color: white; }}
        .btn-clear:hover {{ background: #dc2626; }}
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
      <div id="display-card">
        <div id="items-text">READY</div>
      </div>

      <div id="input-box-wrapper">
        <input type="text" id="user-text-input" placeholder="e.g. 1 4 A C" autocomplete="off" />
        <div class="control-btns">
          <button class="ctrl-btn btn-clear" onclick="clearInput()">Clear</button>
          <button class="ctrl-btn btn-submit" onclick="submitAnswer()">Submit Order</button>
        </div>
      </div>

      <button id="action-btn" onclick="startTask()">Start Letter-Number Task</button>
      <div id="status-msg">Click Start to begin.</div>
      <div id="progress"></div>

      <script>
        const API_URL = "{api_url}";
        const USER_ID = "{user_id}";
        const SESSION_ID = "{session_id}";

        const displayCard = document.getElementById("display-card");
        const itemsText = document.getElementById("items-text");
        const inputBoxWrapper = document.getElementById("input-box-wrapper");
        const userTextInput = document.getElementById("user-text-input");
        const actionBtn = document.getElementById("action-btn");
        const statusMsg = document.getElementById("status-msg");
        const progressDiv = document.getElementById("progress");

        // Sequences (mixed letters & numbers):
        // 2 practice trials (length 2, 3)
        // 7 scored trials (lengths 3, 4, 4, 5, 5, 6, 7)
        const sequenceBattery = [
          {{ raw: "B 2", isPractice: true }},
          {{ raw: "C 1 A", isPractice: true }},
          // Scored
          {{ raw: "4 B 1" }},           // Expected: 1 4 B
          {{ raw: "D 7 A 2" }},         // Expected: 2 7 A D
          {{ raw: "3 G 9 E" }},         // Expected: 3 9 E G
          {{ raw: "L 2 F 8 C" }},       // Expected: 2 8 C F L
          {{ raw: "5 P 1 K 6" }},       // Expected: 1 5 6 K P
          {{ raw: "B 7 M 2 Q 4" }},     // Expected: 2 4 7 B M Q
          {{ raw: "3 X 9 A 1 R 6" }}    // Expected: 1 3 6 9 A R X
        ];

        let currentIdx = -1;
        let stimulusOnset = 0;
        let responseAllowed = false;
        const recordedTrials = [];

        function sortLetterNumber(str) {{
          const tokens = str.trim().split(/\\s+/);
          const nums = [];
          const letters = [];
          tokens.forEach(tok => {{
            if (!isNaN(tok)) nums.push(parseInt(tok));
            else letters.push(tok.toUpperCase());
          }});
          nums.sort((a, b) => a - b);
          letters.sort();
          return [...nums.map(String), ...letters].join(" ");
        }}

        function startTask() {{
          actionBtn.style.display = "none";
          currentIdx = -1;
          runNextTrial();
        }}

        function runNextTrial() {{
          currentIdx++;
          if (currentIdx >= sequenceBattery.length) {{
            finishTask();
            return;
          }}

          const trial = sequenceBattery[currentIdx];
          responseAllowed = false;
          inputBoxWrapper.style.display = "none";
          displayCard.style.display = "flex";
          userTextInput.value = "";

          const totalScored = sequenceBattery.length - 2;
          const lenItems = trial.raw.split(" ").length;
          progressDiv.innerText = trial.isPractice
            ? `Practice ${{currentIdx + 1}} of 2`
            : `Scored trial ${{currentIdx - 1}} of ${{totalScored}} (Len: ${{lenItems}})`;

          statusMsg.innerText = "Memorize the characters...";
          itemsText.innerText = "+";

          setTimeout(() => {{
            // Display stimulus for 2500ms
            itemsText.innerText = trial.raw;
            setTimeout(() => {{
              // Mask completely
              itemsText.innerText = "• • •";
              setTimeout(beginInputPhase, 500);
            }}, 2500);
          }}, 800);
        }}

        function beginInputPhase() {{
          displayCard.style.display = "none";
          inputBoxWrapper.style.display = "flex";
          responseAllowed = true;
          stimulusOnset = performance.now();
          statusMsg.innerText = "Reorder: NUMBERS (ascending) first, then LETTERS (alphabetical):";
          userTextInput.focus();
        }}

        function clearInput() {{
          userTextInput.value = "";
          userTextInput.focus();
        }}

        userTextInput.addEventListener("keydown", (e) => {{
          if (e.key === "Enter") {{
            submitAnswer();
          }}
        }});

        function submitAnswer() {{
          if (!responseAllowed) return;
          responseAllowed = false;
          const rt = performance.now() - stimulusOnset;
          const trial = sequenceBattery[currentIdx];
          const expected = sortLetterNumber(trial.raw);
          const response = userTextInput.value.trim().toUpperCase();

          if (!trial.isPractice) {{
            recordedTrials.push({{
              stimulus: trial.raw,
              expected: expected,
              response: response,
              length: trial.raw.split(" ").length,
              rt_ms: rt,
              timestamp: new Date().toISOString(),
              valid: true
            }});
          }}

          inputBoxWrapper.style.display = "none";
          displayCard.style.display = "flex";
          itemsText.innerText = "✓";
          statusMsg.innerText = "Response recorded.";

          setTimeout(runNextTrial, 600);
        }}

        function finishTask() {{
          inputBoxWrapper.style.display = "none";
          displayCard.style.display = "flex";
          itemsText.innerText = "DONE";
          progressDiv.innerText = "";
          statusMsg.innerText = "Uploading results to CogLayer...";

          fetch(`${{API_URL}}/v1/assessment/tasks/letter_number_sequencing/submit`, {{
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
        if st.button("Check Status & Return to Lab", key="lns_check_btn", type="primary"):
            st.session_state["page"] = "lab"
            st.rerun()
