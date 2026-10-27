"""Focused API tests for IOI event recording and score snapshots."""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime
from typing import cast

from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.core.models import IOIComponent, IOIEventType
from coglayer.core.settings import Settings


def _client(tmp_path: pathlib.Path) -> TestClient:
    return TestClient(create_app(Settings(db_path=str(tmp_path / "ioi_api.db"))))


def _event(
    user_id: str,
    session_id: str,
    *,
    event_id: str = "event-1",
    opportunity_id: str = "opportunity-1",
    observed: bool = True,
    component: str = IOIComponent.CRITICAL_VERIFICATION.value,
    event_type: str = IOIEventType.VERIFICATION_OPPORTUNITY.value,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "user_id": user_id,
        "session_id": session_id,
        "component": component,
        "event_type": event_type,
        "opportunity_id": opportunity_id,
        "behavior_observed": observed,
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
        "schema_version": "1.0",
    }


def _session(client: TestClient, user_id: str) -> str:
    assert client.post("/v1/assessment/consent", json={"user_id": user_id}).status_code == 201
    response = client.post("/v1/assessment/sessions", json={"user_id": user_id})
    assert response.status_code == 201
    return cast(str, response.json()["session_id"])


def test_record_event_and_get_insufficient_snapshot(tmp_path: pathlib.Path) -> None:
    client = _client(tmp_path)
    user_id = "ioi-user"
    session_id = _session(client, user_id)

    response = client.post("/v1/assessment/ioi/events", json=_event(user_id, session_id))

    assert response.status_code == 201
    assert response.json()["event_id"] == "event-1"
    snapshot = client.get(f"/v1/assessment/ioi/{user_id}/score", params={"session_id": session_id})
    assert snapshot.status_code == 200
    assert snapshot.json()["status"] == "INSUFFICIENT_EVIDENCE"
    assert snapshot.json()["aggregate_score"] is None
    assert snapshot.json()["components"]["critical_verification"]["evidence_count"] == 1

    refreshed_client = _client(tmp_path)
    refreshed_snapshot = refreshed_client.get(
        f"/v1/assessment/ioi/{user_id}/score",
        params={"session_id": session_id},
    )
    assert refreshed_snapshot.status_code == 200
    assert refreshed_snapshot.json()["components"]["critical_verification"]["evidence_count"] == 1


def test_consent_and_ownership_are_required(tmp_path: pathlib.Path) -> None:
    client = _client(tmp_path)
    owner_session = _session(client, "owner")
    no_consent_event = _event("no-consent", owner_session, event_id="event-no-consent")
    assert client.post("/v1/assessment/ioi/events", json=no_consent_event).status_code == 403

    other_session = _session(client, "other")
    cross_user_event = _event("other", owner_session, event_id="event-cross-user")
    assert client.post("/v1/assessment/ioi/events", json=cross_user_event).status_code == 403
    assert (
        client.get(
            "/v1/assessment/ioi/other/score",
            params={"session_id": owner_session},
        ).status_code
        == 403
    )
    assert other_session != owner_session


def test_duplicate_retry_is_idempotent_and_conflict_is_rejected(tmp_path: pathlib.Path) -> None:
    client = _client(tmp_path)
    user_id = "duplicate-user"
    session_id = _session(client, user_id)
    event = _event(user_id, session_id)

    assert client.post("/v1/assessment/ioi/events", json=event).status_code == 201
    retry = client.post("/v1/assessment/ioi/events", json=event)
    assert retry.status_code == 200
    assert retry.json()["status"] == "duplicate"

    conflict = client.post(
        "/v1/assessment/ioi/events",
        json={**event, "behavior_observed": False},
    )
    assert conflict.status_code == 409


def test_invalid_component_event_pair_is_rejected(tmp_path: pathlib.Path) -> None:
    client = _client(tmp_path)
    user_id = "invalid-user"
    session_id = _session(client, user_id)

    response = client.post(
        "/v1/assessment/ioi/events",
        json=_event(
            user_id,
            session_id,
            component=IOIComponent.CLARIFICATION.value,
        ),
    )

    assert response.status_code == 422


def test_unknown_session_is_rejected(tmp_path: pathlib.Path) -> None:
    client = _client(tmp_path)
    user_id = "unknown-session-user"
    assert client.post("/v1/assessment/consent", json={"user_id": user_id}).status_code == 201

    response = client.post("/v1/assessment/ioi/events", json=_event(user_id, "missing-session"))

    assert response.status_code == 404


def test_malformed_event_is_rejected(tmp_path: pathlib.Path) -> None:
    client = _client(tmp_path)
    user_id = "malformed-event-user"
    session_id = _session(client, user_id)

    response = client.post(
        "/v1/assessment/ioi/events",
        json={**_event(user_id, session_id), "metadata": {"prompt": "raw text"}},
    )

    assert response.status_code == 422


def test_user_deletion_cascades_ioi_events(tmp_path: pathlib.Path) -> None:
    client = _client(tmp_path)
    user_id = "delete-ioi-user"
    session_id = _session(client, user_id)
    assert (
        client.post("/v1/assessment/ioi/events", json=_event(user_id, session_id)).status_code
        == 201
    )

    deletion = client.delete(f"/v1/assessment/users/{user_id}")

    assert deletion.status_code == 204
    assert client.get(f"/v1/assessment/ioi/{user_id}/score").status_code == 403

    # Re-consent and use a new session to verify the cascaded event is gone.
    assert client.post("/v1/assessment/consent", json={"user_id": user_id}).status_code == 201
    new_session_id = _session(client, user_id)
    snapshot = client.get(
        f"/v1/assessment/ioi/{user_id}/score",
        params={"session_id": new_session_id},
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["components"]["critical_verification"]["evidence_count"] == 0


def test_all_components_sufficient_produces_weighted_snapshot(tmp_path: pathlib.Path) -> None:
    client = _client(tmp_path)
    user_id = "complete-user"
    session_id = _session(client, user_id)
    definitions = [
        (IOIComponent.CRITICAL_VERIFICATION.value, IOIEventType.VERIFICATION_OPPORTUNITY.value),
        (IOIComponent.CLARIFICATION.value, IOIEventType.CLARIFICATION_OPPORTUNITY.value),
        (IOIComponent.ITERATION.value, IOIEventType.ITERATION_OPPORTUNITY.value),
        (IOIComponent.AUTONOMY.value, IOIEventType.AUTONOMY_OPPORTUNITY.value),
        (IOIComponent.RESPONSIBLE_USAGE.value, IOIEventType.RESPONSIBLE_USAGE_OPPORTUNITY.value),
    ]
    for component, event_type in definitions:
        for index in range(3):
            response = client.post(
                "/v1/assessment/ioi/events",
                json=_event(
                    user_id,
                    session_id,
                    event_id=f"{component}-{index}",
                    opportunity_id=f"{component}-opportunity-{index}",
                    observed=component == IOIComponent.ITERATION.value,
                    component=component,
                    event_type=event_type,
                ),
            )
            assert response.status_code == 201
        intermediate = client.get(
            f"/v1/assessment/ioi/{user_id}/score",
            params={"session_id": session_id},
        )
        assert intermediate.status_code == 200
        expected_status = (
            "AVAILABLE"
            if component == IOIComponent.RESPONSIBLE_USAGE.value
            else "INSUFFICIENT_EVIDENCE"
        )
        assert intermediate.json()["status"] == expected_status

    snapshot = client.get(f"/v1/assessment/ioi/{user_id}/score")

    assert snapshot.status_code == 200
    assert snapshot.json()["status"] == "AVAILABLE"
    assert snapshot.json()["aggregate_score"] == 0.2
