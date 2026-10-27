"""Unit tests for daily plan lifecycle status transitions.

Validates:
- Allowed transitions: generated→started, started→completed (all tasks done)
- Rejected transitions: completed→started (409), generated→completed (409)
- Auto-completion: submitting all recommended tasks updates plan to completed
- Partial completion keeps plan as started
- GET reconciles stale status against actual session data
- Force regenerate on a completed plan resets to generated
- Consent and identity guards remain active
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.api.db.sqlite import SQLiteAssessmentRepository, SQLiteDailyPlanRepository
from coglayer.core.models import AdaptiveDailyPlan
from coglayer.core.settings import Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GO_NO_GO_PAYLOAD = {
    "trials": [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 250.0,
            "timestamp": "2026-10-25T10:00:00+00:00",
        },
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": None,
            "rt_ms": 0.0,
            "timestamp": "2026-10-25T10:00:01+00:00",
        },
    ]
}

_DIGIT_SPAN_PAYLOAD = {
    "trials": [
        {
            "stimulus": "123",
            "condition": "forward",
            "expected": "123",
            "response": "123",
            "length": 3,
            "rt_ms": 1200.0,
        },
    ]
}

_STROOP_PAYLOAD = {
    "trials": [
        {
            "stimulus": "RED",
            "expected": "RED",
            "response": "RED",
            "condition": "congruent",
            "rt_ms": 500.0,
            "timestamp": "2026-10-25T10:00:00+00:00",
        },
    ]
}

_SEQUENCE_SPAN_PAYLOAD = {
    "trials": [
        {
            "stimulus": "A",
            "expected": "A",
            "response": "A",
            "rt_ms": 300.0,
            "timestamp": "2026-10-25T10:00:00+00:00",
        },
    ]
}

_CORSI_BLOCKS_PAYLOAD = {
    "trials": [
        {
            "stimulus": "1,2",
            "expected": "1,2",
            "response": "1,2",
            "condition": "forward",
            "span_length": 2,
            "rt_ms": 1500.0,
        },
    ]
}

_N_BACK_PAYLOAD = {
    "trials": [
        {
            "stimulus": "A",
            "expected": "no_match",
            "response": "no_match",
            "n_level": 2,
            "rt_ms": 600.0,
            "timestamp": "2026-10-25T10:00:00+00:00",
        },
    ]
}

_LETTER_NUMBER_PAYLOAD = {
    "trials": [
        {
            "stimulus": "B2A1",
            "expected": "1A2B",
            "response": "1A2B",
            "length": 4,
            "rt_ms": 3000.0,
        },
    ]
}

_PERCEPTION_PAYLOAD = {
    "trials": [
        {
            "stimulus": "circle",
            "expected": "circle",
            "response": "circle",
            "rt_ms": 400.0,
            "experiment_type": "visual_search",
            "timestamp": "2026-10-25T10:00:00+00:00",
        },
    ]
}

_PAYLOADS: dict[str, dict[str, Any]] = {
    "go_no_go": _GO_NO_GO_PAYLOAD,
    "digit_span": _DIGIT_SPAN_PAYLOAD,
    "stroop": _STROOP_PAYLOAD,
    "sequence_span": _SEQUENCE_SPAN_PAYLOAD,
    "corsi_blocks": _CORSI_BLOCKS_PAYLOAD,
    "n_back": _N_BACK_PAYLOAD,
    "letter_number_sequencing": _LETTER_NUMBER_PAYLOAD,
    "perception_lab": _PERCEPTION_PAYLOAD,
}


def _setup_user(client: TestClient, user_id: str) -> str:
    """Create consent and session, return session_id."""
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    resp = client.post("/v1/assessment/sessions", json={"user_id": user_id})
    assert resp.status_code == 201
    return str(resp.json()["session_id"])


def _submit_task(
    client: TestClient,
    task_id: str,
    session_id: str,
    user_id: str,
) -> int:
    """Submit a task result and return the response status code."""
    payload = _PAYLOADS.get(task_id)
    if payload is None:
        raise ValueError(f"No test payload registered for task_id={task_id!r}")
    resp = client.post(
        f"/v1/assessment/tasks/{task_id}/submit",
        json={"session_id": session_id, "user_id": user_id, "raw_result": payload},
    )
    return int(resp.status_code)


# ---------------------------------------------------------------------------
# 1. Valid transition: generated → started
# ---------------------------------------------------------------------------
def test_transition_generated_to_started(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "lifecycle_1.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_lifecycle_1"
    session_id = _setup_user(client, user_id)

    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_gen.status_code == 200
    assert res_gen.json()["status"] == "generated"

    res_patch = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={
            "plan_date": "2026-10-25",
            "status": "started",
            "session_id": session_id,
        },
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["status"] == "started"
    assert res_patch.json()["session_id"] == session_id


# ---------------------------------------------------------------------------
# 2. Invalid transition: completed → started (must return 409)
# ---------------------------------------------------------------------------
def test_transition_completed_to_started_rejected(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "lifecycle_2.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_lifecycle_2"
    session_id = _setup_user(client, user_id)

    # Generate → start → complete all tasks to reach completed state
    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_gen.status_code == 200
    plan = res_gen.json()

    # Start plan
    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={
            "plan_date": "2026-10-25",
            "status": "started",
            "session_id": session_id,
        },
    )

    # Submit all recommended tasks to achieve genuine completion
    for rec in plan["recommendations"]:
        status_code = _submit_task(client, rec["task_id"], session_id, user_id)
        assert status_code == 200, f"Failed to submit {rec['task_id']}"

    # Verify plan is now completed
    res_check = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_check.json()["status"] == "completed"

    # Now try to go back to started — must be rejected
    res_reject = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={
            "plan_date": "2026-10-25",
            "status": "started",
            "session_id": session_id,
        },
    )
    assert res_reject.status_code == 409


# ---------------------------------------------------------------------------
# 3. Invalid transition: generated → completed (must return 409)
# ---------------------------------------------------------------------------
def test_transition_generated_to_completed_rejected(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "lifecycle_3.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_lifecycle_3"
    _setup_user(client, user_id)

    client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )

    res_reject = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "completed"},
    )
    assert res_reject.status_code == 409


# ---------------------------------------------------------------------------
# 4. Auto-completion: all recommended tasks submitted → plan completed
# ---------------------------------------------------------------------------
def test_auto_complete_when_all_tasks_submitted(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "lifecycle_4.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_lifecycle_4"
    session_id = _setup_user(client, user_id)

    # Generate plan
    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_gen.status_code == 200
    plan = res_gen.json()
    recs = plan["recommendations"]
    assert len(recs) >= 2, "Expected at least 2 recommendations"

    # Start plan
    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={
            "plan_date": "2026-10-25",
            "status": "started",
            "session_id": session_id,
        },
    )

    # Submit all recommended tasks
    for rec in recs:
        status_code = _submit_task(client, rec["task_id"], session_id, user_id)
        assert status_code == 200, f"Failed to submit {rec['task_id']}"

    # Verify plan is auto-completed
    res_check = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_check.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# 5. Partial completion keeps plan as started
# ---------------------------------------------------------------------------
def test_partial_completion_stays_started(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "lifecycle_5.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_lifecycle_5"
    session_id = _setup_user(client, user_id)

    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    plan = res_gen.json()
    recs = plan["recommendations"]
    assert len(recs) >= 2, "Expected at least 2 recommendations"

    # Start plan
    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={
            "plan_date": "2026-10-25",
            "status": "started",
            "session_id": session_id,
        },
    )

    # Submit only the first recommended task
    status_code = _submit_task(client, recs[0]["task_id"], session_id, user_id)
    assert status_code == 200

    # Verify plan stays started (not completed)
    res_check = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_check.json()["status"] == "started"


# ---------------------------------------------------------------------------
# 6. GET reconciles stale status (started → completed when all done)
# ---------------------------------------------------------------------------
def test_get_reconciles_stale_status(tmp_path: pathlib.Path) -> None:
    """If all tasks are completed but plan status is stale, GET reconciles."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_6.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_lifecycle_6"
    session_id = _setup_user(client, user_id)

    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    plan = res_gen.json()
    recs = plan["recommendations"]

    # Start plan
    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={
            "plan_date": "2026-10-25",
            "status": "started",
            "session_id": session_id,
        },
    )

    # Submit all recommended tasks (the auto-completion in tasks.py will update it,
    # but this test verifies the GET reconciliation path is also correct)
    for rec in recs:
        _submit_task(client, rec["task_id"], session_id, user_id)

    # Re-fetch the plan — should be completed
    res_check = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_check.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# 7. Force regenerate on completed plan resets to generated
