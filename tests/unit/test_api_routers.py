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
    # Profile access without consent is forbidden
    assert client.get(f"/v1/assessment/profile/{user_id}").status_code == 403
    # Re-consenting confirms the underlying profile data was wiped blank
    client.post("/v1/assessment/consent", json={"user_id": user_id})
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


def test_submit_unregistered_task_version_stores_result_without_profile_update(
    tmp_path: pathlib.Path,
) -> None:
    """If result.task_version is not registered, result is stored and profile untouched."""
    from coglayer.api.deps import get_scoring_adapters
    from coglayer.core.models import DataQuality, TaskResult

    class FakeVersionScorer:
        def score(self, raw: dict[str, object]) -> TaskResult:
            return TaskResult(
                task_id="go_no_go",
                task_version="9.9",
                session_id=str(raw["session_id"]),
                user_id=str(raw["user_id"]),
                trials=[],
                metrics={"nogo_accuracy": 0.85, "nogo_valid_count": 10.0},
                signals=[],
                target_dimensions=["response_inhibition"],
                data_quality=DataQuality(
                    valid_trials=10, total_trials=10, completeness=1.0, anomalies=[]
                ),
                uncertainty=None,
            )

    settings = Settings(db_path=str(tmp_path / "test_api_ver.db"))
    app = create_app(settings)
    app.dependency_overrides[get_scoring_adapters] = lambda: {"go_no_go": FakeVersionScorer()}
    client = TestClient(app)

    user_id = "u_ver"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    sess = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()
    s_id = sess["session_id"]

    resp = client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={"session_id": s_id, "user_id": user_id, "raw_result": {}},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert "unknown_task_version" in res_data["data_quality"]["anomalies"]

    # Profile was not updated
    prof = client.get(f"/v1/assessment/profile/{user_id}").json()
    assert prof["dimensions"] == {}

    # Result was still stored in session results
    results_resp = client.get(f"/v1/assessment/sessions/{s_id}/results")
    assert results_resp.status_code == 200
    assert len(results_resp.json()) == 1
    assert results_resp.json()[0]["task_version"] == "9.9"


def test_sessions_decision_with_stored_profile(tmp_path: pathlib.Path) -> None:
    """GET /sessions/{session_id}/decision with a stored profile in the database.

    Hand-derived:
      Scenario:
      Two built-in tasks in registry:
        - go_no_go: measures response_inhibition (label: 'Response Inhibition')
        - sequence_span: measures sequential_visual_memory (label: 'Sequential Visual Memory')
      Uniform prior Beta(1,1): width = 0.95 - 0.05 = 0.900000.
      Posterior Beta(9,3): lower = 0.529913, upper = 0.921180, width = 0.391267.

      Case 1: User 1 has stored profile with Beta(9,3) for response_inhibition (width 0.391267)
      and no evidence for sequential_visual_memory (width 0.900000).
      Session has no results.
      Least certain dimension is sequential_visual_memory.
      Expected task: 'sequence_span'.
      Expected reason: 'Sequential Visual Memory is where our estimate is least
      certain, so we test it next.'

      Case 2 (Swapped): User 2 has stored profile with Beta(9,3) for
      sequential_visual_memory (width 0.391267)
      and no evidence for response_inhibition (width 0.900000).
      Session has no results.
      Least certain dimension is response_inhibition.
      Expected task: 'go_no_go'.
      Expected reason: 'Response Inhibition is where our estimate is least
      certain, so we test it next.'
    """
    from datetime import UTC, datetime

    from coglayer.api.db.sqlite import SQLiteProfileRepository
    from coglayer.core.models import CognitiveProfile, DimensionEstimate

    client = _client(tmp_path)
    db_path = str(tmp_path / "test_api_unit.db")
    profile_repo = SQLiteProfileRepository(db_path)
    now = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

    # --- Case 1: X (response_inhibition) has Beta(9,3), Y has no evidence ---
    user_1 = "u_decision_case1"
    client.post("/v1/assessment/consent", json={"user_id": user_1})
    sess_1 = client.post("/v1/assessment/sessions", json={"user_id": user_1}).json()
    s_id_1 = sess_1["session_id"]

    prof_1 = CognitiveProfile(
        user_id=user_1,
        dimensions={
            "response_inhibition": DimensionEstimate(
                dimension="response_inhibition",
                mean=0.75,
                lower=0.529913,
                upper=0.921180,
                n_evidence=12,
                last_update=now,
                alpha=9.0,
                beta_param=3.0,
            ),
        },
        evidence_history=[],
        data_quality={},
        uncertainty={"response_inhibition": 0.921180 - 0.75},
    )
    profile_repo.save_profile(prof_1)

    resp_1 = client.get(f"/v1/assessment/sessions/{s_id_1}/decision")
    assert resp_1.status_code == 200
    d1 = resp_1.json()
    assert d1["status"] == "next_task"
    assert d1["next_task"] == "sequence_span"
    assert d1["reason"] == (
        "Sequential Visual Memory is where our estimate is least certain, so we test it next."
    )

    # --- Case 2: Y (sequential_visual_memory) has Beta(9,3), X has no evidence ---
    user_2 = "u_decision_case2"
    client.post("/v1/assessment/consent", json={"user_id": user_2})
    sess_2 = client.post("/v1/assessment/sessions", json={"user_id": user_2}).json()
    s_id_2 = sess_2["session_id"]

    prof_2 = CognitiveProfile(
        user_id=user_2,
        dimensions={
            "sequential_visual_memory": DimensionEstimate(
                dimension="sequential_visual_memory",
                mean=0.75,
                lower=0.529913,
                upper=0.921180,
                n_evidence=12,
                last_update=now,
                alpha=9.0,
                beta_param=3.0,
            ),
        },
        evidence_history=[],
        data_quality={},
        uncertainty={"sequential_visual_memory": 0.921180 - 0.75},
    )
    profile_repo.save_profile(prof_2)

    resp_2 = client.get(f"/v1/assessment/sessions/{s_id_2}/decision")
    assert resp_2.status_code == 200
    d2 = resp_2.json()
    assert d2["status"] == "next_task"
    assert d2["next_task"] == "go_no_go"
    assert d2["reason"] == (
        "Response Inhibition is where our estimate is least certain, so we test it next."
    )
