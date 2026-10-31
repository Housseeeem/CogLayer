"""Integration tests: Full Loop (REQ-011).

Covers the complete vertical slice loop over the FastAPI HTTP interface:
- test_ac_new_session_after_consent
- test_ac_storage_raw_trials_retained
- test_ac_profile_data_quality
- test_ac_double_submission
- test_ac_coach_lock
"""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.core.settings import Settings


def _client(tmp_path: pathlib.Path) -> TestClient:
    """Create a TestClient wired to an isolated SQLite file in tmp_path."""
    settings = Settings(db_path=str(tmp_path / "test_api.db"))
    app = create_app(settings)
    return TestClient(app)


def test_ac_new_session_after_consent(tmp_path: pathlib.Path) -> None:
    """REQ-011 test_ac_new_session_after_consent.

    POST consent -> POST session returns Session object.
    Attempting to create a session without consent returns HTTP 403.
    """
    client = _client(tmp_path)
    user_id = "user_loop_001"

    # Attempt session without consent -> 403 Forbidden
    resp = client.post("/v1/assessment/sessions", json={"user_id": user_id})
    assert resp.status_code == 403

    # Grant consent
    consent_resp = client.post("/v1/assessment/consent", json={"user_id": user_id})
    assert consent_resp.status_code == 201
    assert consent_resp.json()["user_id"] == user_id
    assert consent_resp.json()["revoked_at"] is None

    # Check consent status endpoint
    status_resp = client.get(f"/v1/assessment/consent/{user_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["has_consented"] is True

    # Now create session -> 201 Created with valid Session object
    session_resp = client.post("/v1/assessment/sessions", json={"user_id": user_id})
    assert session_resp.status_code == 201
    session_data = session_resp.json()
    assert session_data["user_id"] == user_id
    assert session_data["status"] == "pending"
    assert "session_id" in session_data


def test_ac_storage_raw_trials_retained(tmp_path: pathlib.Path) -> None:
    """REQ-011 test_ac_storage_raw_trials_retained.

    Submit Go/No-Go result -> GET session results -> all trial rows present.
    """
    client = _client(tmp_path)
    user_id = "user_loop_002"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()[
        "session_id"
    ]

    trials_payload = [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 220.0,
            "timestamp": "2024-01-15T10:00:00+00:00",
        },
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 280.0,
            "timestamp": "2024-01-15T10:00:01+00:00",
        },
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": None,
            "rt_ms": 0.0,
            "timestamp": "2024-01-15T10:00:02+00:00",
        },
    ]

    submit_resp = client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {
                "trials": trials_payload,
            },
        },
    )
    assert submit_resp.status_code == 200
    res_data = submit_resp.json()
    assert len(res_data["trials"]) == 3

    # Query GET /v1/assessment/sessions/{session_id}/results
    get_res = client.get(f"/v1/assessment/sessions/{session_id}/results")
    assert get_res.status_code == 200
    all_results = get_res.json()
    assert len(all_results) == 1
    stored_trials = all_results[0]["trials"]
    assert len(stored_trials) == 3
    assert stored_trials[0]["stimulus"] == "go"
    assert stored_trials[2]["stimulus"] == "nogo"


def test_ac_profile_data_quality(tmp_path: pathlib.Path) -> None:
    """REQ-011 test_ac_profile_data_quality.

    After GNG submit -> GET profile -> dimension response_inhibition present
    with lower <= mean <= upper and data quality summary.
    """
    client = _client(tmp_path)
    user_id = "user_loop_003"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()[
        "session_id"
    ]

    trials_payload = [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 210.0,
            "timestamp": "2024-01-15T10:00:00+00:00",
        },
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": None,
            "rt_ms": 0.0,
            "timestamp": "2024-01-15T10:00:01+00:00",
        },
    ]
    client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {"trials": trials_payload},
        },
    )

    prof_resp = client.get(f"/v1/assessment/profile/{user_id}")
    assert prof_resp.status_code == 200
    profile = prof_resp.json()
    assert "response_inhibition" in profile["dimensions"]
    est = profile["dimensions"]["response_inhibition"]
    assert 0.0 <= est["mean"] <= 1.0
    assert est["lower"] <= est["mean"] <= est["upper"]
    assert "response_inhibition" in profile["data_quality"]


def test_ac_double_submission(tmp_path: pathlib.Path) -> None:
    """REQ-011 test_ac_double_submission.

    Submitting same (session_id, task_id) twice returns HTTP 409 Conflict.
    """
    client = _client(tmp_path)
    user_id = "user_loop_004"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()[
        "session_id"
    ]

    trials = [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 250.0,
            "timestamp": "2024-01-15T10:00:00+00:00",
        }
    ]
    payload = {"session_id": session_id, "user_id": user_id, "raw_result": {"trials": trials}}

    first = client.post("/v1/assessment/tasks/go_no_go/submit", json=payload)
    assert first.status_code == 200

    second = client.post("/v1/assessment/tasks/go_no_go/submit", json=payload)
    assert second.status_code == 409


def test_ac_coach_lock(tmp_path: pathlib.Path) -> None:
    """REQ-011 test_ac_coach_lock.

    POST coach before both tasks done -> HTTP 403.
    After both done -> HTTP 200 with friendly feedback string containing disclaimer.
    """
    client = _client(tmp_path)
    user_id = "user_loop_005"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()[
        "session_id"
    ]

    # Before any task -> coach locked (403)
    c1 = client.post(f"/v1/assessment/coach/{user_id}")
    assert c1.status_code == 403

    # Submit GNG only -> still locked (403)
    client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {
                "trials": [
                    {
                        "stimulus": "go",
                        "expected": "press",
                        "response": "press",
                        "rt_ms": 200.0,
                        "timestamp": "2024-01-15T10:00:00+00:00",
                    },
                    {
                        "stimulus": "nogo",
                        "expected": "inhibit",
                        "response": None,
                        "rt_ms": 0.0,
                        "timestamp": "2024-01-15T10:00:01+00:00",
                    },
                ]
            },
        },
    )
    c2 = client.post(f"/v1/assessment/coach/{user_id}")
    assert c2.status_code == 403

    # Submit Sequence Span -> both complete -> unlocked (200)
    client.post(
        "/v1/assessment/tasks/sequence_span/submit",
        json={
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {
                "sequences": [
                    {
                        "stimulus": "0,1,2",
                        "expected": "0,1,2",
                        "response": "0,1,2",
                        "rt_ms": 1200.0,
                        "timestamp": "2024-01-15T10:00:10+00:00",
                        "length": 3,
                    }
                ]
            },
        },
    )
    c3 = client.post(f"/v1/assessment/coach/{user_id}")
    assert c3.status_code == 200
    feedback = c3.text
    assert "Based on the tasks completed so far" in feedback