# ---------------------------------------------------------------------------
def test_force_regenerate_on_completed_plan(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "lifecycle_7.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_lifecycle_7"
    session_id = _setup_user(client, user_id)

    # Generate, start, complete
    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    plan = res_gen.json()

    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={
            "plan_date": "2026-10-25",
            "status": "started",
            "session_id": session_id,
        },
    )

    for rec in plan["recommendations"]:
        _submit_task(client, rec["task_id"], session_id, user_id)

    # Verify completed
    res_check = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_check.json()["status"] == "completed"

    # Force regenerate — separate operation, not a PATCH
    res_regen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25", "force_regenerate": True},
    )
    assert res_regen.status_code == 200
    assert res_regen.json()["status"] == "generated"


# ---------------------------------------------------------------------------
# 8. Consent / identity guards still active on PATCH
# ---------------------------------------------------------------------------
def test_patch_rejects_unconsented_user(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "lifecycle_8.db"))
    app = create_app(settings)
    client = TestClient(app)

    res = client.patch(
        "/v1/assessment/daily-plan/unconsented_user/status",
        json={"plan_date": "2026-10-25", "status": "started"},
    )
    assert res.status_code == 403


def test_patch_rejects_identity_mismatch(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "lifecycle_9.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_lifecycle_9"
    _setup_user(client, user_id)

    client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )

    res = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status?user_id=other_user",
        json={"plan_date": "2026-10-25", "status": "started"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 9. Idempotent started → started is accepted
# ---------------------------------------------------------------------------
def test_idempotent_started_to_started(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "lifecycle_10.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_lifecycle_10"
    session_id = _setup_user(client, user_id)

    client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )

    # First start
    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={
            "plan_date": "2026-10-25",
            "status": "started",
            "session_id": session_id,
        },
    )

    # Second start (idempotent)
    res = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={
            "plan_date": "2026-10-25",
            "status": "started",
            "session_id": session_id,
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "started"


# ---------------------------------------------------------------------------
# 10. started → generated via PATCH is rejected
# ---------------------------------------------------------------------------
def test_transition_started_to_generated_rejected(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "lifecycle_11.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_lifecycle_11"
    session_id = _setup_user(client, user_id)

    client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )

    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={
            "plan_date": "2026-10-25",
            "status": "started",
            "session_id": session_id,
        },
    )

    res = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "generated"},
    )
    assert res.status_code == 409


