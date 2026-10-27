"""Unit tests for SQLite IOI event persistence."""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest

from coglayer.api.db.sqlite import SQLiteAssessmentRepository, SQLiteIOIEventRepository
from coglayer.core.exceptions import (
    DuplicateIOIEventError,
    IOIOpportunityConflictError,
    IOISessionOwnershipError,
)
from coglayer.core.models import (
    IOIComponent,
    IOIEventType,
    IOIObservation,
    Session,
    SessionStatus,
)

TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def _observation(
    *,
    event_id: str = "event-1",
    user_id: str = "user-1",
    session_id: str = "session-1",
    opportunity_id: str = "opportunity-1",
    observed: bool = True,
) -> IOIObservation:
    return IOIObservation(
        event_id=event_id,
        user_id=user_id,
        session_id=session_id,
        component=IOIComponent.CLARIFICATION,
        event_type=IOIEventType.CLARIFICATION_OPPORTUNITY,
        opportunity_id=opportunity_id,
        behavior_observed=observed,
        timestamp=TIMESTAMP,
        schema_version="1.0",
    )


def _session(user_id: str = "user-1") -> Session:
    return Session(
        session_id="session-1",
        user_id=user_id,
        start_time=TIMESTAMP,
        end_time=None,
        status=SessionStatus.PENDING,
        completed_tasks=[],
    )


def test_event_round_trip_and_exact_duplicate_is_idempotent(tmp_path: pathlib.Path) -> None:
    db_path = str(tmp_path / "ioi.db")
    SQLiteAssessmentRepository(db_path).save_session(_session())
    repo = SQLiteIOIEventRepository(db_path)
    event = _observation()

    assert repo.save_event(event) is True
    assert repo.save_event(event) is False
    assert repo.get_events("user-1") == [event]


def test_conflicting_event_id_is_rejected(tmp_path: pathlib.Path) -> None:
    db_path = str(tmp_path / "ioi.db")
    SQLiteAssessmentRepository(db_path).save_session(_session())
    repo = SQLiteIOIEventRepository(db_path)
    repo.save_event(_observation())

    with pytest.raises(DuplicateIOIEventError):
        repo.save_event(_observation(observed=False))


def test_conflicting_opportunity_is_rejected(tmp_path: pathlib.Path) -> None:
    db_path = str(tmp_path / "ioi.db")
    SQLiteAssessmentRepository(db_path).save_session(_session())
    repo = SQLiteIOIEventRepository(db_path)
    repo.save_event(_observation())

    with pytest.raises(IOIOpportunityConflictError):
        repo.save_event(_observation(event_id="event-2", observed=False))


def test_session_owner_is_enforced(tmp_path: pathlib.Path) -> None:
    db_path = str(tmp_path / "ioi.db")
    SQLiteAssessmentRepository(db_path).save_session(_session())
    repo = SQLiteIOIEventRepository(db_path)

    with pytest.raises(IOISessionOwnershipError):
        repo.save_event(_observation(user_id="other-user"))


def test_delete_user_removes_ioi_events_only_for_that_user(tmp_path: pathlib.Path) -> None:
    db_path = str(tmp_path / "ioi.db")
    assessment_repo = SQLiteAssessmentRepository(db_path)
    assessment_repo.save_session(_session("user-1"))
    assessment_repo.save_session(
        Session(
            session_id="session-2",
            user_id="user-2",
            start_time=TIMESTAMP,
            end_time=None,
            status=SessionStatus.PENDING,
            completed_tasks=[],
        )
    )
    repo = SQLiteIOIEventRepository(db_path)
    repo.save_event(_observation())
    repo.save_event(_observation(event_id="event-2", user_id="user-2", session_id="session-2"))

    repo.delete_user("user-1")

    assert repo.get_events("user-1") == []
    assert len(repo.get_events("user-2")) == 1
