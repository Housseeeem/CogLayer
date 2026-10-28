"""Tests for conversation API endpoints.

Tests cover authorization, consent checks, and conversation lifecycle.
Uses mock for coach availability to avoid complex session completion setup.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.core.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def clear_singletons() -> Generator[None, None, None]:
    """Clear module-level singletons between tests."""
    import coglayer.api.deps as deps_module

    original = getattr(deps_module, "_conversation_service_singleton", None)
    deps_module._conversation_service_singleton = None
    get_settings.cache_clear()
    yield
    deps_module._conversation_service_singleton = original
    get_settings.cache_clear()


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """Create a FastAPI TestClient with isolated SQLite database."""
    settings = Settings(
        _env_file=None,
        db_path=str(tmp_path / "conversation_test.db"),
        store_conversations=True,
    )
    app = create_app(settings)
    # Override get_db_settings to return our test settings
    from coglayer.api.deps import get_db_settings

    app.dependency_overrides[get_db_settings] = lambda: settings
    client = TestClient(app)
    yield client
    # Clean up override
    app.dependency_overrides.clear()


@pytest.fixture
def _setup_user(client: TestClient) -> str:
    """Setup a consented user with basic session data."""
    user_id = "test_user_conv"

    # Give consent
    consent_resp = client.post("/v1/assessment/consent", json={"user_id": user_id})
    assert consent_resp.status_code == 201, f"Consent failed: {consent_resp.text}"

    # Create a session (no tasks needed for mocked availability)
    session_resp = client.post("/v1/assessment/sessions", json={"user_id": user_id})
    assert session_resp.status_code == 201, f"Session creation failed: {session_resp.text}"

    return user_id


def test_start_conversation_requires_consent(client: TestClient) -> None:
    """Starting a conversation requires active consent."""
    resp = client.post("/v1/assessment/coach/no_consent/conversations")
    assert resp.status_code == 403
    assert "consent" in resp.json()["detail"].lower()


def test_start_conversation_requires_completion(client: TestClient) -> None:
    """Starting a conversation requires completed assessment session."""
    user_id = "incomplete_user"

    # Give consent
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    # Create a session but don't submit any tasks
    client.post("/v1/assessment/sessions", json={"user_id": user_id})

    # Try to start conversation - should fail due to incomplete assessment
    resp = client.post(f"/v1/assessment/coach/{user_id}/conversations")
    assert resp.status_code == 403
    assert "assessment" in resp.json()["detail"].lower()


def test_start_conversation_success(
    client: TestClient,
    _setup_user: str,
) -> None:
    """Successfully starting a conversation returns a conversation ID."""
    user_id = _setup_user

    # Mock coach availability to True for testing
    with patch("coglayer.coach.coach.CognitiveCoach.is_available", return_value=True):
        resp = client.post(f"/v1/assessment/coach/{user_id}/conversations")

    assert resp.status_code == 200
    data = resp.json()
    assert "conversation_id" in data
    assert len(data["conversation_id"]) > 0


def test_add_message_requires_consent(client: TestClient) -> None:
    """Adding a message requires active consent."""
    resp = client.post(
        "/v1/assessment/coach/no_consent/conversations/conv_1/messages",
        json={"content": "Hello"},
    )
    assert resp.status_code == 403


def test_add_message_requires_ownership(
    client: TestClient,
    _setup_user: str,
) -> None:
    """Adding a message requires conversation ownership."""
    user_id = _setup_user

    # Start a conversation for user_1
    with patch("coglayer.coach.coach.CognitiveCoach.is_available", return_value=True):
        start_resp = client.post(f"/v1/assessment/coach/{user_id}/conversations")
    conv_id = start_resp.json()["conversation_id"]

    # Try to add message as different user (give consent to other_user first)
    client.post("/v1/assessment/consent", json={"user_id": "other_user"})
    resp = client.post(
        f"/v1/assessment/coach/other_user/conversations/{conv_id}/messages",
        json={"content": "Hello"},
    )
    assert resp.status_code == 403


def test_add_message_success(
    client: TestClient,
    _setup_user: str,
) -> None:
    """Successfully adding a message returns assistant response."""
    user_id = _setup_user

    # Start conversation
    with patch("coglayer.coach.coach.CognitiveCoach.is_available", return_value=True):
        start_resp = client.post(f"/v1/assessment/coach/{user_id}/conversations")
    conv_id = start_resp.json()["conversation_id"]

    # Add message
    resp = client.post(
        f"/v1/assessment/coach/{user_id}/conversations/{conv_id}/messages",
        json={"content": "How am I doing?"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data
    assert len(data["content"]) > 0


def test_list_conversations_requires_consent(client: TestClient) -> None:
    """Listing conversations requires active consent."""
    resp = client.get("/v1/assessment/coach/no_consent/conversations")
    assert resp.status_code == 403


def test_list_conversations_success(
    client: TestClient,
    _setup_user: str,
) -> None:
    """Successfully listing conversations returns list of conversations."""
    user_id = _setup_user

    # Start a conversation
    with patch("coglayer.coach.coach.CognitiveCoach.is_available", return_value=True):
        client.post(f"/v1/assessment/coach/{user_id}/conversations")

    # List conversations
    resp = client.get(f"/v1/assessment/coach/{user_id}/conversations")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "conversation_id" in data[0]
    assert "created_at" in data[0]


def test_get_conversation_requires_consent(client: TestClient) -> None:
    """Getting a conversation requires active consent."""
    resp = client.get("/v1/assessment/coach/no_consent/conversations/conv_1")
    assert resp.status_code == 403


def test_get_conversation_requires_ownership(
    client: TestClient,
    _setup_user: str,
) -> None:
    """Getting a conversation requires ownership."""
    user_id = _setup_user

    # Start conversation
    with patch("coglayer.coach.coach.CognitiveCoach.is_available", return_value=True):
        start_resp = client.post(f"/v1/assessment/coach/{user_id}/conversations")
    conv_id = start_resp.json()["conversation_id"]

    # Give consent to other_user
    client.post("/v1/assessment/consent", json={"user_id": "other_user"})

    # Try to get as different user
    resp = client.get(f"/v1/assessment/coach/other_user/conversations/{conv_id}")
    assert resp.status_code == 403


def test_get_conversation_success(
    client: TestClient,
    _setup_user: str,
) -> None:
    """Successfully getting a conversation returns full conversation with messages."""
    user_id = _setup_user

    # Start conversation
    with patch("coglayer.coach.coach.CognitiveCoach.is_available", return_value=True):
        start_resp = client.post(f"/v1/assessment/coach/{user_id}/conversations")
    conv_id = start_resp.json()["conversation_id"]

    # Add a message
    msg_resp = client.post(
        f"/v1/assessment/coach/{user_id}/conversations/{conv_id}/messages",
        json={"content": "Hello"},
    )
    assert msg_resp.status_code == 200, f"Add message failed: {msg_resp.text}"

    # Get conversation
    resp = client.get(f"/v1/assessment/coach/{user_id}/conversations/{conv_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["conversation_id"] == conv_id
    assert "messages" in data
    assert len(data["messages"]) >= 2  # user + assistant
