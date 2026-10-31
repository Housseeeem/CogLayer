"""Conversational coach service for CogLayer.

Manages multi-turn coaching conversations with profile-grounded context.
Reuses existing safety rules from CognitiveCoach.

Requirements: Multi-turn coach with profile grounding
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Final

from coglayer.core.adaptation import CoachAdaptationConfig
from coglayer.core.brain_twin import BrainTwinSignal
from coglayer.core.models import (
    CoachConversation,
    CoachMessage,
    CoachMessageRole,
    CognitiveProfile,
)
from coglayer.core.protocols import ConversationRepository, LLMProvider, LLMRequest
from coglayer.core.settings import Settings

from .coach import _DISCLAIMER, _LLM_INSTRUCTION, FORBIDDEN_WORDS_PATTERN, CognitiveCoach

__all__ = ["ConversationService"]

_log = logging.getLogger(__name__)

_MAX_HISTORY_MESSAGES: Final[int] = 10
"""Maximum number of recent messages to include in context."""

_MAX_MEMORY_MESSAGES: Final[int] = 50
"""Maximum number of messages to keep in memory when storage is disabled."""

_FALLBACK_MESSAGE: Final[str] = (
    "The conversation service is temporarily unavailable. Please try again later."
)
"""Safe fallback message when LLM cannot produce a reliable response."""


class ConversationService:
    """Service for managing multi-turn coaching conversations."""

    def __init__(
        self,
        conversation_repo: ConversationRepository,
        coach: CognitiveCoach,
    ) -> None:
        self._repo = conversation_repo
        self._coach = coach
        self._memory_cache: dict[str, list[CoachMessage]] = defaultdict(list)

    def start_conversation(
        self,
        user_id: str,
        session_id: str | None = None,
    ) -> CoachConversation:
        """Start a new coaching conversation.

        Args:
            user_id: User identifier.
            session_id: Optional assessment session ID for context.

        Returns:
            The new conversation with an initial assistant greeting.
        """
        conversation_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        conversation = CoachConversation(
            conversation_id=conversation_id,
            user_id=user_id,
            session_id=session_id,
            created_at=now,
            messages=[],
        )

        self._repo.save_conversation(conversation)
        return conversation

    def add_message_and_get_response(
        self,
        conversation_id: str,
        user_message: str,
        profile: CognitiveProfile,
        provider: LLMProvider | None,
        settings: Settings | None,
        *,
        brain_twin_signal: BrainTwinSignal | None = None,
        adaptation: CoachAdaptationConfig | None = None,
    ) -> CoachMessage:
        """Add a user message and generate an assistant response.

        Args:
            conversation_id: Conversation identifier.
            user_message: User's message content.
            profile: User's cognitive profile for context.
            provider: Optional LLM provider.
            settings: Optional application settings.
            brain_twin_signal: Optional Brain Twin signal.
            adaptation: Optional coach adaptation settings (e.g. for age group).

        Returns:
            The assistant's response message.
        """
        # Save user message
        user_msg = CoachMessage(
            conversation_id=conversation_id,
            role=CoachMessageRole.USER,
            content=user_message,
            timestamp=datetime.now(UTC),
        )
        should_store = (
            settings is not None
            and settings.store_conversations
            and (adaptation is None or adaptation.store_conversation)
        )
        if should_store:
            self._repo.save_message(user_msg)
        else:
            self._store_in_memory(user_msg)

        if adaptation is not None and not adaptation.allow_free_chat:
            # Child mode: strictly no LLM call, predefined response
            response_text = adaptation.get_predefined_reply(user_message)
        else:
            # Build context from profile and conversation history
            context = self._build_context(conversation_id, profile, brain_twin_signal, settings)

            system_instruction = adaptation.system_prompt if adaptation else _LLM_INSTRUCTION
            prompt = f"{system_instruction}\n\n{context}"

            if settings is not None and not settings.coach_use_llm:
                _log.warning("LLM is disabled; returning safe fallback message")
                response_text = _FALLBACK_MESSAGE
            elif provider is None:
                _log.warning("No LLM provider available; returning safe fallback message")
                response_text = _FALLBACK_MESSAGE
            else:
                try:
                    llm_response = provider.complete(LLMRequest(prompt=prompt))
                    raw_text = llm_response.text
                    # Validate against safety rules
                    validated = self._validate_response(raw_text, instruction=system_instruction)
                    if validated is None:
                        _log.warning(
                            "LLM response failed validation; returning safe fallback message"
                        )
                        response_text = _FALLBACK_MESSAGE
                    else:
                        response_text = validated
                except Exception:
                    _log.warning(
                        "LLM provider raised an exception; returning safe fallback message"
                    )
                    response_text = _FALLBACK_MESSAGE

            # Ensure disclaimer is present for valid LLM responses only
            if response_text != _FALLBACK_MESSAGE and _DISCLAIMER not in response_text:
                response_text = f"{response_text}\n\n{_DISCLAIMER}"

        # Save assistant message
        assistant_msg = CoachMessage(
            conversation_id=conversation_id,
            role=CoachMessageRole.ASSISTANT,
            content=response_text,
            timestamp=datetime.now(UTC),
        )
        if should_store:
            self._repo.save_message(assistant_msg)
        else:
            self._store_in_memory(assistant_msg)

        return assistant_msg

    def get_conversation(self, conversation_id: str) -> CoachConversation | None:
        """Retrieve a conversation by ID."""
        return self._repo.get_conversation(conversation_id)

    def get_user_conversations(self, user_id: str) -> list[CoachConversation]:
        """Retrieve all conversations for a user."""
        return self._repo.get_conversations_by_user(user_id)

    def _build_context(
        self,
        conversation_id: str,
        profile: CognitiveProfile,
        brain_twin_signal: BrainTwinSignal | None = None,
        settings: Settings | None = None,
    ) -> str:
        """Build conversation context from profile and message history.

        Args:
            conversation_id: Conversation identifier.
            profile: User's cognitive profile.
            brain_twin_signal: Optional Brain Twin signal.
            settings: Optional application settings.

        Returns:
            Formatted context string.
        """
        # Get recent message history from repo or memory
        if settings is not None and settings.store_conversations:
            messages = self._repo.get_messages(conversation_id)
        else:
            messages = self._memory_cache.get(conversation_id, [])
        recent_messages = messages[-_MAX_HISTORY_MESSAGES:] if messages else []

        # Build profile summary using existing coach logic
        profile_summary = self._coach._build_local_text(profile, brain_twin_signal)

        # Format conversation history
        history_text = ""
        if recent_messages:
            history_lines = ["Recent conversation:"]
            for msg in recent_messages:
                role_label = "You" if msg.role == CoachMessageRole.USER else "Coach"
                history_lines.append(f"  {role_label}: {msg.content}")
            history_text = "\n".join(history_lines) + "\n\n"

        return f"{history_text}{profile_summary}"

    def _validate_response(
        self,
        response: str,
        instruction: str = _LLM_INSTRUCTION,
    ) -> str | None:
        """Validate LLM response against safety rules.

        Args:
            response: Raw LLM response.
            instruction: Instruction prompt to check for echo.

        Returns:
            Validated response or None if validation fails.
        """
        if not response:
            return None
        stripped = response.strip()
        if len(stripped) < 20:
            return None
        if FORBIDDEN_WORDS_PATTERN.search(stripped):
            return None
        # Check for instruction echo
        if instruction.strip().lower() in stripped.lower():
            return None
        return stripped

    def _store_in_memory(self, message: CoachMessage) -> None:
        """Store a message in the in-memory cache when storage is disabled.

        Args:
            message: The message to store.
        """
        conversation_id = message.conversation_id
        messages = self._memory_cache[conversation_id]
        messages.append(message)
        # Keep only the most recent messages in memory
        if len(messages) > _MAX_MEMORY_MESSAGES:
            self._memory_cache[conversation_id] = messages[-_MAX_MEMORY_MESSAGES:]

    def clear_memory_cache(self, conversation_id: str) -> None:
        """Clear the memory cache for a specific conversation.

        Args:
            conversation_id: Conversation identifier.
        """
        self._memory_cache.pop(conversation_id, None)
