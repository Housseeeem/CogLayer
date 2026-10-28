"""Unit tests for SQLite storage repositories.

Covers: SQLiteAssessmentRepository, SQLiteProfileRepository, SQLiteConsentRepository.

Acceptance criteria tested:
  test_ac_storage_raw_trials_retained  — trials round-trip through save/get
  test_ac_double_submission  — duplicate (session_id, task_id) raises DuplicateSubmissionError

Requirements: R-005.1, R-005.2, R-005.3, R-005.4, R-005.5, R-001.2
"""

from __future__ import annotations

import pathlib
import uuid
from datetime import UTC, datetime

import pytest

from coglayer.api.db.sqlite import (
    SQLiteAssessmentRepository,
    SQLiteConsentRepository,
    SQLiteProfileRepository,
)
from coglayer.core.exceptions import DuplicateSubmissionError
from coglayer.core.models import (
    CognitiveProfile,
    ConsentRecord,
    DataQuality,
    Session,
    SessionStatus,
    Signal,
    TaskResult,
    Trial,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TIMESTAMP = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)


def _session(user_id: str = "user1", session_id: str | None = None) -> Session:
    return Session(
        session_id=session_id or str(uuid.uuid4()),
        user_id=user_id,
        start_time=TIMESTAMP,
        end_time=None,
        status=SessionStatus.PENDING,
        completed_tasks=[],
    )


def _trial(
    stimulus: str = "go",
    valid: bool = True,
    response: str | None = "press",
    rt_ms: float = 250.0,
) -> Trial:
    return Trial(
        stimulus=stimulus,
        expected="press" if stimulus == "go" else "inhibit",
        response=response,
        rt_ms=rt_ms,
        timestamp=TIMESTAMP,
        valid=valid,
        invalid_reason=None if valid else "anticipation",
    )


def _result(
    session_id: str,
    user_id: str = "user1",
    task_id: str = "go_no_go",
    trials: list[Trial] | None = None,
) -> TaskResult:
    t = trials or [_trial(), _trial("nogo", response=None)]
    dq = DataQuality(
        valid_trials=sum(1 for tr in t if tr.valid),
        total_trials=len(t),
        completeness=sum(1 for tr in t if tr.valid) / len(t),
        anomalies=[],
    )
    return TaskResult(
        task_id=task_id,
        task_version="1.0",
        session_id=session_id,
        user_id=user_id,
        trials=t,
        metrics={"accuracy": 0.8, "valid_trial_count": float(dq.valid_trials)},
        signals=[],
        target_dimensions=["response_inhibition"],
        data_quality=dq,
        uncertainty=None,
    )


# ---------------------------------------------------------------------------
# SQLiteAssessmentRepository tests
# ---------------------------------------------------------------------------


def test_save_and_get_session(tmp_path: pathlib.Path) -> None:
    """save_session then get_session returns the same data."""
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    sess = _session()
    repo.save_session(sess)
    loaded = repo.get_session(sess.session_id)
    assert loaded is not None
    assert loaded.session_id == sess.session_id
    assert loaded.user_id == sess.user_id
    assert loaded.status == SessionStatus.PENDING
    assert loaded.completed_tasks == []


def test_get_session_not_found(tmp_path: pathlib.Path) -> None:
    """get_session returns None for a non-existent session_id."""
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    assert repo.get_session("does-not-exist") is None


def test_update_session_status(tmp_path: pathlib.Path) -> None:
    """update_session_status changes the status field."""
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    sess = _session()
    repo.save_session(sess)
    repo.update_session_status(sess.session_id, SessionStatus.IN_PROGRESS)
    loaded = repo.get_session(sess.session_id)
    assert loaded is not None
    assert loaded.status == SessionStatus.IN_PROGRESS