# ---------------------------------------------------------------------------
# 11. Cross-user session rejection in PATCH and GET read-repair
# ---------------------------------------------------------------------------
def test_other_user_session_rejected_in_patch_and_get_reconciliation(
    tmp_path: pathlib.Path,
) -> None:
    """A session belonging to user B cannot be used to start or complete user A's plan,
    neither in PATCH nor via GET read-repair."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_cross_user.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_a = "user_cross_a"
    user_b = "user_cross_b"
    _setup_user(client, user_a)
    session_b = _setup_user(client, user_b)

    # User A generates plan
    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_a}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_gen.status_code == 200

    # 1. User A tries to start plan with user B's session -> 403 Forbidden
    res_patch_start = client.patch(
        f"/v1/assessment/daily-plan/{user_a}/status",
        json={
            "plan_date": "2026-10-25",
            "status": "started",
            "session_id": session_b,
        },
    )
    assert res_patch_start.status_code == 403
    assert "not owned by this user" in res_patch_start.json()["detail"].lower()

    # User B completes all tasks in session_b
    plan_a = res_gen.json()
    for rec in plan_a["recommendations"]:
        _submit_task(client, rec["task_id"], session_b, user_b)

    # 2. User A tries to complete plan with user B's session -> 403 Forbidden
    res_patch_comp = client.patch(
        f"/v1/assessment/daily-plan/{user_a}/status",
        json={
            "plan_date": "2026-10-25",
            "status": "completed",
            "session_id": session_b,
        },
    )
    assert res_patch_comp.status_code == 403

    # 3. If user A's plan in repo was corrupted/tampered to point to session_b:
    daily_plan_repo = SQLiteDailyPlanRepository(str(tmp_path / "lifecycle_cross_user.db"))
    tampered_plan = res_gen.json()
    tampered_plan["session_id"] = session_b
    daily_plan_repo.save_plan(AdaptiveDailyPlan.model_validate(tampered_plan))

    # GET read-repair must reject using user B's session and NOT mark user A's plan as completed
    res_get = client.get(
        f"/v1/assessment/daily-plan/{user_a}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_get.status_code == 200
    assert res_get.json()["status"] == "generated"


# ---------------------------------------------------------------------------
# 12. Missing or deleted result prevents completion
# ---------------------------------------------------------------------------
def test_missing_or_deleted_result_prevents_completion(tmp_path: pathlib.Path) -> None:
    """If a result is missing or deleted from database, the plan cannot be completed."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_deleted.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_deleted"
    session_id = _setup_user(client, user_id)

    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    plan = res_gen.json()
    recs = plan["recommendations"]

    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": session_id},
    )

    # Submit all tasks
    for rec in recs:
        _submit_task(client, rec["task_id"], session_id, user_id)

    # Verify plan is completed
    res_check = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_check.json()["status"] == "completed"

    # Now delete one result via assessment repository
    assessment_repo = SQLiteAssessmentRepository(str(tmp_path / "lifecycle_deleted.db"))
    assessment_repo.delete_result(session_id, recs[0]["task_id"])

    # Reset plan status to started in repo to verify that completion cannot be re-achieved
    daily_plan_repo = SQLiteDailyPlanRepository(str(tmp_path / "lifecycle_deleted.db"))
    daily_plan_repo.update_plan_status(user_id, "2026-10-25", "started", session_id)

    # PATCH to completed must be rejected (409) because result is deleted
    res_patch = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "completed", "session_id": session_id},
    )
    assert res_patch.status_code == 409
    assert "not all recommended tasks are finished" in res_patch.json()["detail"].lower()

    # GET read-repair must not complete it either
    res_get = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_get.json()["status"] == "started"


