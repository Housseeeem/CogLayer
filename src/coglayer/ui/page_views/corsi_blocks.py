"""Corsi Blocks task page for CogLayer UI.

Renders an interactive browser-side HTML/JS component capturing visuospatial
working memory span through forward and backward block sequence reproduction.

Non-clinical statement: This task measures performance on spatial block sequence
reproduction under standardized conditions. It is not a clinical assessment.
"""

from __future__ import annotations

import httpx
import streamlit as st
import streamlit.components.v1 as components


def render_corsi_blocks_page(api_url: str, user_id: str, session_id: str) -> None:
    """Render Corsi Blocks interactive cognitive task page."""
    st.header("Cognitive Lab: Corsi Blocks")

    st.markdown(
        """
        > **Non-clinical statement**: This task measures spatial working memory
        > capacity via block sequence reproduction. It is not a clinical assessment.

        **Instructions**:
        - Observe the 9 spatial blocks carefully.
        - Blocks will light up in amber one by one.
        - When the sequence ends and the banner turns blue:
          - **Forward mode**: tap the blocks in the **same order** they flashed.
          - **Backward mode**: tap the blocks in **reverse order** (last block first).
        - Sequences start at 3 blocks and get progressively longer.
        """
    )

    if st.button("← Back to Cognitive Lab", key="corsi_back_top"):
        st.session_state["page"] = "lab"
        st.rerun()

    # Check if session already completed corsi_blocks
    if session_id:
        try:
            sess_resp = httpx.get(f"{api_url}/v1/assessment/sessions/{session_id}", timeout=5.0)
            if sess_resp.status_code == 200:
                session_data = sess_resp.json()
                if "corsi_blocks" in session_data.get("completed_tasks", []):
                    st.success("✅ Corsi Blocks task is already completed for this session.")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(
                            "Return to Cognitive Lab", key="corsi_ret_comp", type="primary"
                        ):
                            st.session_state["page"] = "lab"
                            st.rerun()
                    with col2:
                        if st.button("View Cognitive Profile", key="corsi_view_prof"):
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
        #board-wrapper {{
          position: relative;
          width: 320px;
          height: 320px;
          background: #111827;
          border: 2px solid #374151;
          border-radius: 16px;
          margin: 15px auto;
          box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        }}
        .corsi-block {{
          position: absolute;
          width: 65px;
          height: 65px;
          background: #1f2937;
          border: 2px solid #4b5563;
          border-radius: 10px;
          cursor: default;
          transition: background-color 0.15s ease, transform 0.1s ease, border-color 0.15s;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 16px;
          font-weight: bold;
          color: #9ca3af;
        }}
        .corsi-block.interactive {{
          cursor: pointer;
        }}
        .corsi-block.interactive:hover {{
          border-color: #60a5fa;
        }}
        .corsi-block.flashing {{
          background: #f59e0b !important;
          border-color: #fbbf24 !important;
          transform: scale(1.08);
          box-shadow: 0 0 18px rgba(245, 158, 11, 0.7);
        }}
        .corsi-block.user-tapped {{
          background: #3b82f6 !important;
          border-color: #60a5fa !important;
          transform: scale(0.95);
        }}
        #mode-banner {{
          display: inline-block;
          font-size: 13px;
          font-weight: 700;
          letter-spacing: 1px;
          padding: 4px 14px;
          border-radius: 20px;
          text-transform: uppercase;
          margin-bottom: 8px;
        }}
        .banner-watch {{
          background: rgba(245, 158, 11, 0.2);
          color: #fbbf24;
          border: 1px solid #f59e0b;
        }}
        .banner-respond {{
          background: rgba(59, 130, 246, 0.2);
          color: #60a5fa;
          border: 1px solid #3b82f6;
        }}
        #action-btn {{
          background: #3b82f6;
          color: white;
          border: none;
          padding: 12px 36px;
          font-size: 18px;
          font-weight: 600;
          border-radius: 8px;
          cursor: pointer;
          margin-top: 10px;
        }}
        #action-btn:hover {{ background: #2563eb; }}
        #status-msg {{
          margin-top: 10px;
          font-size: 15px;
          color: #9ca3af;
          min-height: 22px;
          text-align: center;
        }}
        #progress {{
          margin-top: 4px;
          font-size: 13px;
          color: #6b7280;
        }}
      </style>
    </head>
    <body>
      <span id="mode-banner" class="banner-watch">READY</span>
      <div id="board-wrapper">
        <!-- 9 spatial blocks positioned in realistic Corsi layout -->
        <div class="corsi-block" id="block-0" style="top: 25px; left: 30px;">1</div>
        <div class="corsi-block" id="block-1" style="top: 15px; left: 160px;">2</div>
        <div class="corsi-block" id="block-2" style="top: 50px; left: 240px;">3</div>
        <div class="corsi-block" id="block-3" style="top: 125px; left: 40px;">4</div>
        <div class="corsi-block" id="block-4" style="top: 120px; left: 140px;">5</div>
        <div class="corsi-block" id="block-5" style="top: 145px; left: 235px;">6</div>
        <div class="corsi-block" id="block-6" style="top: 225px; left: 20px;">7</div>
        <div class="corsi-block" id="block-7" style="top: 235px; left: 125px;">8</div>
        <div class="corsi-block" id="block-8" style="top: 225px; left: 225px;">9</div>
      </div>

      <button id="action-btn" onclick="startCorsi()">Start Corsi Blocks</button>
      <div id="status-msg">Press Start to begin.</div>
      <div id="progress"></div>

      <script>
        const API_URL = "{api_url}";
        const USER_ID = "{user_id}";
        const SESSION_ID = "{session_id}";

        const boardWrapper = document.getElementById("board-wrapper");
        const modeBanner = document.getElementById("mode-banner");
        const actionBtn = document.getElementById("action-btn");
        const statusMsg = document.getElementById("status-msg");
        const progressDiv = document.getElementById("progress");

        // Sequence battery: practice (2 sequences: 1 forward len 3, 1 backward len 3)
        // Scored: forward (3, 4, 5, 6) and backward (3, 4, 5, 6)
        const sequenceBattery = [
          {{ items: [0, 4, 8], condition: "forward", isPractice: true }},
          {{ items: [2, 7, 3], condition: "backward", isPractice: true }},
          // Scored Forward
          {{ items: [1, 5, 6], condition: "forward" }},
          {{ items: [3, 0, 7, 2], condition: "forward" }},
          {{ items: [8, 4, 1, 6, 5], condition: "forward" }},
          {{ items: [2, 7, 0, 4, 8, 3], condition: "forward" }},
          // Scored Backward
          {{ items: [6, 1, 4], condition: "backward" }},
          {{ items: [5, 2, 8, 0], condition: "backward" }},
          {{ items: [7, 3, 6, 1, 4], condition: "backward" }},
          {{ items: [0, 8, 5, 2, 7, 4], condition: "backward" }}
        ];

        let currentSeqIdx = -1;
        let isUserTurn = false;
        let userTaps = [];
        let seqStartTime = 0;
        let responseTimer = null;
        const recordedSequences = [];

        // Attach click handlers to all 9 blocks
        for (let i = 0; i < 9; i++) {{
          const blk = document.getElementById("block-" + i);
          blk.addEventListener("click", () => {{
            if (!isUserTurn) return;
            handleUserTap(i, blk);
          }});
        }}

        function handleUserTap(idx, blk) {{
          userTaps.push(idx);
          blk.classList.add("user-tapped");
          setTimeout(() => blk.classList.remove("user-tapped"), 180);

          const curSeq = sequenceBattery[currentSeqIdx];
          if (userTaps.length >= curSeq.items.length) {{
            finishCurrentSequence(false);
          }}
        }}

        function startCorsi() {{
          actionBtn.style.display = "none";
          currentSeqIdx = -1;
          runNextSequence();
        }}

        function setInteractive(allow) {{
          isUserTurn = allow;
          for (let i = 0; i < 9; i++) {{
            const blk = document.getElementById("block-" + i);
            if (allow) blk.classList.add("interactive");
            else blk.classList.remove("interactive");
          }}
        }}

        function runNextSequence() {{
          currentSeqIdx++;
          if (currentSeqIdx >= sequenceBattery.length) {{
            finishTask();
            return;
          }}

          const seq = sequenceBattery[currentSeqIdx];
          userTaps = [];
          setInteractive(false);

          modeBanner.className = "banner-watch";
          const pracSuffix = seq.isPractice ? " (PRACTICE)" : "";
          modeBanner.innerText = "WATCH: " + seq.condition.toUpperCase() + pracSuffix;
          const totalScored = sequenceBattery.length - 2;
          progressDiv.innerText = seq.isPractice
            ? `Practice sequence ${{currentSeqIdx + 1}} of 2`
            : `Sequence ${{currentSeqIdx - 1}}/${{totalScored}} (Len: ${{seq.items.length}})`;

          statusMsg.innerText = "Watch the flashing blocks...";

          setTimeout(() => {{
            flashStep(seq.items, 0);
          }}, 800);
        }}

        function flashStep(items, step) {{
          if (step >= items.length) {{
            // Presentation done -> user reproduction phase
            setTimeout(() => {{
              beginUserTurn();
            }}, 400);
            return;
          }}

          const blockId = "block-" + items[step];
          const blk = document.getElementById(blockId);
          blk.classList.add("flashing");

          setTimeout(() => {{
            blk.classList.remove("flashing");
            setTimeout(() => {{
              flashStep(items, step + 1);
            }}, 250);
          }}, 600);
        }}

        function beginUserTurn() {{
          const seq = sequenceBattery[currentSeqIdx];
          setInteractive(true);
          modeBanner.className = "banner-respond";
          modeBanner.innerText = seq.condition === "forward"
            ? "REPRODUCE FORWARD"
            : "REPRODUCE IN REVERSE (BACKWARD)";

          statusMsg.innerText = seq.condition === "forward"
            ? "Tap the blocks in the EXACT SAME order:"
            : "Tap the blocks in REVERSE order (last block first):";

          seqStartTime = performance.now();

          // 30s timeout
          responseTimer = setTimeout(() => {{
            finishCurrentSequence(true);
          }}, 30000);
        }}

        function finishCurrentSequence(isTimeout) {{
          clearTimeout(responseTimer);
          setInteractive(false);
          const rt = performance.now() - seqStartTime;
          const seq = sequenceBattery[currentSeqIdx];

          const stimStr = seq.items.join(",");
          const expectedTokens = seq.condition === "backward"
            ? [...seq.items].reverse()
            : seq.items;
          const expectedStr = expectedTokens.join(",");
          const respStr = userTaps.join(",");

          if (!seq.isPractice) {{
            recordedSequences.push({{
              stimulus: stimStr,
              condition: seq.condition,
              expected: expectedStr,
              response: respStr,
              length: seq.items.length,
              rt_ms: rt,
              timestamp: new Date().toISOString(),
              valid: !isTimeout
            }});
          }}

          modeBanner.innerText = "RECORDED";
          statusMsg.innerText = "Sequence recorded.";
          setTimeout(runNextSequence, 600);
        }}

        function finishTask() {{
          modeBanner.innerText = "DONE";
          statusMsg.innerText = "Uploading results to CogLayer...";
          progressDiv.innerText = "";

          fetch(`${{API_URL}}/v1/assessment/tasks/corsi_blocks/submit`, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{
              session_id: SESSION_ID,
              user_id: USER_ID,
              raw_result: {{ sequences: recordedSequences }}
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
        if st.button("Check Status & Return to Lab", key="corsi_check_btn", type="primary"):
            st.session_state["page"] = "lab"
            st.rerun()
