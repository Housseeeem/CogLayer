"""SQLite-backed repository implementations for CogLayer.

Provides concrete implementations of AssessmentRepository, ProfileRepository,
and ConsentRepository using the stdlib sqlite3 module.

Design constraints:
- All queries use parameterized placeholders (never f-string SQL) (R-001.2)
- PRAGMA foreign_keys = ON is set per connection
- No global mutable state; each repository instance owns its db_path
- delete_user removes ALL data for the user across every table (R-001.2)
- DuplicateSubmissionError is raised on duplicate (session_id, task_id) (R-005.4)

Requirements: R-005.1, R-005.2, R-005.3, R-005.4, R-005.5, R-005.6, R-001.2
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

from coglayer.core.exceptions import (
    DuplicateIOIEventError,
    DuplicateSubmissionError,
    IOIOpportunityConflictError,
    IOISessionOwnershipError,
)
from coglayer.core.models import (
    AdaptiveDailyPlan,
    CoachConversation,
    CoachMessage,
    CognitiveProfile,
    ConsentRecord,
    DataQuality,
    ExperienceProfile,
    IOIObservation,
    Session,
    SessionStatus,
    SessionType,
    Signal,
    TaskResult,
    Trial,
)

__all__ = [
    "SQLiteAssessmentRepository",
    "SQLiteConsentRepository",
    "SQLiteConversationRepository",
    "SQLiteDailyPlanRepository",
    "SQLiteExperienceProfileRepository",
    "SQLiteIOIEventRepository",
    "SQLiteProfileRepository",
]

# ---------------------------------------------------------------------------
# Schema path
# ---------------------------------------------------------------------------

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _connect(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """Yield a sqlite3 connection with FK enforcement and row_factory set."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply lightweight idempotent schema migrations for existing databases."""
    consent_cols = {row["name"] for row in conn.execute("PRAGMA table_info(consent)").fetchall()}
    if consent_cols:
        if "guardian_consent" not in consent_cols:
            conn.execute(
                "ALTER TABLE consent ADD COLUMN guardian_consent INTEGER NOT NULL DEFAULT 0"
            )
        if "guardian_id" not in consent_cols:
            conn.execute("ALTER TABLE consent ADD COLUMN guardian_id TEXT")

    sessions_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if sessions_cols:
        if "session_type" not in sessions_cols:
            conn.execute(
                "ALTER TABLE sessions ADD COLUMN session_type TEXT NOT NULL DEFAULT 'assessment'"
            )


def _ensure_schema(db_path: str) -> None:
    """Create tables if they do not exist yet and apply migrations."""
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    with _connect(db_path) as conn:
        conn.executescript(schema)
        _migrate_schema(conn)


# ---------------------------------------------------------------------------
# Helper: datetime <-> str
# ---------------------------------------------------------------------------


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _event_from_row(row: sqlite3.Row) -> IOIObservation:
    """Build an IOI observation from a SQLite row."""
    return IOIObservation(
        event_id=row["event_id"],
        user_id=row["user_id"],
        session_id=row["session_id"],
        component=row["component"],
        event_type=row["event_type"],
        opportunity_id=row["opportunity_id"],
        behavior_observed=bool(row["behavior_observed"]),
        valid=bool(row["valid"]),
        timestamp=_str_to_dt(row["timestamp_iso"]),
        schema_version=row["schema_version"],
        metadata=json.loads(row["metadata"]),
    )


# ---------------------------------------------------------------------------
# SQLiteAssessmentRepository
# ---------------------------------------------------------------------------