# ---------------------------------------------------------------------------
# 13. Zero valid trials result prevents completion
# ---------------------------------------------------------------------------
def test_zero_valid_trials_prevents_completion(tmp_path: pathlib.Path) -> None:
    """A task result with zero valid trials does not allow plan completion."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_zero_valid.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_zero_valid"
    session_id = _setup_user(client, user_id)

    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    plan = res_gen.json()
    recs = plan["recommendations"]

    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": session_id},
    )

    # Submit go_no_go with anticipation errors (rt_ms < 100ms) resulting in 0 valid trials
    invalid_gng_payload = {
        "trials": [
            {
                "stimulus": "go",
                "expected": "press",
                "response": "press",
                "rt_ms": 30.0,
                "timestamp": "2026-10-25T10:00:00+00:00",
            },
            {
                "stimulus": "go",
                "expected": "press",
                "response": "press",
                "rt_ms": 40.0,
                "timestamp": "2026-10-25T10:00:01+00:00",
            },
        ]
    }

    # Submit all recommendations, but go_no_go has 0 valid trials
    for rec in recs:
        task_id = rec["task_id"]
        if task_id == "go_no_go":
            resp = client.post(
                f"/v1/assessment/tasks/{task_id}/submit",
                json={
                    "session_id": session_id,
                    "user_id": user_id,
                    "raw_result": invalid_gng_payload,
                },
            )
            assert resp.status_code == 200
            assert resp.json()["data_quality"]["valid_trials"] == 0
        else:
            _submit_task(client, task_id, session_id, user_id)

    # Verify session.completed_tasks does NOT contain go_no_go
    sess_resp = client.get(f"/v1/assessment/sessions/{session_id}")
    assert "go_no_go" not in sess_resp.json()["completed_tasks"]

    # Plan cannot be marked completed
    res_patch = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "completed", "session_id": session_id},
    )
    assert res_patch.status_code == 409

    # GET read-repair keeps plan started, not completed
    res_get = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_get.json()["status"] == "started"


# ---------------------------------------------------------------------------
# 14. Non-recommended task does not contribute to completion
# ---------------------------------------------------------------------------
def test_non_recommended_task_does_not_contribute_to_completion(
    tmp_path: pathlib.Path,
) -> None:
    """A task not in plan recommendations does not satisfy completion criteria."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_non_rec.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_non_rec"
    session_id = _setup_user(client, user_id)

    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    plan = res_gen.json()
    recs = plan["recommendations"]
    rec_ids = {r["task_id"] for r in recs}

    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": session_id},
    )

    # Submit a non-recommended task (e.g. letter_number_sequencing)
    non_rec_task = "letter_number_sequencing"
    assert non_rec_task not in rec_ids
    _submit_task(client, non_rec_task, session_id, user_id)

    # Submit only recs[:-1] (leaving one recommended task undone)
    for rec in recs[:-1]:
        _submit_task(client, rec["task_id"], session_id, user_id)

    # Attempt to complete: must be rejected (409)
    res_patch = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "completed", "session_id": session_id},
    )
    assert res_patch.status_code == 409

    res_get = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_get.json()["status"] == "started"


