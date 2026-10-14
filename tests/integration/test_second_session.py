"""Integration tests: Second Session and Edge Cases (REQ-011).

Covers:
- test_ac_second_session_history
- test_ac_interrupted_session
- test_ac_missing_responses
- test_ac_incomplete_session
"""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.core.settings import Settings


def _client(tmp_path: pathlib.Path) -> TestClient:
    """Create a TestClient wired to an isolated SQLite file in tmp_path."""
    settings = Settings(db_path=str(tmp_path / "test_api_sess2.db"))
    app = create_app(settings)
    return TestClient(app)


def test_ac_second_session_history(tmp_path: pathlib.Path) -> None:
    """REQ-011 test_ac_second_session_history.

    Run full happy path in session 1 (consent -> GNG -> Span -> complete).
    Start session 2 with same user, submit fresh results.
    Assert session 1 results are still retrievable, and profile n_evidence >= 2.
    """
    client = _client(tmp_path)
    user_id = "user_hist_001"

    # 1. Session 1
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    s1_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()["session_id"]

    # Submit GNG
    gng1 = [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 220.0,
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
        json={"session_id": s1_id, "user_id": user_id, "raw_result": {"trials": gng1}},
    )

    # Submit Span
    span1 = [
        {
            "stimulus": "0,1,2",
            "expected": "0,1,2",
            "response": "0,1,2",
            "rt_ms": 1200.0,
            "timestamp": "2024-01-15T10:00:10+00:00",
            "length": 3,
        }
    ]
    client.post(
        "/v1/assessment/tasks/sequence_span/submit",
        json={"session_id": s1_id, "user_id": user_id, "raw_result": {"sequences": span1}},
    )

    # Mark session 1 complete
    client.patch(f"/v1/assessment/sessions/{s1_id}/status", json={"status": "completed"})

    # Check profile after session 1
    p1 = client.get(f"/v1/assessment/profile/{user_id}").json()
    assert p1["dimensions"]["response_inhibition"]["n_evidence"] == 1

    # 2. Session 2
    s2_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()["session_id"]
    assert s2_id != s1_id

    # Submit second GNG result
    client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={"session_id": s2_id, "user_id": user_id, "raw_result": {"trials": gng1}},
    )

    # Verify session 1 results are still retrievable
    s1_res = client.get(f"/v1/assessment/sessions/{s1_id}/results").json()
    assert len(s1_res) == 2

    # Verify session 2 results are retrievable
    s2_res = client.get(f"/v1/assessment/sessions/{s2_id}/results").json()
    assert len(s2_res) == 1

    # Verify profile n_evidence is now >= 2 for response_inhibition
    p2 = client.get(f"/v1/assessment/profile/{user_id}").json()
    assert p2["dimensions"]["response_inhibition"]["n_evidence"] >= 2


def test_ac_interrupted_session(tmp_path: pathlib.Path) -> None:
    """REQ-011 test_ac_interrupted_session.

    Create session, submit GNG, mark session INTERRUPTED, evaluate decide()
    -> expect sequence_span next.
    """
    client = _client(tmp_path)
    user_id = "user_interrupted_001"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    s_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()["session_id"]

    gng = [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 220.0,
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
        json={"session_id": s_id, "user_id": user_id, "raw_result": {"trials": gng}},
    )

    # Mark INTERRUPTED
    client.patch(f"/v1/assessment/sessions/{s_id}/status", json={"status": "interrupted"})

    # Evaluate decision
    decision = client.get(f"/v1/assessment/sessions/{s_id}/decision").json()
    assert decision["status"] == "next_task"
    assert decision["next_task"] == "sequence_span"


def test_ac_missing_responses(tmp_path: pathlib.Path) -> None:
    """REQ-011 test_ac_missing_responses.

    When both tasks have results submitted, but one has completeness < 0.8,
    decide() returns insufficient_data.
    """
    client = _client(tmp_path)
    user_id = "user_missing_001"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    s_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()["session_id"]

    # Submit GNG where only 1 of 4 trials is valid -> completeness = 0.25 < 0.8
    # Anticipation rt_ms < 100 marks trial invalid
    gng_low = [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 50.0,
            "timestamp": "2024-01-15T10:00:00+00:00",
        },  # anticipation
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 50.0,
            "timestamp": "2024-01-15T10:00:01+00:00",
        },  # anticipation
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 50.0,
            "timestamp": "2024-01-15T10:00:02+00:00",
        },  # anticipation
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": None,
            "rt_ms": 0.0,
            "timestamp": "2024-01-15T10:00:03+00:00",
        },  # valid
    ]
    client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={"session_id": s_id, "user_id": user_id, "raw_result": {"trials": gng_low}},
    )

    # Submit sequence span
    span = [
        {
            "stimulus": "0,1,2",
            "expected": "0,1,2",
            "response": "0,1,2",
            "rt_ms": 1200.0,
            "timestamp": "2024-01-15T10:00:10+00:00",
            "length": 3,
        }
    ]
    client.post(
        "/v1/assessment/tasks/sequence_span/submit",
        json={"session_id": s_id, "user_id": user_id, "raw_result": {"sequences": span}},
    )

    decision = client.get(f"/v1/assessment/sessions/{s_id}/decision").json()
    assert decision["status"] == "insufficient_data"


def test_ac_incomplete_session(tmp_path: pathlib.Path) -> None:
    """REQ-011 test_ac_incomplete_session.

    Open session, submit nothing, call decide() -> returns next_task: go_no_go.
    """
    client = _client(tmp_path)
    user_id = "user_incomp_001"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    s_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()["session_id"]

    decision = client.get(f"/v1/assessment/sessions/{s_id}/decision").json()
    assert decision["status"] == "next_task"
    assert decision["next_task"] == "go_no_go"