class SQLiteAssessmentRepository:
    """AssessmentRepository backed by SQLite.

    Parameters
    ----------
    db_path:
        Path to the SQLite file, or ``":memory:"`` for in-memory use in tests.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        _ensure_schema(db_path)

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def save_session(self, session: Session) -> None:
        """Persist a session record (upsert without cascaded row deletion)."""
        with _connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions
                    (session_id, user_id, start_time, end_time, status,
                     session_type, completed_tasks)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    status = excluded.status,
                    session_type = excluded.session_type,
                    completed_tasks = excluded.completed_tasks
                """,
                (
                    session.session_id,
                    session.user_id,
                    _dt_to_str(session.start_time),
                    _dt_to_str(session.end_time) if session.end_time else None,
                    session.status.value,
                    session.session_type.value,
                    json.dumps(session.completed_tasks),
                ),
            )

    def get_session(self, session_id: str) -> Session | None:
        """Return the session or None if not found."""
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            return None
        session_type = (
            SessionType(row["session_type"])
            if "session_type" in row.keys()
            else SessionType.ASSESSMENT
        )
        return Session(
            session_id=row["session_id"],
            user_id=row["user_id"],
            start_time=_str_to_dt(row["start_time"]),
            end_time=_str_to_dt(row["end_time"]) if row["end_time"] else None,
            status=SessionStatus(row["status"]),
            session_type=session_type,
            completed_tasks=json.loads(row["completed_tasks"]),
        )

    def get_sessions_by_user(self, user_id: str) -> list[Session]:
        """Return all sessions for a given user ordered by start_time."""
        with _connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE user_id = ? ORDER BY start_time",
                (user_id,),
            ).fetchall()
        return [
            Session(
                session_id=row["session_id"],
                user_id=row["user_id"],
                start_time=_str_to_dt(row["start_time"]),
                end_time=_str_to_dt(row["end_time"]) if row["end_time"] else None,
                status=SessionStatus(row["status"]),
                session_type=SessionType(row["session_type"])
                if "session_type" in row.keys()
                else SessionType.ASSESSMENT,
                completed_tasks=json.loads(row["completed_tasks"]),
            )
            for row in rows
        ]

    def update_session_status(self, session_id: str, status: SessionStatus) -> None:
        """Update the status field of an existing session."""
        with _connect(self._db_path) as conn:
            conn.execute(
                "UPDATE sessions SET status = ? WHERE session_id = ?",
                (status.value, session_id),
            )

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def save_result(self, result: TaskResult) -> None:
        """Persist a scored TaskResult including all raw trials.

        Uses a single BEGIN IMMEDIATE transaction.  The data_quality row is
        inserted first so its PRIMARY KEY constraint fires before any trial or
        metric row is written; the whole transaction rolls back on any error.

        Raises DuplicateSubmissionError if (session_id, task_id) already exists
        (R-005.4).  Any other sqlite3.IntegrityError (e.g. FK violation for an
        unknown session_id) is re-raised as-is.
        """
        try:
            with _connect(self._db_path) as conn:
                conn.execute("BEGIN IMMEDIATE")

                # 1. data_quality first — its PK fires on duplicate before
                #    any trial or metric row is written.
                conn.execute(
                    """
                    INSERT INTO data_quality
                        (session_id, task_id, task_version, user_id,
                         valid_trials, total_trials, completeness,
                         anomalies, target_dimensions, signals, uncertainty)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.session_id,
                        result.task_id,
                        result.task_version,
                        result.user_id,
                        result.data_quality.valid_trials,
                        result.data_quality.total_trials,
                        result.data_quality.completeness,
                        json.dumps(result.data_quality.anomalies),
                        json.dumps(result.target_dimensions),
                        json.dumps([s.model_dump() for s in result.signals]),
                        result.uncertainty,
                    ),
                )

                # 2. Trials
                for trial in result.trials:
                    conn.execute(
                        """
                        INSERT INTO trials
                            (session_id, task_id, task_version, user_id,
                             stimulus, expected, response, rt_ms,
                             timestamp_iso, valid, invalid_reason)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            result.session_id,
                            result.task_id,
                            result.task_version,
                            result.user_id,
                            trial.stimulus,
                            trial.expected,
                            trial.response,
                            trial.rt_ms,
                            _dt_to_str(trial.timestamp),
                            1 if trial.valid else 0,
                            trial.invalid_reason,
                        ),
                    )

                # 3. Metrics
                for name, value in result.metrics.items():
                    conn.execute(
                        """
                        INSERT INTO task_metrics
                            (session_id, task_id, metric_name, metric_value)
                        VALUES (?, ?, ?, ?)
                        """,
                        (result.session_id, result.task_id, name, value),
                    )
        except sqlite3.IntegrityError as e:
            if e.sqlite_errorname in (
                "SQLITE_CONSTRAINT_PRIMARYKEY",
                "SQLITE_CONSTRAINT_UNIQUE",
            ):
                raise DuplicateSubmissionError(result.session_id, result.task_id) from e
            raise

    def get_results(self, session_id: str) -> list[TaskResult]:
        """Return all TaskResult objects for a given session."""
        with _connect(self._db_path) as conn:
            # Get all task results from data_quality table
            dq_rows = conn.execute(
                """
                SELECT session_id, task_id, task_version, user_id, valid_trials, total_trials,
                       completeness, anomalies, target_dimensions, signals, uncertainty
                FROM data_quality
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchall()

            results: list[TaskResult] = []
            for dq_row in dq_rows:
                task_id: str = dq_row["task_id"]
                task_version: str = dq_row["task_version"]
                user_id: str = dq_row["user_id"]

                # Load trials
                trial_rows = conn.execute(
                    """
                    SELECT * FROM trials
                    WHERE session_id = ? AND task_id = ?
                    ORDER BY id
                    """,
                    (session_id, task_id),
                ).fetchall()
                trials = [
                    Trial(
                        stimulus=r["stimulus"],
                        expected=r["expected"],
                        response=r["response"],
                        rt_ms=r["rt_ms"],
                        timestamp=_str_to_dt(r["timestamp_iso"]),
                        valid=bool(r["valid"]),
                        invalid_reason=r["invalid_reason"],
                    )
                    for r in trial_rows
                ]

                # Load metrics
                metric_rows = conn.execute(
                    "SELECT metric_name, metric_value FROM task_metrics"
                    " WHERE session_id = ? AND task_id = ?",
                    (session_id, task_id),
                ).fetchall()
                metrics = {r["metric_name"]: r["metric_value"] for r in metric_rows}

                # Build data quality from stored values
                dq = DataQuality(
                    valid_trials=dq_row["valid_trials"],
                    total_trials=dq_row["total_trials"],
                    completeness=dq_row["completeness"],
                    anomalies=json.loads(dq_row["anomalies"]),
                )

                # Parse target_dimensions and signals from JSON
                target_dimensions = json.loads(dq_row["target_dimensions"])
                signals_data = json.loads(dq_row["signals"])
                signals = [Signal.model_validate(s) for s in signals_data]

                results.append(
                    TaskResult(
                        task_id=task_id,
                        task_version=task_version,
                        session_id=session_id,
                        user_id=user_id,
                        trials=trials,
                        metrics=metrics,
                        signals=signals,
                        target_dimensions=target_dimensions,
                        data_quality=dq,
                        uncertainty=dq_row["uncertainty"],
                    )
                )
        return results

    def delete_result(self, session_id: str, task_id: str) -> None:
        """Remove a task result and all associated trials, metrics, and quality records."""
        with _connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM trials WHERE session_id = ? AND task_id = ?",
                (session_id, task_id),
            )
            conn.execute(
                "DELETE FROM task_metrics WHERE session_id = ? AND task_id = ?",
                (session_id, task_id),
            )
            conn.execute(
                "DELETE FROM data_quality WHERE session_id = ? AND task_id = ?",
                (session_id, task_id),
            )

    def delete_user(self, user_id: str) -> None:
        """Remove all sessions (and cascaded trials/metrics/quality) for the user."""
        with _connect(self._db_path) as conn:
            # Sessions have FK cascade to trials/task_metrics/data_quality
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM daily_plans WHERE user_id = ?", (user_id,))


# ---------------------------------------------------------------------------
# SQLiteProfileRepository
# ---------------------------------------------------------------------------


class SQLiteProfileRepository:
    """ProfileRepository backed by SQLite."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        _ensure_schema(db_path)

    def save_profile(self, profile: CognitiveProfile) -> None:
        """Persist (create or replace) a CognitiveProfile as JSON."""
        with _connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO profiles (user_id, profile_json) VALUES (?, ?)",
                (profile.user_id, profile.model_dump_json()),
            )

    def get_profile(self, user_id: str) -> CognitiveProfile | None:
        """Return the profile or None if not found."""
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT profile_json FROM profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return None
        return CognitiveProfile.model_validate_json(row["profile_json"])

    def delete_user(self, user_id: str) -> None:
        """Remove the profile record for the given user."""
        with _connect(self._db_path) as conn:
            conn.execute("DELETE FROM profiles WHERE user_id = ?", (user_id,))