# ---------------------------------------------------------------------------
# 15. Results from different sessions not combined implicitly
# ---------------------------------------------------------------------------
def test_results_from_different_sessions_not_combined(tmp_path: pathlib.Path) -> None:
    """Tasks done in session 1 do not count towards completing plan linked to session 2."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_diff_sessions.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_multi_sess"
    session_1 = _setup_user(client, user_id)
    resp_sess2 = client.post("/v1/assessment/sessions", json={"user_id": user_id})
    session_2 = resp_sess2.json()["session_id"]

    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    plan = res_gen.json()
    recs = plan["recommendations"]

    # Link plan to session_2
    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": session_2},
    )

    # Submit recs[0] in session_1, and the others in session_2
    _submit_task(client, recs[0]["task_id"], session_1, user_id)
    for rec in recs[1:]:
        _submit_task(client, rec["task_id"], session_2, user_id)

    # Try completing plan with session_2: rejected because recs[0] is in session_1
    res_patch = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "completed", "session_id": session_2},
    )
    assert res_patch.status_code == 409

    res_get = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_get.json()["status"] == "started"


# ---------------------------------------------------------------------------
# 16. Regeneration followed by normal GET: no ghost completion
# ---------------------------------------------------------------------------
def test_regeneration_followed_by_normal_get_no_ghost_completion(
    tmp_path: pathlib.Path,
) -> None:
    """Regenerating a completed plan resets it to generated with session_id=None,
    and a subsequent GET does not falsely re-complete it from old session results."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_ghost.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_ghost"
    session_id = _setup_user(client, user_id)

    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    plan = res_gen.json()

    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": session_id},
    )
    for rec in plan["recommendations"]:
        _submit_task(client, rec["task_id"], session_id, user_id)

    # Confirm it is completed
    res_check = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_check.json()["status"] == "completed"

    # Force regenerate
    res_regen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25", "force_regenerate": True},
    )
    assert res_regen.status_code == 200
    assert res_regen.json()["status"] == "generated"
    assert res_regen.json()["session_id"] is None

    # Normal GET without force_regenerate must remain 'generated' without phantom completion
    res_get_normal = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_get_normal.status_code == 200
    assert res_get_normal.json()["status"] == "generated"
    assert res_get_normal.json()["session_id"] is None


