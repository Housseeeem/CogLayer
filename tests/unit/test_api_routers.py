"""Unit tests for FastAPI routers, dependencies, and error branches.

Ensures complete test coverage for all endpoints and error cases in coglayer.api.
"""

from __future__ import annotations

import pathlib

import pytest
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


def test_brain_twin_requires_consent_and_reports_insufficient_data(
    tmp_path: pathlib.Path,
) -> None:
    """The baseline endpoint is consent-protected and honest about empty history."""
    client = _client(tmp_path)
    user_id = "brain-twin-user"

    assert client.get(f"/v1/assessment/brain-twin/{user_id}").status_code == 403

    client.post("/v1/assessment/consent", json={"user_id": user_id})
    response = client.get(f"/v1/assessment/brain-twin/{user_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "INSUFFICIENT_DATA"
    assert response.json()["points"] == []


def test_brain_twin_endpoint_returns_expected_contract_with_history(
    tmp_path: pathlib.Path,
) -> None:
    """The baseline endpoint returns full EMAResult contract when history is available."""
    client = _client(tmp_path)
    user_id = "brain-twin-history-user"
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    # Submit 4 Go/No-Go results to meet minimum_observations threshold
    for i in range(4):
        s_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()[
            "session_id"
        ]
        gng_trials = [
            {
                "stimulus": "go",
                "expected": "press",
                "response": "press",
                "rt_ms": 200.0,
                "timestamp": f"2024-01-15T10:0{i}:00+00:00",
            },
            {
                "stimulus": "nogo",
                "expected": "inhibit",
                "response": None,
                "rt_ms": 0.0,
                "timestamp": f"2024-01-15T10:0{i}:01+00:00",
            },
        ]
        client.post(
            "/v1/assessment/tasks/go_no_go/submit",
            json={"session_id": s_id, "user_id": user_id, "raw_result": {"trials": gng_trials}},
        )

    response = client.get(f"/v1/assessment/brain-twin/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "AVAILABLE"
    assert data["alpha"] == 0.3
    assert data["sigma_multiplier"] == 1.5
    assert len(data["points"]) == 4
    for point in data["points"]:
        assert "observation" in point
        assert "prediction" in point
        assert "residual" in point
        assert "threshold" in point
        assert "flagged" in point
        assert isinstance(point["flagged"], bool)


def test_coach_endpoint_derives_signal_from_persisted_evidence_not_client_input(
    tmp_path: pathlib.Path,
) -> None:
    """Coach endpoint derives signal from DB evidence and ignores spoofed client fields."""
    client = _client(tmp_path)
    user_id = "coach-persisted-user"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    s_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()["session_id"]

    # Complete both tasks so coach is unlocked
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
        json={"session_id": s_id, "user_id": user_id, "raw_result": {"trials": gng}},
    )
    client.post(
        "/v1/assessment/tasks/sequence_span/submit",
        json={"session_id": s_id, "user_id": user_id, "raw_result": {"sequences": span}},
    )

    # Attempt to spoof a VARIATION_FLAGGED signal via request payload
    spoofed_payload = {
        "user_id": user_id,
        "brain_twin_signal": {
            "state": "VARIATION_FLAGGED",
            "comparable_observation_count": 10,
        },
    }
    resp = client.post(f"/v1/assessment/coach/{user_id}", json=spoofed_payload)
    assert resp.status_code == 200
    # Because only 1 session was done, DB has INSUFFICIENT_DATA (count < 4),
    # so variation text MUST NOT appear despite client trying to spoof it.
    assert "differs from the user's usual reference" not in resp.text


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
    bad_resp = client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={"session_id": s_id, "user_id": user_id, "raw_result": {"trials": "not_a_list"}},
    )
    assert bad_resp.status_code == 422
    # Check that all new cognitive lab tasks are in the registered tasks list
    for expected_task in (
        "digit_span",
        "stroop",
        "corsi_blocks",
        "n_back",
        "letter_number_sequencing",
        "perception_lab",
    ):
        assert expected_task in tasks


