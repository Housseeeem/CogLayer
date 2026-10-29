"""Unit and API tests for coach age-group adaptation.

Tests verify:
- Refusal (HTTP 403) of free text chat for child accounts.
- Predefined message handling for child accounts with strictly NO LLM call.
- FakeProvider that raises an error if called is NOT invoked for child.
- No text persistence for child and teen accounts in the SQLite database.
- Free text allowed for teen and adult accounts.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.api.db.sqlite import (
    SQLiteAssessmentRepository,
    SQLiteConsentRepository,
    SQLiteConversationRepository,
    SQLiteExperienceProfileRepository,
)
from coglayer.api.deps import get_llm_provider
from coglayer.core.models import (
    AgeGroup,
    ConsentRecord,
    DataQuality,
    ExperienceProfile,
    GuidanceLevel,
    InfoStyle,
    LayoutType,
    Session,
    SessionStatus,
    TaskResult,
    TechComfort,
    ThemeType,
)
from coglayer.core.protocols import LLMProvider, LLMRequest, LLMResponse
from coglayer.core.settings import Settings


class FailingLLMProvider:
    """Mock provider that raises an exception if called."""

    def complete(self, request: LLMRequest) -> LLMResponse:
        raise AssertionError("LLMProvider.complete should NOT be called!")


@pytest.fixture(autouse=True)
def reset_conversation_service() -> Generator[None, None, None]:
    import coglayer.api.deps as deps

    orig = deps._conversation_service_singleton
    deps._conversation_service_singleton = None
    yield
    deps._conversation_service_singleton = orig


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "coach_adaptation_test.db")


@pytest.fixture
def settings(db_path: str) -> Settings:
    return Settings(
        db_path=db_path,
        store_conversations=True,  # Global storage enabled
        coach_use_llm=True,
    )


def _setup_completed_user(
    db_path: str,
    user_id: str,
    age_group: AgeGroup,
    guardian_consent: bool = True,
) -> None:
    """Setup consent, experience profile, and a completed session for user."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)

    # Consent
    consent_repo = SQLiteConsentRepository(db_path)
    consent_repo.save_consent(
        ConsentRecord(
            user_id=user_id,
            consented_at=now,
            guardian_consent=guardian_consent,
        )
    )

    # Experience Profile
    exp_repo = SQLiteExperienceProfileRepository(db_path)
    exp_repo.save_profile(
        ExperienceProfile(
            user_id=user_id,
            age_group=age_group,
            goals=["improve_focus"],
            tech_comfort=TechComfort.COMFORTABLE,
            info_style=InfoStyle.CONVERSATIONAL,
            layout=LayoutType.GUIDED_JOURNEY,
            theme=ThemeType.STANDARD,
            guidance_level=GuidanceLevel.SOME,
        )
    )

    # Completed session so coach is unlocked
    assess_repo = SQLiteAssessmentRepository(db_path)
    session_id = f"sess_{user_id}"
    session = Session(
        session_id=session_id,
        user_id=user_id,
        start_time=now,
        end_time=now,
        status=SessionStatus.COMPLETED,
        completed_tasks=["go_no_go", "sequence_span"],
    )
    assess_repo.save_session(session)
    for task_id in ["go_no_go", "sequence_span"]:
        res = TaskResult(
            task_id=task_id,
            task_version="1.0",
            session_id=session_id,
            user_id=user_id,
            trials=[],
            metrics={},
            signals=[],
            target_dimensions=[],
            data_quality=DataQuality(
                valid_trials=10,
                total_trials=10,
                completeness=1.0,
                anomalies=[],
            ),
            uncertainty=None,
        )
        assess_repo.save_result(res)


def test_child_free_text_rejected_with_403(settings: Settings) -> None:
    """Child user sending free text is rejected with HTTP 403."""
    user_id = "child_user"
    _setup_completed_user(settings.db_path, user_id, AgeGroup.CHILD_7_12)

    app = create_app(settings)
    client = TestClient(app)

    # Start conversation
    resp = client.post(f"/v1/assessment/coach/{user_id}/conversations")
    assert resp.status_code == 200
    conv_id = resp.json()["conversation_id"]

    # Free text message (is_predefined=False by default)
    msg_resp = client.post(
        f"/v1/assessment/coach/{user_id}/conversations/{conv_id}/messages",
        json={"content": "Can you help me with my homework?"},
    )
    assert msg_resp.status_code == 403
    assert "Free text messages are not permitted for child accounts" in msg_resp.json()["detail"]