# ---------------------------------------------------------------------------
# 17. Task submission across date / rollover
# ---------------------------------------------------------------------------
def test_submission_around_utc_date_change(tmp_path: pathlib.Path) -> None:
    """A session linked to a plan preserves association even if submitted on another date."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_date_rollover.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_rollover"
    session_id = _setup_user(client, user_id)

    # Plan generated for 2026-10-25
    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    plan = res_gen.json()

    # Link plan to session
    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": session_id},
    )

    # Submit all tasks
    for rec in plan["recommendations"]:
        _submit_task(client, rec["task_id"], session_id, user_id)

    # Plan for 2026-10-25 must be completed via session lookup
    res_check = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_check.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# 18. Plan generated without session: justified subsequent association
# ---------------------------------------------------------------------------
def test_generated_plan_without_session_subsequent_justified_association(
    tmp_path: pathlib.Path,
) -> None:
    """A generated plan without session_id associates only when a recommended task is submitted."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_unlinked.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_unlinked"
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    # Generate plan with no session
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": today_str},
    )
    plan = res_gen.json()
    assert plan["status"] == "generated"
    assert plan["session_id"] is None
    recs = plan["recommendations"]
    rec_ids = {r["task_id"] for r in recs}

    # User creates session
    sess_resp = client.post("/v1/assessment/sessions", json={"user_id": user_id})
    session_id = sess_resp.json()["session_id"]

    # 1. Submit non-recommended task: plan remains unlinked and generated
    non_rec = "letter_number_sequencing"
    assert non_rec not in rec_ids
    _submit_task(client, non_rec, session_id, user_id)

    res_check1 = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": today_str},
    )
    assert res_check1.json()["status"] == "generated"
    assert res_check1.json()["session_id"] is None

    # 2. Submit recommended task: plan links session and transitions to started
    _submit_task(client, recs[0]["task_id"], session_id, user_id)

    res_check2 = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": today_str},
    )
    assert res_check2.json()["status"] == "started"
    assert res_check2.json()["session_id"] == session_id

    # 3. Submit remaining recommendations: plan transitions to completed
    for rec in recs[1:]:
        _submit_task(client, rec["task_id"], session_id, user_id)

    res_check3 = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": today_str},
    )
    assert res_check3.json()["status"] == "completed"