def test_cognitive_lab_tasks_api_submit_and_listing(tmp_path: pathlib.Path) -> None:
    """Submit results for all new cognitive lab tasks and verify metrics and profile update."""
    client = _client(tmp_path)
    user_id = "lab_test_user"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    s_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()["session_id"]

    # 1. Digit Span
    ds_resp = client.post(
        "/v1/assessment/tasks/digit_span/submit",
        json={
            "session_id": s_id,
            "user_id": user_id,
            "raw_result": {
                "trials": [
                    {
                        "stimulus": "1,2,3",
                        "response": "123",
                        "condition": "forward",
                        "rt_ms": 1500.0,
                    },
                    {
                        "stimulus": "4,5,6",
                        "response": "654",
                        "condition": "backward",
                        "rt_ms": 1800.0,
                    },
                ]
            },
        },
    )
    assert ds_resp.status_code == 200
    assert ds_resp.json()["metrics"]["digit_span_max"] == 3.0

    # 2. Stroop
    stroop_resp = client.post(
        "/v1/assessment/tasks/stroop/submit",
        json={
            "session_id": s_id,
            "user_id": user_id,
            "raw_result": {
                "trials": [
                    {
                        "stimulus": "RED",
                        "expected": "RED",
                        "response": "RED",
                        "condition": "congruent",
                        "rt_ms": 400.0,
                    },
                    {
                        "stimulus": "BLUE",
                        "expected": "GREEN",
                        "response": "GREEN",
                        "condition": "incongruent",
                        "rt_ms": 650.0,
                    },
                ]
            },
        },
    )
    assert stroop_resp.status_code == 200
    stroop_effect = stroop_resp.json()["metrics"]["stroop_effect_ms"]
    assert stroop_effect == pytest.approx(250.0)

    # 3. Corsi Blocks
    corsi_resp = client.post(
        "/v1/assessment/tasks/corsi_blocks/submit",
        json={
            "session_id": s_id,
            "user_id": user_id,
            "raw_result": {
                "sequences": [
                    {
                        "stimulus": "1,2,3",
                        "response": "1,2,3",
                        "condition": "forward",
                        "rt_ms": 2000.0,
                    },
                ]
            },
        },
    )
    assert corsi_resp.status_code == 200
    assert corsi_resp.json()["metrics"]["corsi_span_max"] == 3.0

    # 4. N-Back
    nback_resp = client.post(
        "/v1/assessment/tasks/n_back/submit",
        json={
            "session_id": s_id,
            "user_id": user_id,
            "raw_result": {
                "trials": [
                    {"stimulus": "A", "is_target": True, "response": "MATCH", "rt_ms": 450.0},
                    {"stimulus": "B", "is_target": False, "response": "NO_MATCH", "rt_ms": 420.0},
                ]
            },
        },
    )
    assert nback_resp.status_code == 200
    assert nback_resp.json()["metrics"]["target_accuracy"] == 1.0

    # 5. Letter-Number Sequencing
    lns_resp = client.post(
        "/v1/assessment/tasks/letter_number_sequencing/submit",
        json={
            "session_id": s_id,
            "user_id": user_id,
            "raw_result": {
                "trials": [
                    {"stimulus": "B 1", "response": "1 B", "rt_ms": 2000.0},
                ]
            },
        },
    )
    assert lns_resp.status_code == 200
    assert lns_resp.json()["metrics"]["lns_span_max"] == 2.0

    # 6. Perception Lab
    perc_resp = client.post(
        "/v1/assessment/tasks/perception_lab/submit",
        json={
            "session_id": s_id,
            "user_id": user_id,
            "raw_result": {
                "trials": [
                    {"stimulus": "necker_cube", "response": "4", "rt_ms": 30000.0},
                ]
            },
        },
    )
    assert perc_resp.status_code == 200
    assert perc_resp.json()["metrics"]["switch_rate"] == 4.0

    # Verify profile was updated and can be fetched
    prof_resp = client.get(f"/v1/assessment/profile/{user_id}")
    assert prof_resp.status_code == 200
    profile_data = prof_resp.json()
    assert "working_memory" in profile_data["dimensions"]
    assert "cognitive_flexibility" in profile_data["dimensions"]


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


def test_get_session_rejects_wrong_requested_owner(tmp_path: pathlib.Path) -> None:
    """A durable session ID cannot be used by another requested user."""
    client = _client(tmp_path)
    user_id = "session-owner"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post(
        "/v1/assessment/sessions",
        json={"user_id": user_id},
    ).json()["session_id"]

    assert (
        client.get(
            f"/v1/assessment/sessions/{session_id}",
            params={"user_id": user_id},
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/v1/assessment/sessions/{session_id}",
            params={"user_id": "other-user"},
        ).status_code
        == 403
    )


def test_list_resumable_sessions_is_consent_and_owner_scoped(tmp_path: pathlib.Path) -> None:
    """The session picker only exposes resumable sessions for the requested user."""
    client = _client(tmp_path)
    user_id = "session-picker-user"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    pending_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()[
        "session_id"
    ]
    completed_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()[
        "session_id"
    ]
    client.patch(
        f"/v1/assessment/sessions/{completed_id}/status",
        json={"status": "completed"},
    )

    response = client.get("/v1/assessment/sessions", params={"user_id": user_id})

    assert response.status_code == 200
    assert [item["session_id"] for item in response.json()] == [pending_id]
    assert all(item["user_id"] == user_id for item in response.json())


def test_list_sessions_rejects_user_without_consent(tmp_path: pathlib.Path) -> None:
    """The session picker does not reveal sessions without active consent."""
    client = _client(tmp_path)

    assert (
        client.get(
            "/v1/assessment/sessions",
            params={"user_id": "unconsented-session-picker-user"},
        ).status_code
        == 403
    )


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
    assert "Based on the tasks completed so far" in coach_resp.text


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
