"""Characterization test for task -> dimension links.

Asserts exact dimension and metric currently fed to the profile for built-in tasks:
- go_no_go -> response_inhibition via nogo_accuracy
- sequence_span -> sequential_visual_memory via correct_sequences_ratio
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.core.settings import Settings

_TS = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat()


def _client(tmp_path: pathlib.Path) -> TestClient:
    db_file = str(tmp_path / "test_char.db")
    settings = Settings(db_path=db_file)
    app = create_app(settings)
    return TestClient(app)


def test_characterization_go_no_go_dimension_and_metric(tmp_path: pathlib.Path) -> None:
    """go_no_go feeds response_inhibition via nogo_accuracy to the cognitive profile."""
    client = _client(tmp_path)
    user_id = "u_gng_char"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()[
        "session_id"
    ]

    # 15 Go trials (all correct presses) + 5 No-Go trials
    # (4 correct inhibitions, 1 commission error)
    # nogo_accuracy = 4 / 5 = 0.8
    # go_accuracy = 15 / 15 = 1.0 (passes gate >= 0.7)
    trials: list[dict[str, object]] = []
    for _ in range(15):
        trials.append(
            {
                "stimulus": "go",
                "expected": "press",
                "response": "press",
                "rt_ms": 250.0,
                "timestamp": _TS,
            }
        )
    for _ in range(4):
        trials.append(
            {
                "stimulus": "nogo",
                "expected": "inhibit",
                "response": None,
                "rt_ms": 0.0,
                "timestamp": _TS,
            }
        )
    # 1 commission error
    trials.append(
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": "press",
            "rt_ms": 220.0,
            "timestamp": _TS,
        }
    )

    resp = client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {"trials": trials},
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    # Derived from descriptor and scorer:
    assert data["target_dimensions"] == ["response_inhibition"]
    assert data["metrics"]["nogo_accuracy"] == pytest.approx(0.8)

    # Profile check:
    prof_resp = client.get(f"/v1/assessment/profile/{user_id}")
    assert prof_resp.status_code == 200
    profile = prof_resp.json()

    assert "response_inhibition" in profile["dimensions"]
    assert len(profile["evidence_history"]) == 1
    evidence = profile["evidence_history"][0]
    assert evidence["dimension"] == "response_inhibition"
    assert evidence["reason_code"] == "go_no_go:nogo_accuracy"
    assert evidence["outcome"] == pytest.approx(0.8)


def test_characterization_sequence_span_dimension_and_metric(tmp_path: pathlib.Path) -> None:
    """sequence_span feeds sequential_visual_memory via correct_sequences_ratio to the profile."""
    client = _client(tmp_path)
    user_id = "u_span_char"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()[
        "session_id"
    ]

    # 4 sequences: 3 correct, 1 incorrect
    # completeness = 4/4 = 1.0 (passes gate >= 0.8)
    # correct_sequences_ratio = 3/4 = 0.75
    sequences = [
        {
            "length": 3,
            "stimulus": "1,2,3",
            "expected": "1,2,3",
            "response": "1,2,3",
            "rt_ms": 1200.0,
            "timestamp": _TS,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "length": 3,
            "stimulus": "1,4,2",
            "expected": "1,4,2",
            "response": "1,4,2",
            "rt_ms": 1400.0,
            "timestamp": _TS,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "length": 3,
            "stimulus": "2,3,5",
            "expected": "2,3,5",
            "response": "2,3,5",
            "rt_ms": 1300.0,
            "timestamp": _TS,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "length": 3,
            "stimulus": "3,1,4",
            "expected": "3,1,4",
            "response": "3,2,4",
            "rt_ms": 1500.0,
            "timestamp": _TS,
            "valid": True,
            "invalid_reason": None,
        },
    ]

    resp = client.post(
        "/v1/assessment/tasks/sequence_span/submit",
        json={
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {"sequences": sequences},
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    # Derived from descriptor and scorer:
    assert data["target_dimensions"] == ["sequential_visual_memory"]
    assert data["metrics"]["correct_sequences_ratio"] == pytest.approx(0.75)

    # Profile check:
    prof_resp = client.get(f"/v1/assessment/profile/{user_id}")
    assert prof_resp.status_code == 200
    profile = prof_resp.json()

    assert "sequential_visual_memory" in profile["dimensions"]
    assert len(profile["evidence_history"]) == 1
    evidence = profile["evidence_history"][0]
    assert evidence["dimension"] == "sequential_visual_memory"
    assert evidence["reason_code"] == "sequence_span:correct_sequences_ratio"
    assert evidence["outcome"] == pytest.approx(0.75)