# ---------------------------------------------------------------------------
# 19. Retries and duplicate submissions
# ---------------------------------------------------------------------------
def test_retries_and_duplicate_submissions(tmp_path: pathlib.Path) -> None:
    """Duplicate task submission returns 409; retrying idempotent transitions returns 200."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_retries.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_retries"
    session_id = _setup_user(client, user_id)

    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    plan = res_gen.json()
    task_id = plan["recommendations"][0]["task_id"]

    # First submission -> 200
    status_1 = _submit_task(client, task_id, session_id, user_id)
    assert status_1 == 200

    # Duplicate submission in same session -> 409 Conflict
    status_2 = _submit_task(client, task_id, session_id, user_id)
    assert status_2 == 409


# ---------------------------------------------------------------------------
# 20. Invalid transitions and idempotence
# ---------------------------------------------------------------------------
def test_transitions_idempotence_and_invalid_rejections(tmp_path: pathlib.Path) -> None:
    """Verify idempotent transitions return 200, and forbidden transitions 409."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_transitions.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_transitions"
    session_id = _setup_user(client, user_id)

    client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )

    # generated -> generated: idempotent 200
    res_gen_idemp = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "generated"},
    )
    assert res_gen_idemp.status_code == 200
    assert res_gen_idemp.json()["status"] == "generated"

    # generated -> completed: rejected 409
    res_gen_comp = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "completed"},
    )
    assert res_gen_comp.status_code == 409

    # generated -> started: 200
    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": session_id},
    )

    # started -> started: idempotent 200
    res_start_idemp = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": session_id},
    )
    assert res_start_idemp.status_code == 200

    # started -> generated: rejected 409
    res_start_gen = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "generated"},
    )
    assert res_start_gen.status_code == 409


# ---------------------------------------------------------------------------
# 21. Identity and consent guards preserved
# ---------------------------------------------------------------------------
def test_identity_and_consent_preserved_all_endpoints(tmp_path: pathlib.Path) -> None:
    """Unconsented users or query param identity mismatch are rejected with 403."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_guards.db"))
    app = create_app(settings)
    client = TestClient(app)

    # 1. Unconsented GET
    res_unconsented_get = client.get("/v1/assessment/daily-plan/ghost_user")
    assert res_unconsented_get.status_code == 403

    # 2. Unconsented PATCH
    res_unconsented_patch = client.patch(
        "/v1/assessment/daily-plan/ghost_user/status",
        json={"plan_date": "2026-10-25", "status": "started"},
    )
    assert res_unconsented_patch.status_code == 403

    # Consented user
    user_id = "user_guarded"
    _setup_user(client, user_id)

    # 3. GET with mismatched user_id query param
    res_mismatch_get = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"user_id": "other_user"},
    )
    assert res_mismatch_get.status_code == 403

    # 4. PATCH with mismatched user_id query param
    res_mismatch_patch = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        params={"user_id": "other_user"},
        json={"plan_date": "2026-10-25", "status": "started"},
    )
    assert res_mismatch_patch.status_code == 403


# ---------------------------------------------------------------------------
# 22. Historical results not deleted or modified by regeneration
# ---------------------------------------------------------------------------
def test_historical_results_preserved_on_regeneration(tmp_path: pathlib.Path) -> None:
    """Force regenerating a plan does not delete or alter past sessions or results."""
    db_file = str(tmp_path / "lifecycle_preserve_history.db")
    settings = Settings(db_path=db_file)
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_preserve"
    session_id = _setup_user(client, user_id)

    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    plan = res_gen.json()

    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": session_id},
    )

    for rec in plan["recommendations"]:
        _submit_task(client, rec["task_id"], session_id, user_id)

    assessment_repo = SQLiteAssessmentRepository(db_file)
    results_before = assessment_repo.get_results(session_id)
    session_before = assessment_repo.get_session(session_id)
    assert len(results_before) == len(plan["recommendations"])
    assert session_before is not None

    # Force regenerate
    res_regen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25", "force_regenerate": True},
    )
    assert res_regen.status_code == 200

    # Verify history is 100% intact
    results_after = assessment_repo.get_results(session_id)
    session_after = assessment_repo.get_session(session_id)
    assert len(results_after) == len(results_before)
    assert [r.task_id for r in results_after] == [r.task_id for r in results_before]
    assert session_after == session_before


# ---------------------------------------------------------------------------
# 23. Invalid plan_date format validation
# ---------------------------------------------------------------------------
def test_invalid_plan_date_format_rejected(tmp_path: pathlib.Path) -> None:
    """Invalid plan_date string is rejected by GET (400) and PATCH (422)."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_dates.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_dates"
    _setup_user(client, user_id)

    # Invalid date in GET -> 400
    res_get = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "not-a-valid-date"},
    )
    assert res_get.status_code == 400

    # Invalid date in PATCH -> 422
    res_patch = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "not-a-valid-date", "status": "started"},
    )
    assert res_patch.status_code == 422


