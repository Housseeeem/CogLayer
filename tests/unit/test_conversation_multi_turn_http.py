"""Tests for multi-turn conversation context across HTTP requests.

Tests verify that the memory cache preserves context between successive HTTP requests
when store_conversations is disabled.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coglayer.api import deps
from coglayer.api.app import create_app
from coglayer.core.protocols import LLMProvider, LLMRequest, LLMResponse
from coglayer.core.settings import Settings, get_settings
from coglayer.providers.fake import FakeProvider


class PromptCapturingProvider:
    """Wrapper around FakeProvider that captures all prompts received."""

    def __init__(self, fake_provider: FakeProvider) -> None:
        self._fake = fake_provider
        self.prompts_received: list[str] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Capture the prompt and delegate to FakeProvider."""
        self.prompts_received.append(request.prompt)
        return self._fake.complete(request)


# Verify structural compatibility at import time
assert isinstance(PromptCapturingProvider(FakeProvider()), LLMProvider)


# Type alias for the fixture return type
ClientWithProvider = tuple[TestClient, PromptCapturingProvider]


@pytest.fixture(autouse=True)
def clear_singletons() -> Generator[None, None, None]:
    """Clear module-level singletons between tests."""
    original = getattr(deps, "_conversation_service_singleton", None)
    deps._conversation_service_singleton = None
    get_settings.cache_clear()
    yield
    deps._conversation_service_singleton = original
    get_settings.cache_clear()


@pytest.fixture
def client(tmp_path: Path) -> Generator[ClientWithProvider, None, None]:
    """Create a FastAPI TestClient with isolated SQLite database."""
    settings = Settings(
        _env_file=None,
        db_path=str(tmp_path / "multi_turn_test.db"),
        store_conversations=False,
        coach_use_llm=True,  # Enable LLM to test context transmission
    )
    app = create_app(settings)
    from coglayer.api.deps import get_db_settings, get_llm_provider

    # Create a prompt-capturing provider
    fake = FakeProvider(seed=42)
    capturing_provider = PromptCapturingProvider(fake)

    app.dependency_overrides[get_db_settings] = lambda: settings
    app.dependency_overrides[get_llm_provider] = lambda: capturing_provider
    client = TestClient(app)
    yield client, capturing_provider
    app.dependency_overrides.clear()


@pytest.fixture
def _setup_user_with_conversation(client: ClientWithProvider) -> tuple[str, str]:
    """Setup a consented user with a conversation."""
    test_client, _ = client  # Unpack the tuple
    user_id = "test_user_multi_turn"

    # Give consent
    test_client.post("/v1/assessment/consent", json={"user_id": user_id})

    # Create a session
    test_client.post("/v1/assessment/sessions", json={"user_id": user_id})

    # Start a conversation (mock coach availability)
    from unittest.mock import patch

    with patch("coglayer.coach.coach.CognitiveCoach.is_available", return_value=True):
        start_resp = test_client.post(f"/v1/assessment/coach/{user_id}/conversations")
    conv_id = start_resp.json()["conversation_id"]

    return user_id, conv_id