def test_get_sessions_by_user(tmp_path: pathlib.Path) -> None:
    """get_sessions_by_user returns all sessions for user ordered by start_time."""
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    assert repo.get_sessions_by_user("alice") == []

    sess1 = Session(
        session_id="s1",
        user_id="alice",
        start_time=TIMESTAMP,
        end_time=None,
        status=SessionStatus.PENDING,
        completed_tasks=[],
    )
    sess2 = Session(
        session_id="s2",
        user_id="alice",
        start_time=TIMESTAMP.replace(hour=11),
        end_time=None,
        status=SessionStatus.PENDING,
        completed_tasks=[],
    )
    sess3 = Session(
        session_id="s3",
        user_id="bob",
        start_time=TIMESTAMP,
        end_time=None,
        status=SessionStatus.PENDING,
        completed_tasks=[],
    )
    repo.save_session(sess1)
    repo.save_session(sess2)
    repo.save_session(sess3)

    alice_sessions = repo.get_sessions_by_user("alice")
    assert len(alice_sessions) == 2
    assert [s.session_id for s in alice_sessions] == ["s1", "s2"]
    assert len(repo.get_sessions_by_user("bob")) == 1


def test_ac_storage_raw_trials_retained(tmp_path: pathlib.Path) -> None:
    """REQ-011 test_ac_storage_raw_trials_retained.

    After submitting a TaskResult, get_results returns all original trials.
    """
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    sess = _session()
    repo.save_session(sess)

    trials = [
        _trial("go", valid=True, response="press", rt_ms=200.0),
        _trial("nogo", valid=True, response=None, rt_ms=0.0),
        _trial("go", valid=False, response="press", rt_ms=80.0),  # anticipation
    ]
    # Set invalid_reason on the anticipation trial
    trials[2] = Trial(
        stimulus="go",
        expected="press",
        response="press",
        rt_ms=80.0,
        timestamp=TIMESTAMP,
        valid=False,
        invalid_reason="anticipation",
    )
    result = _result(sess.session_id, trials=trials)
    repo.save_result(result)

    loaded_results = repo.get_results(sess.session_id)
    assert len(loaded_results) == 1
    loaded = loaded_results[0]

    assert len(loaded.trials) == 3
    assert loaded.trials[0].stimulus == "go"
    assert loaded.trials[0].valid is True
    assert loaded.trials[1].stimulus == "nogo"
    assert loaded.trials[1].response is None
    assert loaded.trials[2].valid is False
    assert loaded.trials[2].invalid_reason == "anticipation"


def test_get_results_empty(tmp_path: pathlib.Path) -> None:
    """get_results returns empty list for a session with no results."""
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    sess = _session()
    repo.save_session(sess)
    assert repo.get_results(sess.session_id) == []


def test_ac_double_submission(tmp_path: pathlib.Path) -> None:
    """REQ-011 test_ac_double_submission.

    Saving the same (session_id, task_id) twice raises DuplicateSubmissionError
    and leaves the first result intact.
    """
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    sess = _session()
    repo.save_session(sess)

    first = _result(sess.session_id, trials=[_trial(rt_ms=200.0)])
    repo.save_result(first)

    second = _result(sess.session_id, trials=[_trial(rt_ms=999.0)])
    with pytest.raises(DuplicateSubmissionError) as exc_info:
        repo.save_result(second)

    assert exc_info.value.session_id == sess.session_id
    assert exc_info.value.task_id == "go_no_go"

    # First result must remain intact
    loaded_results = repo.get_results(sess.session_id)
    assert len(loaded_results) == 1
    assert loaded_results[0].trials[0].rt_ms == pytest.approx(200.0)


def test_delete_user_removes_sessions(tmp_path: pathlib.Path) -> None:
    """delete_user removes sessions and their cascade-deleted child rows."""
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    sess = _session(user_id="victim")
    repo.save_session(sess)
    repo.save_result(_result(sess.session_id, user_id="victim"))

    repo.delete_user("victim")

    assert repo.get_session(sess.session_id) is None
    assert repo.get_results(sess.session_id) == []


def test_delete_user_leaves_other_users(tmp_path: pathlib.Path) -> None:
    """delete_user does not affect other users' data."""
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    sess_victim = _session(user_id="victim", session_id="sess-v")
    sess_other = _session(user_id="other", session_id="sess-o")
    repo.save_session(sess_victim)
    repo.save_session(sess_other)
    repo.save_result(_result("sess-v", user_id="victim"))
    repo.save_result(_result("sess-o", user_id="other"))

    repo.delete_user("victim")

    assert repo.get_session("sess-v") is None
    assert repo.get_session("sess-o") is not None
    assert len(repo.get_results("sess-o")) == 1


