"""Unit tests for FastAPI routers, dependencies, and error branches.

Ensures complete test coverage for all endpoints and error cases in coglayer.api.
"""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.core.settings import Settings


def _client(tmp_path: pathlib.Path) -> TestClient:
    settings = Settings(db_path=str(tmp_path / "test_api_unit.db"))
    app = create_app(settings)
    return TestClient(app)


def test_health_check(tmp_path: pathlib.Path) -> None:
    """GET /healthz returns ok status and provider."""
    client = _client(tmp_path)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_get_db_settings_dependency() -> None:
    """get_db_settings returns the singleton Settings instance."""
    from coglayer.api.deps import get_db_settings

    s = get_db_settings()
    assert isinstance(s, Settings)


def test_consent_endpoints(tmp_path: pathlib.Path) -> None:
    """Consent lifecycle over HTTP: get, post, delete."""
    client = _client(tmp_path)
    user_id = "test_user_consent"

    # Initially false
    r0 = client.get(f"/v1/assessment/consent/{user_id}")
    assert r0.status_code == 200
    assert r0.json()["has_consented"] is False

    # Record consent
    r1 = client.post("/v1/assessment/consent", json={"user_id": user_id})
    assert r1.status_code == 201

    # Revoke consent
    r2 = client.delete(f"/v1/assessment/consent/{user_id}")
    assert r2.status_code == 204

    # Now false again
    r3 = client.get(f"/v1/assessment/consent/{user_id}")
    assert r3.json()["has_consented"] is False


def test_sessions_errors(tmp_path: pathlib.Path) -> None:
    """Session endpoints error branches (404s)."""
    client = _client(tmp_path)

    # 404 on non-existent session
    assert client.get("/v1/assessment/sessions/non-existent").status_code == 404
    assert (
        client.patch(
            "/v1/assessment/sessions/non-existent/status",
            json={"status": "in_progress"},
        ).status_code
        == 404
    )
    assert client.get("/v1/assessment/sessions/non-existent/results").status_code == 404
    assert client.get("/v1/assessment/sessions/non-existent/decision").status_code == 404


def test_tasks_endpoints_and_errors(tmp_path: pathlib.Path) -> None:
    """Task registry queries and submit error cases."""
    client = _client(tmp_path)
    user_id = "task_err_user"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    s_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()["session_id"]

    # List tasks
    tasks = client.get("/v1/assessment/tasks").json()
    assert "go_no_go" in tasks
    assert "sequence_span" in tasks

    # Get single task
    gng_desc = client.get("/v1/assessment/tasks/go_no_go").json()
    assert gng_desc["task_id"] == "go_no_go"

    # Task not found
    assert client.get("/v1/assessment/tasks/unknown_task").status_code == 404

    # Submit with unknown task_id -> 400 Bad Request
    r_unknown = client.post(
        "/v1/assessment/tasks/unknown_task/submit",
        json={"session_id": s_id, "user_id": user_id, "raw_result": {}},
    )
    assert r_unknown.status_code == 400

    # Submit with invalid payload raising during score -> 422 Unprocessable Entity
    r_bad = client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={"session_id": s_id, "user_id": user_id, "raw_result": {"trials": "not_a_list"}},
    )
    assert r_bad.status_code == 422


def test_admin_delete_user(tmp_path: pathlib.Path) -> None:
    """DELETE /v1/assessment/users/{user_id} removes all user data."""
    client = _client(tmp_path)
    user_id = "admin_del_user"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    s_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()["session_id"]

    # Submit result
    gng = [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 200.0,
            "timestamp": "2024-01-15T10:00:00+00:00",
        },
    ]
    client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={"session_id": s_id, "user_id": user_id, "raw_result": {"trials": gng}},
    )

    # Call admin delete
    del_resp = client.delete(f"/v1/assessment/users/{user_id}")
    assert del_resp.status_code == 204

    # Consent is gone
    assert client.get(f"/v1/assessment/consent/{user_id}").json()["has_consented"] is False
    # Session is gone
    assert client.get(f"/v1/assessment/sessions/{s_id}").status_code == 404
    # Profile is blank
    prof = client.get(f"/v1/assessment/profile/{user_id}").json()
    assert prof["dimensions"] == {}


def test_sessions_get_and_submit_guards(tmp_path: pathlib.Path) -> None:
    """Covers GET existing session, and consent/session guards on submit."""
    client = _client(tmp_path)
    user_id = "guard_user"

    # Task submit before consent -> 403
    r_no_consent = client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={"session_id": "dummy", "user_id": user_id, "raw_result": {}},
    )
    assert r_no_consent.status_code == 403

    # Grant consent and create session
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    sess = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()
    s_id = sess["session_id"]

    # GET existing session -> 200
    get_sess = client.get(f"/v1/assessment/sessions/{s_id}")
    assert get_sess.status_code == 200
    assert get_sess.json()["session_id"] == s_id

    # Task submit with wrong session_id -> 403
    r_bad_sess = client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={"session_id": "non-existent-session", "user_id": user_id, "raw_result": {}},
    )
    assert r_bad_sess.status_code == 403


def test_coach_fallback_when_profile_none(tmp_path: pathlib.Path) -> None:
    """Covers coach router line when profile is None after complete sessions."""
    client = _client(tmp_path)
    user_id = "coach_fallback_user"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    s_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()["session_id"]

    # Submit GNG and Span to unlock coach
    gng = [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 200.0,
            "timestamp": "2024-01-15T10:00:00+00:00",
        }
    ]
    span = [
        {
            "stimulus": "0,1",
            "expected": "0,1",
            "response": "0,1",
            "rt_ms": 1000.0,
            "timestamp": "2024-01-15T10:00:10+00:00",
            "length": 2,
        }
    ]
    client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={
            "session_id": s_id,
            "user_id": user_id,
            "raw_result": {"trials": gng},
        },
    )
    client.post(
        "/v1/assessment/tasks/sequence_span/submit",
        json={
            "session_id": s_id,
            "user_id": user_id,
            "raw_result": {"sequences": span},
        },
    )

    # Now clear the profile directly in the database
    import sqlite3

    with sqlite3.connect(str(tmp_path / "test_api_unit.db")) as conn:
        conn.execute("DELETE FROM profiles WHERE user_id = ?", (user_id,))

    # Coach should regenerate with empty profile and return 200
    coach_resp = client.post(f"/v1/assessment/coach/{user_id}")
    assert coach_resp.status_code == 200
    assert "Based on these two tasks only" in coach_resp.text
