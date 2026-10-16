"""Unit tests for the assessment quality gate before profile updates.

Requirements:
- sequence_span: completeness >= 0.8 required.
- go_no_go: at least 11 correct Go out of 15 (0.7).
  This threshold is a design choice with no source: configured in Settings.
- If the gate fails:
  - The result is still stored.
  - The profile is NOT updated.
  - data_quality gets an explicit anomaly code.
- Required case: a participant who never presses (0 presses) must not update
  the profile (today: nogo_accuracy 5/5 = 1.0, profile updated, coach unlocked).
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.core.settings import Settings

_TS = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC).isoformat()


def _client(tmp_path: pathlib.Path, **settings_kwargs: object) -> TestClient:
    db_file = str(tmp_path / "test_gate.db")
    settings = Settings(db_path=db_file, **settings_kwargs)  # type: ignore[arg-type]
    app = create_app(settings)
    return TestClient(app)


def test_gng_zero_presses_fails_gate_and_does_not_update_profile(
    tmp_path: pathlib.Path,
) -> None:
    """Participant who never presses (0 presses) must NOT update the profile.

    Hand-derived arithmetic:
      Standard Go/No-Go task: 15 Go trials + 5 No-Go trials = 20 trials.
      Participant never presses:
        - 15 Go trials: expected="press", response=None.
          Correct Go = 0.
          go_accuracy = 0 / 15 = 0.0.
        - 5 No-Go trials: expected="inhibit", response=None.
          Correct No-Go = 5.
          nogo_accuracy = 5 / 5 = 1.0.
        - completeness = 20 / 20 = 1.0.
      Threshold check:
        go_no_go_min_go_accuracy = 0.7 (at least 11 correct Go out of 15).
        go_accuracy = 0.0 < 0.7 -> Gate FAILS.
      Expected outcomes:
        - Result is stored in assessment repository.
        - data_quality gets explicit anomaly code 'low_go_accuracy'.
        - Profile is NOT updated (response_inhibition dimension absent).
    """
    client = _client(tmp_path)
    user_id = "user_zero_presses"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()[
        "session_id"
    ]

    # Build 15 Go trials with response=None, and 5 No-Go trials with response=None
    trials: list[dict[str, object]] = []
    for _ in range(15):
        trials.append(
            {
                "stimulus": "go",
                "expected": "press",
                "response": None,
                "rt_ms": 0.0,
                "timestamp": _TS,
            }
        )
    for _ in range(5):
        trials.append(
            {
                "stimulus": "nogo",
                "expected": "inhibit",
                "response": None,
                "rt_ms": 0.0,
                "timestamp": _TS,
            }
        )

    submit_resp = client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {"trials": trials},
        },
    )
    assert submit_resp.status_code == 200
    res_data = submit_resp.json()

    # Result data_quality must contain explicit anomaly code
    assert "low_go_accuracy" in res_data["data_quality"]["anomalies"]

    # Result must still be stored in repository
    results_resp = client.get(f"/v1/assessment/sessions/{session_id}/results")
    assert results_resp.status_code == 200
    results_list = results_resp.json()
    assert len(results_list) == 1
    assert "low_go_accuracy" in results_list[0]["data_quality"]["anomalies"]

    # Profile must NOT be updated
    prof_resp = client.get(f"/v1/assessment/profile/{user_id}")
    assert prof_resp.status_code == 200
    profile = prof_resp.json()
    assert "response_inhibition" not in profile["dimensions"]


def test_gng_ten_correct_go_fails_eleven_passes(tmp_path: pathlib.Path) -> None:
    """10 correct Go fails (0.667 < 0.7), 11 correct Go passes (0.733 >= 0.7).

    Hand-derived arithmetic:
      15 Go trials:
      Case A: 10 correct Go, 5 omissions:
        go_accuracy = 10 / 15 = 0.6666...
        0.6666... < 0.7 -> Gate FAILS -> anomaly 'low_go_accuracy', profile NOT updated.
      Case B: 11 correct Go, 4 omissions:
        go_accuracy = 11 / 15 = 0.7333...
        0.7333... >= 0.7 -> Gate PASSES -> no anomaly, profile IS updated.
    """
    client = _client(tmp_path)

    # Case A: 10 correct Go
    user_a = "user_10_go"
    client.post("/v1/assessment/consent", json={"user_id": user_a})
    sess_a = client.post("/v1/assessment/sessions", json={"user_id": user_a}).json()["session_id"]
    trials_a: list[dict[str, object]] = []
    for _ in range(10):
        trials_a.append(
            {
                "stimulus": "go",
                "expected": "press",
                "response": "press",
                "rt_ms": 250.0,
                "timestamp": _TS,
            }
        )
    for _ in range(5):
        trials_a.append(
            {
                "stimulus": "go",
                "expected": "press",
                "response": None,
                "rt_ms": 0.0,
                "timestamp": _TS,
            }
        )
    for _ in range(5):
        trials_a.append(
            {
                "stimulus": "nogo",
                "expected": "inhibit",
                "response": None,
                "rt_ms": 0.0,
                "timestamp": _TS,
            }
        )

    resp_a = client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={"session_id": sess_a, "user_id": user_a, "raw_result": {"trials": trials_a}},
    )
    assert resp_a.status_code == 200
    assert "low_go_accuracy" in resp_a.json()["data_quality"]["anomalies"]
    prof_a = client.get(f"/v1/assessment/profile/{user_a}").json()
    assert "response_inhibition" not in prof_a["dimensions"]

    # Case B: 11 correct Go
    user_b = "user_11_go"
    client.post("/v1/assessment/consent", json={"user_id": user_b})
    sess_b = client.post("/v1/assessment/sessions", json={"user_id": user_b}).json()["session_id"]
    trials_b: list[dict[str, object]] = []
    for _ in range(11):
        trials_b.append(
            {
                "stimulus": "go",
                "expected": "press",
                "response": "press",
                "rt_ms": 250.0,
                "timestamp": _TS,
            }
        )
    for _ in range(4):
        trials_b.append(
            {
                "stimulus": "go",
                "expected": "press",
                "response": None,
                "rt_ms": 0.0,
                "timestamp": _TS,
            }
        )
    for _ in range(5):
        trials_b.append(
            {
                "stimulus": "nogo",
                "expected": "inhibit",
                "response": None,
                "rt_ms": 0.0,
                "timestamp": _TS,
            }
        )

    resp_b = client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={"session_id": sess_b, "user_id": user_b, "raw_result": {"trials": trials_b}},
    )
    assert resp_b.status_code == 200
    assert "low_go_accuracy" not in resp_b.json()["data_quality"]["anomalies"]
    prof_b = client.get(f"/v1/assessment/profile/{user_b}").json()
    assert "response_inhibition" in prof_b["dimensions"]


def test_sequence_span_completeness_gate(tmp_path: pathlib.Path) -> None:
    """sequence_span requires completeness >= 0.8.

    Hand-derived arithmetic:
      Total sequences: 10.
      Case A: 7 valid sequences, 3 timed out (> 30000 ms):
        completeness = 7 / 10 = 0.7.
        0.7 < 0.8 -> Gate FAILS -> anomaly 'low_completeness', profile NOT updated.
      Case B: 8 valid sequences, 2 timed out:
        completeness = 8 / 10 = 0.8.
        0.8 >= 0.8 -> Gate PASSES -> no anomaly, profile IS updated.
    """
    client = _client(tmp_path)

    # Case A: completeness = 7/10 = 0.7 < 0.8
    user_a = "user_span_low"
    client.post("/v1/assessment/consent", json={"user_id": user_a})
    sess_a = client.post("/v1/assessment/sessions", json={"user_id": user_a}).json()["session_id"]
    seqs_a: list[dict[str, object]] = []
    for _ in range(7):
        seqs_a.append(
            {
                "stimulus": "1,2,3",
                "expected": "1,2,3",
                "response": "1,2,3",
                "rt_ms": 2000.0,
                "timestamp": _TS,
                "length": 3,
            }
        )
    for _ in range(3):
        seqs_a.append(
            {
                "stimulus": "1,2,3",
                "expected": "1,2,3",
                "response": None,
                "rt_ms": 35000.0,
                "timestamp": _TS,
                "length": 3,
            }
        )

    resp_a = client.post(
        "/v1/assessment/tasks/sequence_span/submit",
        json={"session_id": sess_a, "user_id": user_a, "raw_result": {"sequences": seqs_a}},
    )
    assert resp_a.status_code == 200
    assert "low_completeness" in resp_a.json()["data_quality"]["anomalies"]
    prof_a = client.get(f"/v1/assessment/profile/{user_a}").json()
    assert "sequential_visual_memory" not in prof_a["dimensions"]

    # Case B: completeness = 8/10 = 0.8 >= 0.8
    user_b = "user_span_ok"
    client.post("/v1/assessment/consent", json={"user_id": user_b})
    sess_b = client.post("/v1/assessment/sessions", json={"user_id": user_b}).json()["session_id"]
    seqs_b: list[dict[str, object]] = []
    for _ in range(8):
        seqs_b.append(
            {
                "stimulus": "1,2,3",
                "expected": "1,2,3",
                "response": "1,2,3",
                "rt_ms": 2000.0,
                "timestamp": _TS,
                "length": 3,
            }
        )
    for _ in range(2):
        seqs_b.append(
            {
                "stimulus": "1,2,3",
                "expected": "1,2,3",
                "response": None,
                "rt_ms": 35000.0,
                "timestamp": _TS,
                "length": 3,
            }
        )

    resp_b = client.post(
        "/v1/assessment/tasks/sequence_span/submit",
        json={"session_id": sess_b, "user_id": user_b, "raw_result": {"sequences": seqs_b}},
    )
    assert resp_b.status_code == 200
    assert "low_completeness" not in resp_b.json()["data_quality"]["anomalies"]
    prof_b = client.get(f"/v1/assessment/profile/{user_b}").json()
    assert "sequential_visual_memory" in prof_b["dimensions"]