# ---------------------------------------------------------------------------
# SQLiteProfileRepository tests
# ---------------------------------------------------------------------------


def test_profile_round_trip(tmp_path: pathlib.Path) -> None:
    """save_profile then get_profile returns equal data."""
    repo = SQLiteProfileRepository(str(tmp_path / "test.db"))
    profile = CognitiveProfile(
        user_id="alice",
        dimensions={},
        evidence_history=[],
        data_quality={},
        uncertainty={},
    )
    repo.save_profile(profile)
    loaded = repo.get_profile("alice")
    assert loaded is not None
    assert loaded.user_id == "alice"
    assert loaded.dimensions == {}


def test_get_profile_not_found(tmp_path: pathlib.Path) -> None:
    repo = SQLiteProfileRepository(str(tmp_path / "test.db"))
    assert repo.get_profile("ghost") is None


def test_profile_delete_user(tmp_path: pathlib.Path) -> None:
    repo = SQLiteProfileRepository(str(tmp_path / "test.db"))
    profile = CognitiveProfile(
        user_id="alice",
        dimensions={},
        evidence_history=[],
        data_quality={},
        uncertainty={},
    )
    repo.save_profile(profile)
    repo.delete_user("alice")
    assert repo.get_profile("alice") is None


# ---------------------------------------------------------------------------
# SQLiteConsentRepository tests
# ---------------------------------------------------------------------------


def test_consent_round_trip(tmp_path: pathlib.Path) -> None:
    repo = SQLiteConsentRepository(str(tmp_path / "test.db"))
    record = ConsentRecord(
        user_id="alice",
        consented_at=TIMESTAMP,
        revoked_at=None,
        guardian_consent=False,
        guardian_id=None,
    )
    repo.save_consent(record)
    loaded = repo.get_consent("alice")
    assert loaded is not None
    assert loaded.user_id == "alice"
    assert loaded.revoked_at is None
    assert loaded.guardian_consent is False
    assert loaded.guardian_id is None


def test_consent_revoke_persists(tmp_path: pathlib.Path) -> None:
    repo = SQLiteConsentRepository(str(tmp_path / "test.db"))
    record = ConsentRecord(
        user_id="bob",
        consented_at=TIMESTAMP,
        revoked_at=None,
        guardian_consent=False,
        guardian_id=None,
    )
    repo.save_consent(record)
    revoked = ConsentRecord(
        user_id="bob",
        consented_at=TIMESTAMP,
        revoked_at=TIMESTAMP,
        guardian_consent=False,
        guardian_id=None,
    )
    repo.save_consent(revoked)
    loaded = repo.get_consent("bob")
    assert loaded is not None
    assert loaded.revoked_at is not None


def test_consent_delete_user(tmp_path: pathlib.Path) -> None:
    repo = SQLiteConsentRepository(str(tmp_path / "test.db"))
    record = ConsentRecord(
        user_id="alice",
        consented_at=TIMESTAMP,
        revoked_at=None,
        guardian_consent=False,
        guardian_id=None,
    )
    repo.save_consent(record)
    repo.delete_consent("alice")
    assert repo.get_consent("alice") is None


# ---------------------------------------------------------------------------
# New pre-flight tests
# ---------------------------------------------------------------------------


def test_task_result_full_round_trip(tmp_path: pathlib.Path) -> None:
    """Full TaskResult round-trip: retrieved == original for all fields."""
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    session = _session()
    repo.save_session(session)

    # Use TIMESTAMP (no sub-second precision) so ISO round-trip is lossless.
    trial = Trial(
        stimulus="go",
        expected="press",
        response="press",
        rt_ms=250.0,
        timestamp=TIMESTAMP,
        valid=True,
        invalid_reason=None,
    )
    dq = DataQuality(valid_trials=1, total_trials=1, completeness=1.0, anomalies=["test_anomaly"])
    signals = [Signal(name="rt", value=250.0), Signal(name="accuracy", value=1.0)]

    original = TaskResult(
        task_id="go_no_go",
        task_version="2.1",
        session_id=session.session_id,
        user_id=session.user_id,
        trials=[trial],
        metrics={"accuracy": 1.0, "mean_rt_ms": 250.0},
        signals=signals,
        target_dimensions=["response_inhibition", "attention"],
        data_quality=dq,
        uncertainty=0.1,
    )

    repo.save_result(original)
    results = repo.get_results(session.session_id)

    assert len(results) == 1
    retrieved = results[0]
    assert retrieved == original


