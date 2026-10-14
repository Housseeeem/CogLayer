"""Visual Sequence Span task page for CogLayer UI.

Renders an interactive browser-side HTML/JS component adapted from the Corsi
block-tapping test capturing sequence memory reproduction and response times.

Requirements: R-004.1, R-004.2, R-004.4, R-010.3
"""

from __future__ import annotations

import httpx
import streamlit as st
import streamlit.components.v1 as components


def render_sequence_span_page(api_url: str, user_id: str, session_id: str) -> None:
    """Render Visual Sequence Span task page."""
    st.header("Task 2: Visual Sequence Span (Sequential Visual Memory Proxy)")

    st.markdown(
        """
        > **Non-clinical statement**: This task measures sequential visual memory
        > via spatial sequence reproduction. It is used as a proxy for working-memory
        > capacity but does NOT purely measure working memory — it conflates visuospatial
        > short-term memory with the motor reproduction component.

        **Instructions**:
        - Watch the grid of blocks carefully. A sequence of blocks will light up one by one.
        - Once the sequence finishes, click the blocks in the **exact same order**.
        - Sequences will gradually increase in length.
        - You have up to 30 seconds per sequence.
        """
    )

    # Check if sequence_span is already completed
    try:
        sess_resp = httpx.get(f"{api_url}/v1/assessment/sessions/{session_id}", timeout=5.0)
        if sess_resp.status_code == 200:
            session_data = sess_resp.json()
            if "sequence_span" in session_data.get("completed_tasks", []):
                st.success("✅ Sequence Span task is completed for this session.")
                if st.button("Proceed to Cognitive Profile", type="primary"):
                    st.session_state["page"] = "profile"
                    st.rerun()
                return
    except Exception as e:
        st.warning(f"Could not reach API to check session status: {e}")

    # Self-contained HTML/JS sequence span runner
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
        #grid-container {{
          display: grid;
          grid-template-columns: repeat(3, 90px);
          grid-template-rows: repeat(3, 90px);
          gap: 16px;
          margin: 20px auto;
        }}
        .grid-block {{
          background: #1f2937;
          border: 2px solid #374151;
          border-radius: 12px;
          cursor: pointer;
          transition: background-color 0.15s ease, transform 0.1s ease;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: bold;
          font-size: 20px;
        }}
        .grid-block.active {{
          background: #f59e0b !important;
          border-color: #fbbf24 !important;
          transform: scale(1.05);
          box-shadow: 0 0 15px rgba(245, 158, 11, 0.6);
        }}
        .grid-block.user-clicked {{
          background: #3b82f6 !important;
          border-color: #60a5fa !important;
        }}
        #action-btn {{
          background: #3b82f6;
          color: white;
          border: none;
          padding: 12px 32px;
          font-size: 18px;
          font-weight: 600;
          border-radius: 8px;
          cursor: pointer;
          margin-top: 15px;
        }}
        #action-btn:hover {{ background: #2563eb; }}
        #status-msg {{
          margin-top: 15px;
          font-size: 16px;
          color: #9ca3af;
          min-height: 24px;
        }}
        #progress {{
          margin-top: 8px;
          font-size: 14px;
          color: #6b7280;
        }}
      </style>
    </head>
    <body>
      <div id="grid-container">
        <div class="grid-block" data-idx="0"></div>
        <div class="grid-block" data-idx="1"></div>
        <div class="grid-block" data-idx="2"></div>
        <div class="grid-block" data-idx="3"></div>
        <div class="grid-block" data-idx="4"></div>
        <div class="grid-block" data-idx="5"></div>
        <div class="grid-block" data-idx="6"></div>
        <div class="grid-block" data-idx="7"></div>
        <div class="grid-block" data-idx="8"></div>
      </div>
      <button id="action-btn">Start Practice</button>
      <div id="status-msg">Click Start to begin.</div>
      <div id="progress"></div>

      <script>
        const API_URL = "{api_url}";
        const USER_ID = "{user_id}";
        const SESSION_ID = "{session_id}";
        const TIMEOUT_MS = 30000;

        const blocks = document.querySelectorAll(".grid-block");
        const actionBtn = document.getElementById("action-btn");
        const statusMsg = document.getElementById("status-msg");
        const progressDiv = document.getElementById("progress");

        // Sequences for demo, practice, and scored
        const sequenceList = [
          // 1 demo (length 2)
          {{ items: [0, 4], isDemo: true }},
          // 2 practice (length 3)
          {{ items: [1, 5, 2], isPractice: true }},
          {{ items: [3, 7, 8], isPractice: true }},
          // Scored sequences (lengths 3, 4, 5, 6)
          {{ items: [0, 4, 8] }},
          {{ items: [2, 6, 1] }},
          {{ items: [7, 3, 5, 0] }},
          {{ items: [1, 8, 4, 6] }},
          {{ items: [3, 1, 7, 2, 8] }},
          {{ items: [5, 0, 4, 6, 2] }},
          {{ items: [0, 8, 2, 6, 4, 7] }}
        ];

        let currentSeqIdx = -1;
        let userResponses = [];
        let seqStartTime = 0;
        let timeoutTimer = null;
        let isUserTurn = false;
        const results = [];

        actionBtn.addEventListener("click", () => {{
          actionBtn.style.display = "none";
          currentSeqIdx = -1;
          runNextSequence();
        }});

        blocks.forEach(block => {{
          block.addEventListener("click", () => {{
            if (!isUserTurn) return;
            const idx = parseInt(block.getAttribute("data-idx"));
            userResponses.push(idx);

            block.classList.add("user-clicked");
            setTimeout(() => block.classList.remove("user-clicked"), 200);

            const targetSeq = sequenceList[currentSeqIdx].items;
            if (userResponses.length >= targetSeq.length) {{
              recordSequenceEnd(false);
            }}
          }});
        }});

        function runNextSequence() {{
          currentSeqIdx++;
          if (currentSeqIdx >= sequenceList.length) {{
            finishExperiment();
            return;
          }}

          const seq = sequenceList[currentSeqIdx];
          progressDiv.innerText = seq.isDemo
            ? "Demo Sequence"
            : seq.isPractice
              ? `Practice Sequence`
              : `Scored Sequence ${{currentSeqIdx - 2}} of ` +
                `${{sequenceList.length - 3}} (Length ${{seq.items.length}})`;

          statusMsg.innerText = "Watch carefully...";
          isUserTurn = false;
          userResponses = [];

          // Play sequence with 600ms highlight + 300ms pause
          playSequence(seq.items, 0);
        }}

        function playSequence(items, step) {{
          if (step >= items.length) {{
            // Switch to user reproduction
            setTimeout(() => {{
              isUserTurn = true;
              seqStartTime = performance.now();
              statusMsg.innerText = "Your turn: reproduce the sequence!";
              // Enforce 30s timeout
              timeoutTimer = setTimeout(() => {{
                recordSequenceEnd(true);
              }}, TIMEOUT_MS);
            }}, 400);
            return;
          }}

          const blockIdx = items[step];
          const block = blocks[blockIdx];
          block.classList.add("active");

          setTimeout(() => {{
            block.classList.remove("active");
            setTimeout(() => {{
              playSequence(items, step + 1);
            }}, 250);
          }}, 600);
        }}

        function recordSequenceEnd(isTimeout) {{
          clearTimeout(timeoutTimer);
          isUserTurn = false;
          const rt = performance.now() - seqStartTime;
          const seq = sequenceList[currentSeqIdx];

          if (!seq.isDemo && !seq.isPractice) {{
            results.push({{
              stimulus: seq.items.join(","),
              expected: seq.items.join(","),
              response: isTimeout ? null : userResponses.join(","),
              rt_ms: rt,
              timestamp: new Date().toISOString(),
              length: seq.items.length,
              valid: !isTimeout,
              invalid_reason: isTimeout ? "timeout" : null
            }});
          }}

          statusMsg.innerText = isTimeout ? "Sequence timed out." : "Sequence recorded.";
          setTimeout(runNextSequence, 800);
        }}

        function finishExperiment() {{
          statusMsg.innerText = "Uploading results to CogLayer...";

          fetch(`${{API_URL}}/v1/assessment/tasks/sequence_span/submit`, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              session_id: SESSION_ID,
              user_id: USER_ID,
              raw_result: {{ sequences: results }}
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

    components.html(html_code, height=560)

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
                    if "sequence_span" in session_info.get("completed_tasks", []):
                        st.session_state["page"] = "profile"
                        st.rerun()
                    else:
                        st.info(
                            "Task submission is not yet detected. "
                            "Please complete the sequences above."
                        )
            except Exception as e:
                st.error(f"Error communicating with API: {e}")