def test_multi_turn_context_across_http_requests(
    client: ClientWithProvider,
    _setup_user_with_conversation: tuple[str, str],
) -> None:
    """Multi-turn context is preserved across HTTP requests when storage is disabled."""
    test_client, capturing_provider = client
    user_id, conv_id = _setup_user_with_conversation

    # First message with identifiable information
    resp1 = test_client.post(
        f"/v1/assessment/coach/{user_id}/conversations/{conv_id}/messages",
        json={"content": "My goal is to improve my concentration"},
    )
    assert resp1.status_code == 200
    response1_text = resp1.json()["content"]
    # Check that we got a response (not empty)
    assert len(response1_text) > 0

    # Verify that the memory cache now contains the first turn
    assert deps._conversation_service_singleton is not None
    cache = deps._conversation_service_singleton._memory_cache
    assert conv_id in cache
    assert len(cache[conv_id]) == 2  # user + assistant
    # Verify the content of the first user message
    first_user_msg = next(m for m in cache[conv_id] if m.role.value == "user")
    assert "concentration" in first_user_msg.content

    # Verify that the provider was called once with the first prompt
    assert len(capturing_provider.prompts_received) == 1
    first_prompt = capturing_provider.prompts_received[0]
    # The first prompt should contain the first user message
    assert "concentration" in first_prompt

    # Second message asking about the first
    resp2 = test_client.post(
        f"/v1/assessment/coach/{user_id}/conversations/{conv_id}/messages",
        json={"content": "What goal did I mention?"},
    )
    assert resp2.status_code == 200
    response2_text = resp2.json()["content"]

    # Check that we got a response (not empty)
    assert len(response2_text) > 0

    # Verify that the memory cache now contains both turns (4 messages total)
    assert len(cache[conv_id]) == 4  # 2 turns * 2 messages
    # Verify the content of the second user message
    user_msgs = [m for m in cache[conv_id] if m.role.value == "user"]
    assert len(user_msgs) == 2
    assert "concentration" in user_msgs[0].content
    assert "goal" in user_msgs[1].content

    # Verify that the provider was called twice
    assert len(capturing_provider.prompts_received) == 2
    second_prompt = capturing_provider.prompts_received[1]
    # The second prompt should contain conversation history with the first message
    assert "concentration" in second_prompt
    # Verify that the second prompt contains "Recent conversation:" header
    assert "Recent conversation:" in second_prompt
    # Verify that the second prompt contains both user messages in the history
    assert "My goal is to improve my concentration" in second_prompt
    assert "What goal did I mention?" in second_prompt


def test_memory_cache_survives_across_requests(
    client: ClientWithProvider,
    _setup_user_with_conversation: tuple[str, str],
) -> None:
    """Memory cache in ConversationService survives across HTTP requests."""
    test_client, _ = client
    user_id, conv_id = _setup_user_with_conversation

    # Access the singleton ConversationService to check cache
    # First message
    test_client.post(
        f"/v1/assessment/coach/{user_id}/conversations/{conv_id}/messages",
        json={"content": "First message"},
    )

    # Check that cache has messages
    assert deps._conversation_service_singleton is not None
    cache = deps._conversation_service_singleton._memory_cache
    assert conv_id in cache
    assert len(cache[conv_id]) == 2  # user + assistant

    # Second message
    test_client.post(
        f"/v1/assessment/coach/{user_id}/conversations/{conv_id}/messages",
        json={"content": "Second message"},
    )

    # Check that cache now has 4 messages
    assert len(cache[conv_id]) == 4  # 2 turns * 2 messages


def test_different_conversations_have_separate_caches(
    client: ClientWithProvider,
    _setup_user_with_conversation: tuple[str, str],
) -> None:
    """Different conversations maintain separate memory caches."""
    test_client, _ = client
    user_id, conv_id1 = _setup_user_with_conversation

    # Start a second conversation for the same user
    from unittest.mock import patch

    with patch("coglayer.coach.coach.CognitiveCoach.is_available", return_value=True):
        start_resp2 = test_client.post(f"/v1/assessment/coach/{user_id}/conversations")
    conv_id2 = start_resp2.json()["conversation_id"]

    # Add message to first conversation
    test_client.post(
        f"/v1/assessment/coach/{user_id}/conversations/{conv_id1}/messages",
        json={"content": "Message for conv 1"},
    )

    # Add message to second conversation
    test_client.post(
        f"/v1/assessment/coach/{user_id}/conversations/{conv_id2}/messages",
        json={"content": "Message for conv 2"},
    )

    # Check that caches are separate
    assert deps._conversation_service_singleton is not None
    cache = deps._conversation_service_singleton._memory_cache
    assert conv_id1 in cache
    assert conv_id2 in cache
    assert len(cache[conv_id1]) == 2
    assert len(cache[conv_id2]) == 2

    # Verify messages are in correct conversations
    conv1_messages = cache[conv_id1]
    conv2_messages = cache[conv_id2]
    conv1_user_msgs = [m for m in conv1_messages if m.role.value == "user"]
    conv2_user_msgs = [m for m in conv2_messages if m.role.value == "user"]
    assert "conv 1" in conv1_user_msgs[0].content
    assert "conv 2" in conv2_user_msgs[0].content