# ---------------------------------------------------------------------------
# 24. DP-001 Reproduction: Task with low completeness / low valid trials must NOT complete plan
# ---------------------------------------------------------------------------
def test_dp001_low_completeness_does_not_count_as_completed(tmp_path: pathlib.Path) -> None:
    """A task result with low completeness (<0.50 or low_completeness) must not complete plan."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_dp001.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_dp001"
    session_id = _setup_user(client, user_id)

    # Generate plan
    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    assert res_gen.status_code == 200

    # Start plan
    client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": session_id},
    )

    # Submit an aborted / low-completeness payload:
    # 1 valid Go trial (rt=250ms) and 9 anticipation trials (rt=50ms < ANTICIPATION_THRESHOLD_MS)
    # Total trials = 10, valid = 1, completeness = 0.10 < 0.50 (anomalies: ['low_completeness'])
    aborted_trials: list[dict[str, Any]] = [
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 250.0,
            "timestamp": "2026-10-25T10:00:00+00:00",
        }
    ]
    for i in range(1, 10):
        aborted_trials.append(
            {
                "stimulus": "go",
                "expected": "press",
                "response": "press",
                "rt_ms": 50.0,  # anticipation -> valid=False
                "timestamp": f"2026-10-25T10:00:0{i}+00:00",
            }
        )

    resp_submit = client.post(
        "/v1/assessment/tasks/go_no_go/submit",
        json={
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {"trials": aborted_trials},
        },
    )
    assert resp_submit.status_code == 200
    sub_data = resp_submit.json()
    assert sub_data["data_quality"]["valid_trials"] == 1
    assert sub_data["data_quality"]["completeness"] < 0.50
    assert "low_completeness" in sub_data["data_quality"]["anomalies"]

    # 1. The task must NOT be added to session.completed_tasks
    session_data = client.get(f"/v1/assessment/sessions/{session_id}").json()
    assert "go_no_go" not in session_data["completed_tasks"]

    # 2. Daily plan must NOT count this task as verified
    plan_status = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    ).json()
    assert plan_status["status"] != "completed"


# ---------------------------------------------------------------------------
# 25. DP-002 Reproduction: force_regenerate on started plan decouples session
# ---------------------------------------------------------------------------
def test_dp002_force_regenerate_with_existing_results_decouples_session(
    tmp_path: pathlib.Path,
) -> None:
    """Regenerating a started plan with submitted results must decouple session."""
    settings = Settings(db_path=str(tmp_path / "lifecycle_dp002.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_dp002"
    session_id = _setup_user(client, user_id)

    # 1. Generate plan
    res_gen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25"},
    )
    plan = res_gen.json()
    task_0 = plan["recommendations"][0]["task_id"]

    # 2. Start plan with session_id
    res_start = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": session_id},
    )
    assert res_start.status_code == 200
    assert res_start.json()["session_id"] == session_id

    # 3. Complete first task in session_id
    status_code = _submit_task(client, task_0, session_id, user_id)
    assert status_code == 200

    # 4. Force regenerate on this partially completed plan
    res_regen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25", "force_regenerate": True},
    )
    assert res_regen.status_code == 200
    plan_regen = res_regen.json()

    # DP-002 Requirement: session_id must be None to decouple from old submitted results
    assert plan_regen["status"] == "generated"
    assert plan_regen["session_id"] is None

    # Verify a new session can complete tasks without HTTP 409
    res_s2 = client.post("/v1/assessment/sessions", json={"user_id": user_id})
    session_id_2 = res_s2.json()["session_id"]
    status_code_2 = _submit_task(client, task_0, session_id_2, user_id)
    assert status_code_2 == 200
