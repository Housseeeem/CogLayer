"""Tests for conversation service.

Tests cover conversation lifecycle, context building, and validation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from coglayer.coach.coach import CognitiveCoach
from coglayer.coach.conversation import ConversationService
from coglayer.core.brain_twin import BrainTwinSignal, BrainTwinState
from coglayer.core.models import (
    CoachMessage,
    CoachMessageRole,
    CognitiveProfile,
    DimensionEstimate,
)
from coglayer.core.settings import Settings


@pytest.fixture
def fake_conversation_repo() -> MagicMock:
    """Mock conversation repository."""
    repo = MagicMock()
    repo.save_conversation = MagicMock()
    repo.get_conversation = MagicMock()
    repo.get_conversations_by_user = MagicMock(return_value=[])
    repo.save_message = MagicMock()
    repo.get_messages = MagicMock(return_value=[])
    repo.delete_user = MagicMock()
    return repo


@pytest.fixture
def conversation_service(fake_conversation_repo: MagicMock) -> ConversationService:
    """Conversation service with mocked repository."""
    coach = CognitiveCoach()
    return ConversationService(fake_conversation_repo, coach)


@pytest.fixture
def sample_profile() -> CognitiveProfile:
    """Sample cognitive profile for testing."""
    return CognitiveProfile(
        user_id="test_user",
        dimensions={
            "response_inhibition": DimensionEstimate(
                dimension="response_inhibition",
                mean=0.75,
                lower=0.51,
                upper=0.91,
                n_evidence=1,
                last_update=datetime.now(UTC),
                alpha=9.0,
                beta_param=3.0,
            )
        },
        evidence_history=[],
        data_quality={},
        uncertainty={},
    )


def test_start_conversation(conversation_service: ConversationService) -> None:
    """Starting a conversation creates a new conversation with UUID."""
    conversation = conversation_service.start_conversation("user_1", session_id="sess_1")

    assert conversation.user_id == "user_1"
    assert conversation.session_id == "sess_1"
    assert conversation.conversation_id is not None
    assert len(conversation.conversation_id) > 0
    assert conversation.messages == []
    assert conversation.created_at is not None


def test_start_conversation_without_session(conversation_service: ConversationService) -> None:
    """Starting a conversation without a session ID is allowed."""
    conversation = conversation_service.start_conversation("user_1")

    assert conversation.user_id == "user_1"
    assert conversation.session_id is None


def test_add_message_and_get_response_with_fake_provider(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
) -> None:
    """Adding a message with no provider returns safe fallback message."""
    conversation = conversation_service.start_conversation("user_1")

    response = conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="How am I doing?",
        profile=sample_profile,
        provider=None,
        settings=None,
    )

    assert response.role == CoachMessageRole.ASSISTANT
    assert len(response.content) > 0
    # Should return safe fallback message when provider is None
    assert "The conversation service is temporarily unavailable" in response.content


def test_add_message_validates_response(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
) -> None:
    """Response validation rejects forbidden words and short responses."""
    conversation = conversation_service.start_conversation("user_1")

    # Test with provider that returns forbidden word
    fake_provider = MagicMock()
    fake_provider.complete.return_value = MagicMock(text="This is a diagnosis for you.")

    response = conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="Test",
        profile=sample_profile,
        provider=fake_provider,
        settings=Settings(coach_use_llm=True),
    )

    # Should fall back to safe message due to forbidden word
    assert "diagnosis" not in response.content.lower()
    assert "The conversation service is temporarily unavailable" in response.content


def test_add_message_with_brain_twin_signal(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
) -> None:
    """Brain Twin signal is included in context when provider is available."""
    conversation = conversation_service.start_conversation("user_1")

    signal = BrainTwinSignal(
        state=BrainTwinState.VARIATION_FLAGGED,
        comparable_observation_count=5,
    )

    # Mock provider that returns a valid response
    fake_provider = MagicMock()
    fake_provider.complete.return_value = MagicMock(
        text="This is a helpful response about variation."
    )

    response = conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="Test",
        profile=sample_profile,
        provider=fake_provider,
        settings=Settings(coach_use_llm=True),
        brain_twin_signal=signal,
    )

    # Should return the provider's response (with disclaimer added)
    assert "helpful response" in response.content.lower()


def test_get_conversation(
    conversation_service: ConversationService,
    fake_conversation_repo: MagicMock,
) -> None:
    """Retrieving a conversation by ID returns the conversation."""
    fake_conversation_repo.get_conversation.return_value = None

    result = conversation_service.get_conversation("conv_1")
    assert result is None


def test_get_user_conversations(
    conversation_service: ConversationService,
    fake_conversation_repo: MagicMock,
) -> None:
    """Retrieving user conversations returns list from repository."""
    fake_conversation_repo.get_conversations_by_user.return_value = []

    result = conversation_service.get_user_conversations("user_1")
    assert result == []


def test_context_building_includes_history(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
    fake_conversation_repo: MagicMock,
) -> None:
    """Context building includes recent message history from repo when storage is enabled."""
    conversation = conversation_service.start_conversation("user_1")

    # Add a mock message to history
    fake_conversation_repo.get_messages.return_value = [
        CoachMessage(
            conversation_id=conversation.conversation_id,
            role=CoachMessageRole.USER,
            content="Hello",
            timestamp=datetime.now(UTC),
        )
    ]

    context = conversation_service._build_context(
        conversation.conversation_id, sample_profile, None, Settings(store_conversations=True)
    )

    assert "Recent conversation:" in context
    assert "Hello" in context


def test_context_building_uses_memory_cache_when_storage_disabled(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
    fake_conversation_repo: MagicMock,
) -> None:
    """Context building uses memory cache when storage is disabled."""
    conversation = conversation_service.start_conversation("user_1")

    # Add messages to memory cache
    conversation_service._memory_cache[conversation.conversation_id] = [
        CoachMessage(
            conversation_id=conversation.conversation_id,
            role=CoachMessageRole.USER,
            content="Memory message",
            timestamp=datetime.now(UTC),
        )
    ]

    # Ensure repo returns empty
    fake_conversation_repo.get_messages.return_value = []

    context = conversation_service._build_context(
        conversation.conversation_id, sample_profile, None, Settings(store_conversations=False)
    )

    # Should use memory cache, not repo
    assert "Recent conversation:" in context
    assert "Memory message" in context


def test_messages_not_persisted_when_store_disabled(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
    fake_conversation_repo: MagicMock,
) -> None:
    """Messages are not persisted when store_conversations is False (default)."""
    conversation = conversation_service.start_conversation("user_1")

    settings = Settings(store_conversations=False)
    fake_conversation_repo.save_message.reset_mock()

    conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="Test message",
        profile=sample_profile,
        provider=None,
        settings=settings,
    )

    # save_message should not be called when storage is disabled
    assert fake_conversation_repo.save_message.call_count == 0


def test_messages_persisted_when_store_enabled(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
    fake_conversation_repo: MagicMock,
) -> None:
    """Messages are persisted when store_conversations is True."""
    conversation = conversation_service.start_conversation("user_1")

    settings = Settings(store_conversations=True)
    fake_conversation_repo.save_message.reset_mock()

    conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="Test message",
        profile=sample_profile,
        provider=None,
        settings=settings,
    )

    # save_message should be called twice (user + assistant) when storage is enabled
    assert fake_conversation_repo.save_message.call_count == 2


def test_multi_turn_context_with_memory_cache(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
    fake_conversation_repo: MagicMock,
) -> None:
    """Multi-turn context is preserved in memory when storage is disabled."""
    conversation = conversation_service.start_conversation("user_1")

    settings = Settings(store_conversations=False, coach_use_llm=True)
    fake_conversation_repo.save_message.reset_mock()
    fake_conversation_repo.get_messages.return_value = []

    # Mock provider for valid responses
    fake_provider = MagicMock()
    fake_provider.complete.return_value = MagicMock(text="Response about concentration")

    # First message with identifiable information
    conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="My goal is to improve my concentration",
        profile=sample_profile,
        provider=fake_provider,
        settings=settings,
    )

    # Verify no persistence to repo
    assert fake_conversation_repo.save_message.call_count == 0

    # Verify memory cache has the first turn
    assert len(conversation_service._memory_cache[conversation.conversation_id]) == 2

    # Second message asking about the first
    conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="What goal did I mention?",
        profile=sample_profile,
        provider=fake_provider,
        settings=settings,
    )

    # Verify no persistence to repo (still 0)
    assert fake_conversation_repo.save_message.call_count == 0

    # The context should include the first message via memory cache
    # Check that the service's memory cache has the messages
    assert len(conversation_service._memory_cache[conversation.conversation_id]) == 4
    # 2 messages * 2 turns = 4 messages (user + assistant for each)

    # Verify the cached messages contain the identifiable information
    cached_messages = conversation_service._memory_cache[conversation.conversation_id]
    user_messages = [m for m in cached_messages if m.role == CoachMessageRole.USER]
    assert len(user_messages) == 2
    assert "concentration" in user_messages[0].content


def test_multi_turn_context_with_storage_enabled(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
    fake_conversation_repo: MagicMock,
) -> None:
    """Multi-turn context is preserved via repo when storage is enabled."""
    conversation = conversation_service.start_conversation("user_1")

    settings = Settings(store_conversations=True, coach_use_llm=True)
    fake_conversation_repo.save_message.reset_mock()

    # Track persisted messages
    persisted_messages: list[CoachMessage] = []

    def mock_save_message(msg: CoachMessage) -> None:
        persisted_messages.append(msg)

    fake_conversation_repo.save_message.side_effect = mock_save_message
    fake_conversation_repo.get_messages.return_value = persisted_messages

    # Mock provider for valid responses
    fake_provider = MagicMock()
    fake_provider.complete.return_value = MagicMock(text="Response about concentration")

    # First message
    conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="My goal is to improve my concentration",
        profile=sample_profile,
        provider=fake_provider,
        settings=settings,
    )

    # Verify persistence to repo
    assert fake_conversation_repo.save_message.call_count == 2
    assert len(persisted_messages) == 2

    # Second message
    conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="What goal did I mention?",
        profile=sample_profile,
        provider=fake_provider,
        settings=settings,
    )

    # Verify persistence to repo (4 total: 2 messages * 2 turns)
    assert fake_conversation_repo.save_message.call_count == 4
    assert len(persisted_messages) == 4

    # Verify memory cache is NOT used when storage is enabled
    assert len(conversation_service._memory_cache.get(conversation.conversation_id, [])) == 0


def test_fallback_when_llm_disabled(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
) -> None:
    """Fallback returns safe message when LLM is disabled."""
    conversation = conversation_service.start_conversation("user_1")

    settings = Settings(coach_use_llm=False)
    response = conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="Test message",
        profile=sample_profile,
        provider=None,
        settings=settings,
    )

    # Should return safe fallback message, not context
    assert "The conversation service is temporarily unavailable" in response.content
    # Context markers should NOT be present
    assert "Recent conversation:" not in response.content
    assert "Cognitive profile summary:" not in response.content
    assert "Based on the tasks completed so far" not in response.content


def test_fallback_when_provider_none(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
) -> None:
    """Fallback returns safe message when provider is None."""
    conversation = conversation_service.start_conversation("user_1")

    settings = Settings(coach_use_llm=True)
    response = conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="Test message",
        profile=sample_profile,
        provider=None,
        settings=settings,
    )

    # Should return safe fallback message, not context
    assert "The conversation service is temporarily unavailable" in response.content
    # Context markers should NOT be present
    assert "Recent conversation:" not in response.content
    assert "Cognitive profile summary:" not in response.content


def test_fallback_when_validation_fails(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
) -> None:
    """Fallback returns safe message when LLM response fails validation."""
    conversation = conversation_service.start_conversation("user_1")

    # Mock provider that returns forbidden word
    fake_provider = MagicMock()
    fake_provider.complete.return_value = MagicMock(text="This is a diagnosis for you.")

    settings = Settings(coach_use_llm=True)
    response = conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="Test message",
        profile=sample_profile,
        provider=fake_provider,
        settings=settings,
    )

    # Should return safe fallback message, not context
    assert "The conversation service is temporarily unavailable" in response.content
    # Context markers should NOT be present
    assert "Recent conversation:" not in response.content
    assert "Cognitive profile summary:" not in response.content
    # Forbidden word should NOT be present
    assert "diagnosis" not in response.content.lower()


def test_fallback_when_provider_raises_exception(
    conversation_service: ConversationService,
    sample_profile: CognitiveProfile,
) -> None:
    """Fallback returns safe message when provider raises an exception."""
    conversation = conversation_service.start_conversation("user_1")

    # Mock provider that raises an exception
    fake_provider = MagicMock()
    fake_provider.complete.side_effect = Exception("Provider error")

    settings = Settings(coach_use_llm=True)
    response = conversation_service.add_message_and_get_response(
        conversation_id=conversation.conversation_id,
        user_message="Test message",
        profile=sample_profile,
        provider=fake_provider,
        settings=settings,
    )

    # Should return safe fallback message, not context
    assert "The conversation service is temporarily unavailable" in response.content
    # Context markers should NOT be present
    assert "Recent conversation:" not in response.content
    assert "Cognitive profile summary:" not in response.content