def test_child_tampered_predefined_flag_rejected(settings: Settings) -> None:
    """Child sending arbitrary content with is_predefined=True is still rejected with 403."""
    user_id = "child_user_tamper"
    _setup_completed_user(settings.db_path, user_id, AgeGroup.CHILD_7_12)

    app = create_app(settings)
    client = TestClient(app)

    resp = client.post(f"/v1/assessment/coach/{user_id}/conversations")
    conv_id = resp.json()["conversation_id"]

    msg_resp = client.post(
        f"/v1/assessment/coach/{user_id}/conversations/{conv_id}/messages",
        json={"content": "arbitrary unapproved text", "is_predefined": True},
    )
    assert msg_resp.status_code == 403


def test_child_predefined_message_succeeds_without_llm(settings: Settings) -> None:
    """Child sending valid predefined message succeeds and never calls LLM."""
    user_id = "child_user_ok"
    _setup_completed_user(settings.db_path, user_id, AgeGroup.CHILD_7_12)

    app = create_app(settings)
    # Override LLM provider with FailingLLMProvider to guarantee it is NOT called
    failing_provider = FailingLLMProvider()
    app.dependency_overrides[get_llm_provider] = lambda: failing_provider

    client = TestClient(app)

    resp = client.post(f"/v1/assessment/coach/{user_id}/conversations")
    assert resp.status_code == 200
    conv_id = resp.json()["conversation_id"]

    # Valid predefined option
    msg_resp = client.post(
        f"/v1/assessment/coach/{user_id}/conversations/{conv_id}/messages",
        json={"content": "How am I doing?", "is_predefined": True},
    )
    assert msg_resp.status_code == 200
    data = msg_resp.json()
    assert "Great effort!" in data["content"]


def test_child_and_teen_messages_not_stored_in_db(settings: Settings) -> None:
    """Child and Teen messages are not persisted in SQLite even when store_conversations is True."""
    child_id = "child_user_privacy"
    teen_id = "teen_user_privacy"
    adult_id = "adult_user_privacy"

    _setup_completed_user(settings.db_path, child_id, AgeGroup.CHILD_7_12)
    _setup_completed_user(settings.db_path, teen_id, AgeGroup.TEEN_13_17)
    _setup_completed_user(settings.db_path, adult_id, AgeGroup.ADULT_31_60)

    # Use a dummy provider for teen and adult
    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider.complete.return_value = LLMResponse(
        text="You are making steady progress with regular cognitive practice. Keep it up!"
    )

    app = create_app(settings)
    app.dependency_overrides[get_llm_provider] = lambda: mock_provider
    client = TestClient(app)

    # 1. Child turn
    child_resp = client.post(f"/v1/assessment/coach/{child_id}/conversations")
    child_conv = child_resp.json()["conversation_id"]
    client.post(
        f"/v1/assessment/coach/{child_id}/conversations/{child_conv}/messages",
        json={"content": "Time for a short break", "is_predefined": True},
    )

    # 2. Teen turn
    teen_resp = client.post(f"/v1/assessment/coach/{teen_id}/conversations")
    teen_conv = teen_resp.json()["conversation_id"]
    client.post(
        f"/v1/assessment/coach/{teen_id}/conversations/{teen_conv}/messages",
        json={"content": "How did I do on today's tasks?"},
    )

    # 3. Adult turn
    adult_resp = client.post(f"/v1/assessment/coach/{adult_id}/conversations")
    adult_conv = adult_resp.json()["conversation_id"]
    client.post(
        f"/v1/assessment/coach/{adult_id}/conversations/{adult_conv}/messages",
        json={"content": "How did I do on today's tasks?"},
    )

    # Check database persistence
    conv_repo = SQLiteConversationRepository(settings.db_path)
    child_messages = conv_repo.get_messages(child_conv)
    teen_messages = conv_repo.get_messages(teen_conv)
    adult_messages = conv_repo.get_messages(adult_conv)

    assert len(child_messages) == 0, "Child messages must NOT be persisted to database"
    assert len(teen_messages) == 0, "Teen messages must NOT be persisted to database"
    assert len(adult_messages) > 0, "Adult messages should be persisted when enabled"
