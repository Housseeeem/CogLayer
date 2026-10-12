"""Property test for delete_user completeness.

Property 8: Delete user removes all data — for any user_id for which at
least one session and one profile record exist, calling delete_user must
leave zero sessions, trials, metrics, data-quality rows, profiles, and
consent records for that user_id.

Uses tempfile.TemporaryDirectory (not the tmp_path fixture) so the
Hypothesis health-check for function-scoped fixtures is never triggered.

Tag: # Feature: vertical-slice, Property 8: delete user removes all data
Requirements: R-001.2
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import UTC, datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from coglayer.api.db.sqlite import (
    SQLiteAssessmentRepository,
    SQLiteConsentRepository,
    SQLiteProfileRepository,
)
from coglayer.core.models import (
    CognitiveProfile,
    ConsentRecord,
    DataQuality,
    Session,
    SessionStatus,
    TaskResult,
    Trial,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)


def _make_session(session_id: str, user_id: str) -> Session:
    return Session(
        session_id=session_id,
        user_id=user_id,
        start_time=_TS,
        end_time=None,
        status=SessionStatus.PENDING,
        completed_tasks=[],
    )


def _make_result(session_id: str, user_id: str) -> TaskResult:
    trial = Trial(
        stimulus="go",
        expected="press",
        response="press",
        rt_ms=200.0,
        timestamp=_TS,
        valid=True,
        invalid_reason=None,
    )
    dq = DataQuality(valid_trials=1, total_trials=1, completeness=1.0, anomalies=[])
    return TaskResult(
        task_id="go_no_go",
        task_version="1.0",
        session_id=session_id,
        user_id=user_id,
        trials=[trial],
        metrics={"accuracy": 1.0},
        signals=[],
        target_dimensions=["response_inhibition"],
        data_quality=dq,
        uncertainty=None,
    )


def _make_profile(user_id: str) -> CognitiveProfile:
    return CognitiveProfile(
        user_id=user_id,
        dimensions={},
        evidence_history=[],
        data_quality={},
        uncertainty={},
    )


def _make_consent(user_id: str) -> ConsentRecord:
    return ConsentRecord(user_id=user_id, consented_at=_TS, revoked_at=None)


# ---------------------------------------------------------------------------
# Property 8: Delete user removes all data
# Feature: vertical-slice, Property 8: delete user removes all data
# ---------------------------------------------------------------------------


@settings(max_examples=50, deadline=None)
@given(
    user_suffix=st.one_of(
        st.text(
            min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))
        ),
        st.sampled_from(
            [
                "x' OR '1'='1",
                "a;DROP TABLE sessions;--",
                "robert'; DROP TABLE sessions;--",
                "../../../etc/passwd",
                "%00",
            ]
        ),
    )
)
def test_property8_delete_user_removes_all_data(user_suffix: str) -> None:
    """Property 8: after delete_user, no data is retrievable for that user.

    Uses a TemporaryDirectory created inside the test so hypothesis does not
    detect a function-scoped fixture on a @given test.

    Includes hostile user_id patterns to verify parameterized queries prevent SQL injection.
    """
    user_id = f"user_{user_suffix}"
    session_id = str(uuid.uuid4())

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"{tmpdir}/test.db"

        # Seed data for target user and bystander
        assess_repo = SQLiteAssessmentRepository(db_path)
        profile_repo = SQLiteProfileRepository(db_path)
        consent_repo = SQLiteConsentRepository(db_path)

        # Target user data
        assess_repo.save_session(_make_session(session_id, user_id))
        assess_repo.save_result(_make_result(session_id, user_id))
        profile_repo.save_profile(_make_profile(user_id))
        consent_repo.save_consent(_make_consent(user_id))

        # Bystander user data (should remain untouched)
        bystander_user_id = "bystander_user_static"
        bystander_session_id = str(uuid.uuid4())
        assess_repo.save_session(_make_session(bystander_session_id, bystander_user_id))
        assess_repo.save_result(_make_result(bystander_session_id, bystander_user_id))
        profile_repo.save_profile(_make_profile(bystander_user_id))
        consent_repo.save_consent(_make_consent(bystander_user_id))

        # Count bystander data before deletion
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")

            # Count bystander data before
            bystander_sessions_before = conn.execute(
                "SELECT COUNT(*) as cnt FROM sessions WHERE user_id = ?", (bystander_user_id,)
            ).fetchone()["cnt"]
            bystander_trials_before = conn.execute(
                "SELECT COUNT(*) as cnt FROM trials WHERE user_id = ?", (bystander_user_id,)
            ).fetchone()["cnt"]
            bystander_metrics_before = conn.execute(
                "SELECT COUNT(*) as cnt FROM task_metrics WHERE session_id = ?",
                (bystander_session_id,),
            ).fetchone()["cnt"]
            bystander_dq_before = conn.execute(
                "SELECT COUNT(*) as cnt FROM data_quality WHERE session_id = ?",
                (bystander_session_id,),
            ).fetchone()["cnt"]
            bystander_profile_before = conn.execute(
                "SELECT COUNT(*) as cnt FROM profiles WHERE user_id = ?", (bystander_user_id,)
            ).fetchone()["cnt"]
            bystander_consent_before = conn.execute(
                "SELECT COUNT(*) as cnt FROM consent WHERE user_id = ?", (bystander_user_id,)
            ).fetchone()["cnt"]
        finally:
            conn.close()

        # Non-vacuous check: bystander data must actually exist before deletion
        assert bystander_sessions_before > 0, "bystander sessions should be seeded"
        assert bystander_trials_before > 0, "bystander trials should be seeded"
        assert bystander_metrics_before > 0, "bystander task_metrics should be seeded"
        assert bystander_dq_before > 0, "bystander data_quality should be seeded"
        assert bystander_profile_before > 0, "bystander profiles should be seeded"
        assert bystander_consent_before > 0, "bystander consent should be seeded"

        # Confirm data exists before deletion
        assert assess_repo.get_session(session_id) is not None
        assert profile_repo.get_profile(user_id) is not None
        assert consent_repo.get_consent(user_id) is not None

        # Delete target user from all repositories
        assess_repo.delete_user(user_id)
        profile_repo.delete_user(user_id)
        consent_repo.delete_consent(user_id)

        # Assert target user data removed
        assert assess_repo.get_session(session_id) is None, "session not deleted"
        assert assess_repo.get_results(session_id) == [], "results not deleted"
        assert profile_repo.get_profile(user_id) is None, "profile not deleted"
        assert consent_repo.get_consent(user_id) is None, "consent not deleted"

        # Verify row counts: 0 for target user, unchanged for bystander
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")

            # Count rows across all 6 tables for target user (should be 0)
            target_sessions_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM sessions WHERE user_id = ?", (user_id,)
            ).fetchone()["cnt"]
            target_trials_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM trials WHERE user_id = ?", (user_id,)
            ).fetchone()["cnt"]
            target_metrics_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM task_metrics WHERE session_id = ?", (session_id,)
            ).fetchone()["cnt"]
            target_dq_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM data_quality WHERE session_id = ?", (session_id,)
            ).fetchone()["cnt"]
            target_profile_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM profiles WHERE user_id = ?", (user_id,)
            ).fetchone()["cnt"]
            target_consent_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM consent WHERE user_id = ?", (user_id,)
            ).fetchone()["cnt"]

            # Count bystander data after (should be unchanged)
            bystander_sessions_after = conn.execute(
                "SELECT COUNT(*) as cnt FROM sessions WHERE user_id = ?", (bystander_user_id,)
            ).fetchone()["cnt"]
            bystander_trials_after = conn.execute(
                "SELECT COUNT(*) as cnt FROM trials WHERE user_id = ?", (bystander_user_id,)
            ).fetchone()["cnt"]
            bystander_metrics_after = conn.execute(
                "SELECT COUNT(*) as cnt FROM task_metrics WHERE session_id = ?",
                (bystander_session_id,),
            ).fetchone()["cnt"]
            bystander_dq_after = conn.execute(
                "SELECT COUNT(*) as cnt FROM data_quality WHERE session_id = ?",
                (bystander_session_id,),
            ).fetchone()["cnt"]
            bystander_profile_after = conn.execute(
                "SELECT COUNT(*) as cnt FROM profiles WHERE user_id = ?", (bystander_user_id,)
            ).fetchone()["cnt"]
            bystander_consent_after = conn.execute(
                "SELECT COUNT(*) as cnt FROM consent WHERE user_id = ?", (bystander_user_id,)
            ).fetchone()["cnt"]

            # Assert target user data completely removed
            assert (
                target_sessions_count == 0
            ), f"target sessions: {target_sessions_count} rows remain"
            assert target_trials_count == 0, f"target trials: {target_trials_count} rows remain"
            assert (
                target_metrics_count == 0
            ), f"target task_metrics: {target_metrics_count} rows remain"
            assert target_dq_count == 0, f"target data_quality: {target_dq_count} rows remain"
            assert target_profile_count == 0, f"target profiles: {target_profile_count} rows remain"
            assert target_consent_count == 0, f"target consent: {target_consent_count} rows remain"

            # Assert bystander data unchanged
            assert bystander_sessions_after == bystander_sessions_before, (
                f"bystander sessions changed: {bystander_sessions_before} -> "
                + f"{bystander_sessions_after}"
            )
            assert (
                bystander_trials_after == bystander_trials_before
            ), f"bystander trials changed: {bystander_trials_before} -> {bystander_trials_after}"
            assert bystander_metrics_after == bystander_metrics_before, (
                f"bystander metrics changed: {bystander_metrics_before} -> "
                + f"{bystander_metrics_after}"
            )
            assert (
                bystander_dq_after == bystander_dq_before
            ), f"bystander data_quality changed: {bystander_dq_before} -> {bystander_dq_after}"
            assert bystander_profile_after == bystander_profile_before, (
                f"bystander profiles changed: {bystander_profile_before} -> "
                + f"{bystander_profile_after}"
            )
            assert bystander_consent_after == bystander_consent_before, (
                f"bystander consent changed: {bystander_consent_before} -> "
                + f"{bystander_consent_after}"
            )
        finally:
            conn.close()
