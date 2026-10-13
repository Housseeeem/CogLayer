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
from datetime import datetime
from pathlib import Path

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

__all__ = [
    "SQLiteAssessmentRepository",
    "SQLiteConsentRepository",
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


def _ensure_schema(db_path: str) -> None:
    """Create tables if they do not exist yet."""
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    with _connect(db_path) as conn:
        conn.executescript(schema)


# ---------------------------------------------------------------------------
# Helper: datetime <-> str
# ---------------------------------------------------------------------------


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


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
                    (session_id, user_id, start_time, end_time, status, completed_tasks)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    start_time = excluded.start_time,
                    end_time = excluded.end_time,
                    status = excluded.status,
                    completed_tasks = excluded.completed_tasks
                """,
                (
                    session.session_id,
                    session.user_id,
                    _dt_to_str(session.start_time),
                    _dt_to_str(session.end_time) if session.end_time else None,
                    session.status.value,
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
        return Session(
            session_id=row["session_id"],
            user_id=row["user_id"],
            start_time=_str_to_dt(row["start_time"]),
            end_time=_str_to_dt(row["end_time"]) if row["end_time"] else None,
            status=SessionStatus(row["status"]),
            completed_tasks=json.loads(row["completed_tasks"]),
        )

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

    def delete_user(self, user_id: str) -> None:
        """Remove all sessions (and cascaded trials/metrics/quality) for the user."""
        with _connect(self._db_path) as conn:
            # Sessions have FK cascade to trials/task_metrics/data_quality
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


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
                INSERT OR REPLACE INTO consent (user_id, consented_at, revoked_at)
                VALUES (?, ?, ?)
                """,
                (
                    record.user_id,
                    _dt_to_str(record.consented_at),
                    _dt_to_str(record.revoked_at) if record.revoked_at else None,
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
        )

    def delete_consent(self, user_id: str) -> None:
        """Remove the consent record for the given user."""
        with _connect(self._db_path) as conn:
            conn.execute("DELETE FROM consent WHERE user_id = ?", (user_id,))
