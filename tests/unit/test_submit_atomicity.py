"""Tests for submit endpoint atomicity and compensation (Fix 2).

Requirements:
1. Pure profile computation happens BEFORE save_result.
2. Compensation (delete_result) applies ONLY if save_result succeeded in this request.
   On DuplicateSubmissionError (409), delete_result is NEVER called.
3. delete_result(session_id, task_id) cleans up trials, task_metrics, and data_quality.
4. If save_profile raises, delete_result is called to rollback the stored result,
   and the original error is re-raised. If delete_result itself fails, the original
   error still surfaces (not masked).

Arithmetic for expected values:
- Minimal Go/No-Go result has 2 trials, 1 data_quality row, and 5 metric rows.
  Before delete_result: trials count = 2, metrics count = 5, data_quality count = 1.
  After delete_result(session_id, "go_no_go"): counts all equal 0.
- Duplicate submission: first submit returns HTTP 200, storing 1 result.
  Second submit returns HTTP 409 Conflict; the original result is retained (count = 1).
- Retry after failure: when save_profile fails, result is compensated (count = 0).
  A subsequent retry succeeds with HTTP 200 instead of failing with 409 Conflict.
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.api.db.sqlite import SQLiteAssessmentRepository
from coglayer.api.deps import get_assessment_repo, get_profile_repo
from coglayer.core.settings import Settings


def _client(tmp_path: pathlib.Path) -> tuple[TestClient, FastAPI, Settings]:
    settings = Settings(db_path=str(tmp_path / "test_atomicity.db"))
    app = create_app(settings)
    return TestClient(app), app, settings


def _setup_user(client: TestClient, user_id: str) -> str:
    """Grant consent, create session, return session_id."""
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    resp = client.post("/v1/assessment/sessions", json={"user_id": user_id})
    session_id: str = resp.json()["session_id"]
    return session_id


def _make_gng_trials() -> list[dict[str, Any]]:
    """Return a minimal valid Go/No-Go trial list (1 go, 1 nogo)."""
    return [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 300.0,
            "timestamp": "2024-06-01T12:00:00+00:00",
        },
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": None,
            "rt_ms": 500.0,
            "timestamp": "2024-06-01T12:00:01+00:00",
        },
    ]


# ---------------------------------------------------------------------------
# 1. Storage unit test for delete_result
# ---------------------------------------------------------------------------


class TestAssessmentRepositoryDeleteResult:
    """delete_result must remove trials, task_metrics, and data_quality for
    (session_id, task_id).
    """

    def test_delete_result_cleans_all_tables(self, tmp_path: pathlib.Path) -> None:
        client, _app, settings = _client(tmp_path)
        user_id = "user_delete_test"
        session_id = _setup_user(client, user_id)

        # Submit a result via API to populate DB tables
        resp = client.post(
            "/v1/assessment/tasks/go_no_go/submit",
            json={
                "session_id": session_id,
                "user_id": user_id,
                "raw_result": {"trials": _make_gng_trials()},
            },
        )
        assert resp.status_code == 200, resp.text

        # Verify rows exist in SQLite
        conn = sqlite3.connect(settings.db_path)
        try:
            # Arithmetic: 2 trials, >0 metrics, 1 data_quality row
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM trials WHERE session_id = ? AND task_id = ?",
                (session_id, "go_no_go"),
            )
            assert cur.fetchone()[0] == 2
            cur.execute(
                "SELECT COUNT(*) FROM task_metrics WHERE session_id = ? AND task_id = ?",
                (session_id, "go_no_go"),
            )
            assert cur.fetchone()[0] > 0
            cur.execute(
                "SELECT COUNT(*) FROM data_quality WHERE session_id = ? AND task_id = ?",
                (session_id, "go_no_go"),
            )
            assert cur.fetchone()[0] == 1
        finally:
            conn.close()

        # Call delete_result
        repo = SQLiteAssessmentRepository(settings.db_path)
        repo.delete_result(session_id, "go_no_go")

        # Verify all dependent rows are removed
        conn = sqlite3.connect(settings.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM trials WHERE session_id = ? AND task_id = ?",
                (session_id, "go_no_go"),
            )
            assert cur.fetchone()[0] == 0
            cur.execute(
                "SELECT COUNT(*) FROM task_metrics WHERE session_id = ? AND task_id = ?",
                (session_id, "go_no_go"),
            )
            assert cur.fetchone()[0] == 0
            cur.execute(
                "SELECT COUNT(*) FROM data_quality WHERE session_id = ? AND task_id = ?",
                (session_id, "go_no_go"),
            )
            assert cur.fetchone()[0] == 0
        finally:
            conn.close()

        # get_results returns empty
        assert repo.get_results(session_id) == []


# ---------------------------------------------------------------------------
# 2. Duplicate submission test (never call delete_result on 409)
# ---------------------------------------------------------------------------


class TestDuplicateSubmissionPreservesResult:
    """On DuplicateSubmissionError (409), delete_result must not be called."""

    def test_duplicate_submission_keeps_original_result(self, tmp_path: pathlib.Path) -> None:
        client, _app, settings = _client(tmp_path)
        user_id = "user_dup_test"
        session_id = _setup_user(client, user_id)

        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {"trials": _make_gng_trials()},
        }

        # 1. First submission succeeds (200)
        resp1 = client.post("/v1/assessment/tasks/go_no_go/submit", json=payload)
        assert resp1.status_code == 200

        # 2. Second submission with same session_id and task_id fails with 409
        resp2 = client.post("/v1/assessment/tasks/go_no_go/submit", json=payload)
        assert resp2.status_code == 409
        assert "Duplicate submission" in resp2.json()["detail"]

        # 3. Original result is still stored (not deleted)
        repo = SQLiteAssessmentRepository(settings.db_path)
        results = repo.get_results(session_id)
        assert len(results) == 1
        assert results[0].task_id == "go_no_go"


# ---------------------------------------------------------------------------
# 3. Compensation on save_profile error enables retry
# ---------------------------------------------------------------------------


class TestProfileFailureCompensation:
    """If save_profile fails, result is rolled back and retry succeeds."""

    def test_retry_succeeds_after_save_profile_failure(self, tmp_path: pathlib.Path) -> None:
        client, app, settings = _client(tmp_path)
        user_id = "user_retry_test"
        session_id = _setup_user(client, user_id)

        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {"trials": _make_gng_trials()},
        }

        real_profile_repo = get_profile_repo(settings)
        failing_profile_repo = MagicMock(wraps=real_profile_repo)
        failing_profile_repo.save_profile.side_effect = RuntimeError("Simulated profile DB error")

        app.dependency_overrides[get_profile_repo] = lambda: failing_profile_repo

        # First attempt fails due to simulated profile error
        with pytest.raises(RuntimeError, match="Simulated profile DB error"):
            client.post("/v1/assessment/tasks/go_no_go/submit", json=payload)

        # Result should have been compensated (deleted)
        repo = SQLiteAssessmentRepository(settings.db_path)
        assert repo.get_results(session_id) == []

        # Remove override to simulate recovered DB
        app.dependency_overrides.pop(get_profile_repo)

        # Retry should now succeed (HTTP 200, NOT HTTP 409 Conflict!)
        resp = client.post("/v1/assessment/tasks/go_no_go/submit", json=payload)
        assert resp.status_code == 200
        assert len(repo.get_results(session_id)) == 1


# ---------------------------------------------------------------------------
# 4. Compensation failure does not mask original error
# ---------------------------------------------------------------------------


class TestCompensationFailureSurfacesOriginalError:
    """If delete_result fails during compensation, the original error still surfaces."""

    def test_compensation_failure_logs_and_reraises_original(self, tmp_path: pathlib.Path) -> None:
        client, app, settings = _client(tmp_path)
        user_id = "user_mask_test"
        session_id = _setup_user(client, user_id)

        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {"trials": _make_gng_trials()},
        }

        real_profile_repo = get_profile_repo(settings)
        failing_profile_repo = MagicMock(wraps=real_profile_repo)
        failing_profile_repo.save_profile.side_effect = RuntimeError("Original profile error")

        real_assessment_repo = get_assessment_repo(settings)
        failing_assessment_repo = MagicMock(wraps=real_assessment_repo)
        # delete_result raises
        failing_assessment_repo.delete_result.side_effect = RuntimeError(
            "Delete compensation error"
        )

        app.dependency_overrides[get_profile_repo] = lambda: failing_profile_repo
        app.dependency_overrides[get_assessment_repo] = lambda: failing_assessment_repo

        try:
            # The ORIGINAL error ("Original profile error") must be raised,
            # NOT "Delete compensation error"
            with pytest.raises(RuntimeError, match="Original profile error"):
                client.post("/v1/assessment/tasks/go_no_go/submit", json=payload)
        finally:
            app.dependency_overrides.clear()
