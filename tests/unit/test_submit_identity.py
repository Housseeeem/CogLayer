"""Tests for submit endpoint identity-field integrity.

Fix 1: the endpoint must use identity fields (user_id, session_id, task_id)
from the validated request (body.user_id, body.session_id, URL task_id), NOT
from raw_result.  If raw_result contains different values for these fields,
the stored TaskResult must still carry the trusted values.

Expected behaviour (chosen): the endpoint forces the three identity fields
from the checked request into raw_payload by assignment, not setdefault.

Arithmetic for expected values:
- Go/No-Go scorer hardcodes task_id="go_no_go" from the scorer, but
  user_id and session_id are taken from raw["user_id"] / raw["session_id"].
  If setdefault is used and raw_result already has these keys, the scorer
  picks up the attacker's values.
- SequenceSpanScorer similarly reads user_id and session_id from raw.

Test strategy: submit via the real /tasks/go_no_go/submit endpoint with
raw_result containing a different user_id.  Assert the returned TaskResult
carries body.user_id (the trusted one), not the attacker's value.
Repeat for session_id.
"""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.core.settings import Settings


def _client(tmp_path: pathlib.Path) -> TestClient:
    settings = Settings(db_path=str(tmp_path / "test_identity.db"))
    app = create_app(settings)
    return TestClient(app)


def _setup_user(client: TestClient, user_id: str) -> str:
    """Grant consent, create session, return session_id."""
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    resp = client.post("/v1/assessment/sessions", json={"user_id": user_id})
    session_id: str = resp.json()["session_id"]
    return session_id


def _make_gng_trials() -> list[dict[str, object]]:
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


# ------------------------------------------------------------------
# Fix 1 tests
# ------------------------------------------------------------------


class TestSubmitIdentityUserIdOverride:
    """raw_result.user_id differs from body.user_id.

    Expected: stored result uses body.user_id ("trusted_user"), not
    the attacker value ("attacker_user") found in raw_result.
    """

    def test_user_id_forced_from_body(self, tmp_path: pathlib.Path) -> None:
        client = _client(tmp_path)
        trusted_user = "trusted_user"
        attacker_user = "attacker_user"
        session_id = _setup_user(client, trusted_user)

        resp = client.post(
            "/v1/assessment/tasks/go_no_go/submit",
            json={
                "session_id": session_id,
                "user_id": trusted_user,
                "raw_result": {
                    "user_id": attacker_user,
                    "trials": _make_gng_trials(),
                },
            },
        )
        assert resp.status_code == 200, resp.text
        result = resp.json()
        # The stored result MUST carry the trusted user_id, not the attacker's
        assert result["user_id"] == trusted_user


class TestSubmitIdentitySessionIdOverride:
    """raw_result.session_id differs from body.session_id.

    Expected: stored result uses body.session_id, not the value in
    raw_result.
    """

    def test_session_id_forced_from_body(self, tmp_path: pathlib.Path) -> None:
        client = _client(tmp_path)
        user_id = "sid_test_user"
        session_id = _setup_user(client, user_id)

        resp = client.post(
            "/v1/assessment/tasks/go_no_go/submit",
            json={
                "session_id": session_id,
                "user_id": user_id,
                "raw_result": {
                    "session_id": "attacker_session",
                    "trials": _make_gng_trials(),
                },
            },
        )
        assert resp.status_code == 200, resp.text
        result = resp.json()
        assert result["session_id"] == session_id


class TestSubmitIdentityTaskIdOverride:
    """raw_result.task_id differs from URL task_id.

    The Go/No-Go scorer hardcodes task_id="go_no_go", so this tests that
    the raw_payload["task_id"] is overwritten (even though the scorer
    currently ignores it).  The returned TaskResult.task_id should match
    the URL path task_id.
    """

    def test_task_id_forced_from_url(self, tmp_path: pathlib.Path) -> None:
        client = _client(tmp_path)
        user_id = "tid_test_user"
        session_id = _setup_user(client, user_id)

        resp = client.post(
            "/v1/assessment/tasks/go_no_go/submit",
            json={
                "session_id": session_id,
                "user_id": user_id,
                "raw_result": {
                    "task_id": "evil_task",
                    "trials": _make_gng_trials(),
                },
            },
        )
        assert resp.status_code == 200, resp.text
        result = resp.json()
        # Go/No-Go scorer hardcodes this, so it should pass even before the fix.
        # Included for completeness of the identity-forcing contract.
        assert result["task_id"] == "go_no_go"