def test_zero_trial_result_returned(tmp_path: pathlib.Path) -> None:
    """A zero-trial result is still returned."""
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    session = _session()
    repo.save_session(session)

    dq = DataQuality(valid_trials=0, total_trials=0, completeness=0.0, anomalies=[])
    zero_trial_result = TaskResult(
        task_id="sequence_span",
        task_version="1.0",
        session_id=session.session_id,
        user_id=session.user_id,
        trials=[],
        metrics={"sequences_completed": 0.0},
        signals=[],
        target_dimensions=["sequential_visual_memory"],
        data_quality=dq,
        uncertainty=None,
    )

    repo.save_result(zero_trial_result)
    results = repo.get_results(session.session_id)

    assert len(results) == 1
    retrieved = results[0]
    assert retrieved.task_id == "sequence_span"
    assert len(retrieved.trials) == 0
    assert retrieved.data_quality.total_trials == 0


def test_save_session_after_save_result_keeps_result(tmp_path: pathlib.Path) -> None:
    """save_session after save_result keeps the result and its trials (cascade regression)."""
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    session = _session()
    repo.save_session(session)

    result = _result(session.session_id, session.user_id)
    repo.save_result(result)

    results_before = repo.get_results(session.session_id)
    assert len(results_before) == 1
    trials_before = len(results_before[0].trials)

    # Update session (INSERT OR REPLACE used to cascade-delete child rows)
    updated_session = Session(
        session_id=session.session_id,
        user_id=session.user_id,
        start_time=session.start_time,
        end_time=TIMESTAMP,
        status=SessionStatus.COMPLETED,
        completed_tasks=["go_no_go"],
    )
    repo.save_session(updated_session)

    results_after = repo.get_results(session.session_id)
    assert len(results_after) == 1
    assert len(results_after[0].trials) == trials_before
    assert results_after[0].task_id == result.task_id


def test_duplicate_submission_preserves_first_result(tmp_path: pathlib.Path) -> None:
    """After a rejected duplicate, the FIRST result's metrics and trials are unchanged."""
    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    session = _session()
    repo.save_session(session)

    first_result = _result(session.session_id, session.user_id)
    first_result.metrics = {"accuracy": 0.8, "mean_rt_ms": 300.0}
    repo.save_result(first_result)

    results = repo.get_results(session.session_id)
    assert len(results) == 1
    assert results[0].metrics["accuracy"] == 0.8
    original_trial_count = len(results[0].trials)

    duplicate_result = _result(session.session_id, session.user_id)
    duplicate_result.metrics = {"accuracy": 0.95, "mean_rt_ms": 200.0}

    with pytest.raises(DuplicateSubmissionError):
        repo.save_result(duplicate_result)

    results_after = repo.get_results(session.session_id)
    assert len(results_after) == 1
    assert results_after[0].metrics["accuracy"] == 0.8
    assert results_after[0].metrics["mean_rt_ms"] == 300.0
    assert len(results_after[0].trials) == original_trial_count


def test_save_result_unknown_session_raises_integrity_error(tmp_path: pathlib.Path) -> None:
    """Saving a result for a non-existent session_id raises sqlite3.IntegrityError.

    This is a FK violation — NOT a DuplicateSubmissionError.
    """
    import sqlite3 as _sqlite3

    repo = SQLiteAssessmentRepository(str(tmp_path / "test.db"))
    # Deliberately do NOT create a session
    result = _result("nonexistent-session-id", "user1")
    with pytest.raises(_sqlite3.IntegrityError):
        repo.save_result(result)
