"""Cognitive Coach chat page for CogLayer UI.

Displays a conversational interface for multi-turn coaching interactions.

Requirements: Multi-turn coach with profile grounding
"""

from __future__ import annotations

import httpx
import streamlit as st


def render_coach_page(api_url: str, user_id: str) -> None:
    """Render the cognitive coach chat page."""
    st.header("Supportive Cognitive Coach")

    # Initialize conversation state
    if "conversation_id" not in st.session_state:
        st.session_state["conversation_id"] = None
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Start new conversation button
    if st.button("Start New Conversation", key="start_new_conv"):
        _start_conversation(api_url, user_id)

    # If no conversation, show start prompt
    if not st.session_state["conversation_id"]:
        st.info("Click 'Start New Conversation' to begin chatting with the coach.")
        col1, _ = st.columns([2, 3])
        with col1:
            if st.button("Return to Tasks"):
                st.session_state["page"] = "next"
                st.rerun()
        return

    # Display conversation history
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Chat input
    if prompt := st.chat_input("Type your message..."):
        # Add user message to display
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        # Send to API and get response
        with st.spinner("Coach is thinking..."):
            response = _send_message(api_url, user_id, st.session_state["conversation_id"], prompt)

        if response:
            # Add assistant message to display
            st.session_state.chat_messages.append({"role": "assistant", "content": response})
            with st.chat_message("assistant"):
                st.write(response)
        else:
            st.error("Failed to get a response. Please try again.")

    st.divider()
    col1, col2 = st.columns([2, 3])
    with col1:
        if st.button("Start Another Session"):
            st.session_state["session_id"] = None
            st.session_state["page"] = "next"
            st.rerun()
    with col2:
        if st.button("Back to Profile View"):
            st.session_state["page"] = "profile"
            st.rerun()


def _start_conversation(api_url: str, user_id: str) -> None:
    """Start a new conversation and update session state."""
    try:
        resp = httpx.post(
            f"{api_url}/v1/assessment/coach/{user_id}/conversations",
            json={"session_id": st.session_state.get("session_id", None)},
            timeout=15.0,
        )
        if resp.status_code == 403:
            st.warning("Assessment not yet complete. Please finish all tasks first.")
            return
        elif resp.status_code != 200:
            st.error(f"Error starting conversation: {resp.text}")
            return

        data = resp.json()
        st.session_state["conversation_id"] = data["conversation_id"]
        st.session_state["chat_messages"] = []
        st.rerun()
    except Exception as e:
        st.error(f"Error connecting to coach endpoint: {e}")


def _send_message(api_url: str, user_id: str, conversation_id: str, content: str) -> str | None:
    """Send a message and return the assistant response."""
    try:
        resp = httpx.post(
            f"{api_url}/v1/assessment/coach/{user_id}/conversations/{conversation_id}/messages",
            json={"content": content},
            timeout=30.0,
        )
        if resp.status_code == 403:
            st.error("Session expired or unauthorized. Please start a new conversation.")
            st.session_state["conversation_id"] = None
            st.session_state["chat_messages"] = []
            st.rerun()
            return None
        elif resp.status_code != 200:
            st.error(f"Error sending message: {resp.text}")
            return None

        data = resp.json()
        content = data.get("content")
        if isinstance(content, str):
            return content
        return None
    except Exception as e:
        st.error(f"Error connecting to coach endpoint: {e}")
        return None