# ---------------------------------------------------------------------------
# SQLiteConsentRepository
# ---------------------------------------------------------------------------


class SQLiteConsentRepository:
    """ConsentRepository backed by SQLite."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        _ensure_schema(db_path)

    def save_consent(self, record: ConsentRecord) -> None:
        """Persist a consent record (create or replace)."""
        with _connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO consent
                    (user_id, consented_at, revoked_at, guardian_consent, guardian_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    record.user_id,
                    _dt_to_str(record.consented_at),
                    _dt_to_str(record.revoked_at) if record.revoked_at else None,
                    1 if record.guardian_consent else 0,
                    record.guardian_id,
                ),
            )

    def get_consent(self, user_id: str) -> ConsentRecord | None:
        """Return the consent record or None if absent."""
        with _connect(self._db_path) as conn:
            row = conn.execute("SELECT * FROM consent WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return ConsentRecord(
            user_id=row["user_id"],
            consented_at=_str_to_dt(row["consented_at"]),
            revoked_at=_str_to_dt(row["revoked_at"]) if row["revoked_at"] else None,
            guardian_consent=bool(row["guardian_consent"]),
            guardian_id=row["guardian_id"],
        )

    def delete_consent(self, user_id: str) -> None:
        """Remove the consent record for the given user."""
        with _connect(self._db_path) as conn:
            conn.execute("DELETE FROM consent WHERE user_id = ?", (user_id,))


class SQLiteIOIEventRepository:
    """SQLite repository for structured IOI observations."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        _ensure_schema(db_path)

    def save_event(self, event: IOIObservation) -> bool:
        """Insert an event after checking session ownership and conflicts."""
        with _connect(self._db_path) as conn:
            session = conn.execute(
                "SELECT user_id FROM sessions WHERE session_id = ?",
                (event.session_id,),
            ).fetchone()
            if session is None or session["user_id"] != event.user_id:
                raise IOISessionOwnershipError(event.user_id, event.session_id)

            existing = conn.execute(
                "SELECT * FROM collaboration_events WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
            if existing is not None:
                if _event_from_row(existing) == event:
                    return False
                raise DuplicateIOIEventError(event.event_id)

            opportunity = conn.execute(
                """
                SELECT * FROM collaboration_events
                WHERE user_id = ? AND component = ? AND opportunity_id = ?
                """,
                (event.user_id, event.component.value, event.opportunity_id),
            ).fetchone()
            if opportunity is not None:
                raise IOIOpportunityConflictError(
                    event.user_id,
                    event.component.value,
                    event.opportunity_id,
                )

            conn.execute(
                """
                INSERT INTO collaboration_events
                    (event_id, user_id, session_id, component, event_type,
                     opportunity_id, behavior_observed, valid, timestamp_iso,
                     schema_version, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.user_id,
                    event.session_id,
                    event.component.value,
                    event.event_type.value,
                    event.opportunity_id,
                    int(event.behavior_observed),
                    int(event.valid),
                    _dt_to_str(event.timestamp),
                    event.schema_version,
                    json.dumps(event.metadata, separators=(",", ":")),
                ),
            )
        return True

    def get_events(self, user_id: str, session_id: str | None = None) -> list[IOIObservation]:
        """Return stored IOI events for a user in timestamp order."""
        with _connect(self._db_path) as conn:
            if session_id is None:
                rows = conn.execute(
                    """
                    SELECT * FROM collaboration_events
                    WHERE user_id = ? ORDER BY timestamp_iso, event_id
                    """,
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM collaboration_events
                    WHERE user_id = ? AND session_id = ?
                    ORDER BY timestamp_iso, event_id
                    """,
                    (user_id, session_id),
                ).fetchall()
        return [_event_from_row(row) for row in rows]

    def delete_user(self, user_id: str) -> None:
        """Delete all IOI observations for a user."""
        with _connect(self._db_path) as conn:
            conn.execute("DELETE FROM collaboration_events WHERE user_id = ?", (user_id,))


# ---------------------------------------------------------------------------
# SQLiteDailyPlanRepository
# ---------------------------------------------------------------------------


class SQLiteDailyPlanRepository:
    """DailyPlanRepository backed by SQLite."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        _ensure_schema(db_path)

    def save_plan(self, plan: AdaptiveDailyPlan) -> None:
        """Persist or update an adaptive daily plan."""
        with _connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO daily_plans
                    (user_id, plan_date, session_id, plan_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, plan_date) DO UPDATE SET
                    session_id = excluded.session_id,
                    plan_json = excluded.plan_json,
                    status = excluded.status
                """,
                (
                    plan.user_id,
                    plan.plan_date,
                    plan.session_id,
                    plan.model_dump_json(),
                    plan.status,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_plan(self, user_id: str, plan_date: str) -> AdaptiveDailyPlan | None:
        """Retrieve the daily plan for a user on a given date, or None."""
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT plan_json FROM daily_plans WHERE user_id = ? AND plan_date = ?",
                (user_id, plan_date),
            ).fetchone()
        if row is None:
            return None
        return AdaptiveDailyPlan.model_validate_json(row["plan_json"])

    def get_plan_by_session(self, user_id: str, session_id: str) -> AdaptiveDailyPlan | None:
        """Retrieve the daily plan linked to a session for a user, or None."""
        with _connect(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT plan_json FROM daily_plans
                WHERE user_id = ? AND session_id = ?
                ORDER BY plan_date DESC
                LIMIT 1
                """,
                (user_id, session_id),
            ).fetchone()
        if row is None:
            return None
        return AdaptiveDailyPlan.model_validate_json(row["plan_json"])

    def update_plan_status(
        self,
        user_id: str,
        plan_date: str,
        status: str,
        session_id: str | None = None,
    ) -> None:
        """Update lifecycle status and optional session ID of a daily plan."""
        plan = self.get_plan(user_id, plan_date)
        if plan is None:
            return
        target_session = session_id if session_id is not None else plan.session_id
        if plan.status == status and plan.session_id == target_session:
            return
        updated_plan = plan.model_copy(
            update={
                "status": status,
                "session_id": target_session,
            }
        )
        self.save_plan(updated_plan)

    def delete_user(self, user_id: str) -> None:
        """Remove all daily plans for the given user."""
        with _connect(self._db_path) as conn:
            conn.execute("DELETE FROM daily_plans WHERE user_id = ?", (user_id,))


# ---------------------------------------------------------------------------
# SQLiteConversationRepository
# ---------------------------------------------------------------------------


class SQLiteConversationRepository:
    """ConversationRepository backed by SQLite.

    Parameters
    ----------
    db_path:
        Path to the SQLite file, or ``":memory:"`` for in-memory use in tests.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        _ensure_schema(db_path)

    def save_conversation(self, conversation: CoachConversation) -> None:
        """Persist a new conversation."""
        with _connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO coach_conversations
                    (conversation_id, user_id, session_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    conversation.conversation_id,
                    conversation.user_id,
                    conversation.session_id,
                    _dt_to_str(conversation.created_at),
                ),
            )

    def get_conversation(self, conversation_id: str) -> CoachConversation | None:
        """Retrieve a conversation by ID, or None if not found."""
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM coach_conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        messages = self.get_messages(conversation_id)
        return CoachConversation(
            conversation_id=row["conversation_id"],
            user_id=row["user_id"],
            session_id=row["session_id"],
            created_at=_str_to_dt(row["created_at"]),
            messages=messages,
        )

    def get_conversations_by_user(self, user_id: str) -> list[CoachConversation]:
        """Retrieve all conversations for a user, most recent first."""
        with _connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM coach_conversations WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [
            CoachConversation(
                conversation_id=row["conversation_id"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                created_at=_str_to_dt(row["created_at"]),
                messages=self.get_messages(row["conversation_id"]),
            )
            for row in rows
        ]

    def save_message(self, message: CoachMessage) -> None:
        """Persist a new message."""
        with _connect(self._db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO coach_messages
                    (conversation_id, role, content, timestamp_iso)
                VALUES (?, ?, ?, ?)
                """,
                (
                    message.conversation_id,
                    message.role.value,
                    message.content,
                    _dt_to_str(message.timestamp),
                ),
            )
            # Set the message_id from the inserted row
            message.message_id = cursor.lastrowid

    def get_messages(self, conversation_id: str) -> list[CoachMessage]:
        """Retrieve all messages for a conversation in chronological order."""
        with _connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM coach_messages WHERE conversation_id = ? ORDER BY timestamp_iso ASC",
                (conversation_id,),
            ).fetchall()
        return [
            CoachMessage(
                message_id=row["message_id"],
                conversation_id=row["conversation_id"],
                role=row["role"],
                content=row["content"],
                timestamp=_str_to_dt(row["timestamp_iso"]),
            )
            for row in rows
        ]

    def delete_user(self, user_id: str) -> None:
        """Remove all conversations and messages for a user."""
        with _connect(self._db_path) as conn:
            # Conversations have FK cascade to messages
            conn.execute("DELETE FROM coach_conversations WHERE user_id = ?", (user_id,))


# ---------------------------------------------------------------------------
# SQLiteExperienceProfileRepository
# ---------------------------------------------------------------------------


class SQLiteExperienceProfileRepository:
    """ExperienceProfileRepository backed by SQLite."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        _ensure_schema(db_path)

    def save_profile(self, profile: ExperienceProfile) -> None:
        """Persist (create or replace) an ExperienceProfile."""
        with _connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experience_profiles
                    (user_id, age_group, goals, tech_comfort, info_style,
                     layout, theme, guidance_level, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.user_id,
                    profile.age_group.value,
                    json.dumps(profile.goals),
                    profile.tech_comfort.value,
                    profile.info_style.value,
                    profile.layout.value,
                    profile.theme.value,
                    profile.guidance_level.value if profile.guidance_level else None,
                    _dt_to_str(profile.created_at),
                    _dt_to_str(profile.updated_at),
                ),
            )

    def get_profile(self, user_id: str) -> ExperienceProfile | None:
        """Return the experience profile for a user, or None if not found."""
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM experience_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row is None:
            return None
        return ExperienceProfile(
            user_id=row["user_id"],
            age_group=row["age_group"],
            goals=json.loads(row["goals"]),
            tech_comfort=row["tech_comfort"],
            info_style=row["info_style"],
            layout=row["layout"],
            theme=row["theme"],
            guidance_level=row["guidance_level"],
            created_at=_str_to_dt(row["created_at"]),
            updated_at=_str_to_dt(row["updated_at"]),
        )

    def delete_user(self, user_id: str) -> None:
        """Remove the experience profile for the given user."""
        with _connect(self._db_path) as conn:
            conn.execute("DELETE FROM experience_profiles WHERE user_id = ?", (user_id,))
