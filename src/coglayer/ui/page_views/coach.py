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
    for msg in st.session_state["chat_messages"]:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Fetch onboarding profile to adapt UI for age group and presentation
    profile = _fetch_experience_profile(api_url, user_id)
    age_group = profile.get("age_group") if isinstance(profile, dict) else None
    info_style = profile.get("info_style") if isinstance(profile, dict) else None

    if info_style in ("short_simple", "step_by_step"):
        st.caption("Concise coaching mode.")
    elif info_style == "detailed":
        st.caption("Comprehensive cognitive coaching view.")

    # Child mode: strictly no free text input, predefined response buttons only
    if age_group == "child_7_12":
        _render_child_coach(api_url, user_id)
    else:
        # Teen: show suggested prompts
        if age_group == "teen_13_17":
            _render_teen_suggestions(api_url, user_id)

        # Chat input for free text (teen and adult)
        if prompt := st.chat_input("Type your message..."):
            st.session_state.chat_messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.write(prompt)

            with st.spinner("Coach is thinking..."):
                response = _send_message(
                    api_url,
                    user_id,
                    st.session_state["conversation_id"],
                    prompt,
                    is_predefined=False,
                )

            if response:
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


def _fetch_experience_profile(api_url: str, user_id: str) -> dict[str, object] | None:
    """Fetch the onboarding experience profile for the given user."""
    try:
        resp = httpx.get(
            f"{api_url}/v1/assessment/onboarding/profile/{user_id}",
            params={"user_id": user_id},
            timeout=5.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, dict) else None
    except (httpx.HTTPError, ValueError):
        return None
    return None


def _render_child_coach(api_url: str, user_id: str) -> None:
    """Render predefined-response-only UI for child users."""
    st.write("**Pick a question or message for your coach:**")
    child_options = (
        "How am I doing?",
        "Let's try another game",
        "Time for a short break",
        "Ask a grown-up to help you",
        "Keep up the great work!",
        "You are doing wonderfully!",
    )
    cols = st.columns(3)
    for i, option in enumerate(child_options):
        col = cols[i % 3]
        with col:
            if st.button(option, key=f"child_opt_{i}"):
                st.session_state.chat_messages.append({"role": "user", "content": option})
                with st.spinner("Coach is thinking..."):
                    response = _send_message(
                        api_url,
                        user_id,
                        st.session_state["conversation_id"],
                        option,
                        is_predefined=True,
                    )
                if response:
                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": response}
                    )
                st.rerun()


def _render_teen_suggestions(api_url: str, user_id: str) -> None:
    """Render suggested prompts for teen users alongside free text input."""
    st.write("**Suggested questions:**")
    teen_options = (
        "How did I do on today's tasks?",
        "What game should I try next?",
        "Tips for maintaining daily focus",
    )
    cols = st.columns(3)
    for i, option in enumerate(teen_options):
        col = cols[i % 3]
        with col:
            if st.button(option, key=f"teen_opt_{i}"):
                st.session_state.chat_messages.append({"role": "user", "content": option})
                with st.spinner("Coach is thinking..."):
                    response = _send_message(
                        api_url,
                        user_id,
                        st.session_state["conversation_id"],
                        option,
                        is_predefined=True,
                    )
                if response:
                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": response}
                    )
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


def _send_message(
    api_url: str,
    user_id: str,
    conversation_id: str,
    content: str,
    is_predefined: bool = False,
) -> str | None:
    """Send a message and return the assistant response."""
    try:
        resp = httpx.post(
            f"{api_url}/v1/assessment/coach/{user_id}/conversations/{conversation_id}/messages",
            json={"content": content, "is_predefined": is_predefined},
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
        response_content = data.get("content")
        if isinstance(response_content, str):
            return response_content
        return None
    except Exception as e:
        st.error(f"Error connecting to coach endpoint: {e}")
        return None
