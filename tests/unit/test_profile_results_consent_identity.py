"""Tests for profile and session results endpoints consent and identity verification.

Verifies:
- STEP 1.a: user without active consent -> 403, no profile data / no results in the body;
  refusal happens before profile or results read.
- STEP 1.b: declared user_id different from the path user_id / session owner -> 403;
  refusal happens before profile or results read.
- STEP 1.c: results endpoint: a session that belongs to another user -> 403;
  refusal happens before results read.
- STEP 1.d: consent + matching or absent declared identity -> unchanged response (non-regression).
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.api.deps import get_assessment_repo, get_profile_repo
from coglayer.core.settings import Settings


def _client(tmp_path: pathlib.Path) -> tuple[TestClient, FastAPI, Settings]:
    settings = Settings(
        db_path=str(tmp_path / "test_profile_results_auth.db"),
        coach_use_llm=False,
    )
    app = create_app(settings)
    return TestClient(app), app, settings


def _create_session_with_result(client: TestClient, user_id: str) -> str:
    """Give consent, create session, and submit one task result."""
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    resp = client.post("/v1/assessment/sessions", json={"user_id": user_id})
    session_id: str = resp.json()["session_id"]

    gng_trials = [
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
        json={"session_id": session_id, "user_id": user_id, "raw_result": {"trials": gng_trials}},
    )
    return session_id


class TestProfileConsentAndIdentity:
    """Verifies consent and declared identity checks on GET /v1/assessment/profile/{user_id}."""

    def test_profile_refused_when_consent_never_recorded(self, tmp_path: pathlib.Path) -> None:
        """Case a: unconsented user receives 403, and profile repo is not read."""
        client, app, settings = _client(tmp_path)
        user_id = "user_no_consent"

        real_profile_repo = get_profile_repo(settings)
        failing_profile_repo = MagicMock(wraps=real_profile_repo)
        failing_profile_repo.get_profile.side_effect = AssertionError(
            "Profile repo must not be read when consent is missing"
        )
        app.dependency_overrides[get_profile_repo] = lambda: failing_profile_repo

        try:
            resp = client.get(f"/v1/assessment/profile/{user_id}")
            assert resp.status_code == 403
            assert resp.json()["detail"] == "User has not given active consent."
            # No profile data in body
            assert "dimensions" not in resp.json()
        finally:
            app.dependency_overrides.clear()

    def test_profile_refused_when_consent_revoked(self, tmp_path: pathlib.Path) -> None:
        """Case a: user who revoked consent receives 403, and profile repo is not read."""
        client, app, settings = _client(tmp_path)
        user_id = "user_revoked_consent"
        _create_session_with_result(client, user_id)

        # Revoke consent
        del_resp = client.delete(f"/v1/assessment/consent/{user_id}")
        assert del_resp.status_code == 204

        real_profile_repo = get_profile_repo(settings)
        failing_profile_repo = MagicMock(wraps=real_profile_repo)
        failing_profile_repo.get_profile.side_effect = AssertionError(
            "Profile repo must not be read when consent is revoked"
        )
        app.dependency_overrides[get_profile_repo] = lambda: failing_profile_repo

        try:
            resp = client.get(f"/v1/assessment/profile/{user_id}")
            assert resp.status_code == 403
            assert resp.json()["detail"] == "User has not given active consent."
            assert "dimensions" not in resp.json()
        finally:
            app.dependency_overrides.clear()

    def test_profile_refused_when_declared_identity_mismatches_path(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Case b: declared user_id different from path user_id receives 403."""
        client, app, settings = _client(tmp_path)
        user_id = "path_user"
        attacker_id = "attacker_user"
        _create_session_with_result(client, user_id)

        real_profile_repo = get_profile_repo(settings)
        failing_profile_repo = MagicMock(wraps=real_profile_repo)
        failing_profile_repo.get_profile.side_effect = AssertionError(
            "Profile repo must not be read when declared identity mismatches"
        )
        app.dependency_overrides[get_profile_repo] = lambda: failing_profile_repo

        try:
            resp = client.get(f"/v1/assessment/profile/{user_id}?user_id={attacker_id}")
            assert resp.status_code == 403
            assert resp.json()["detail"] == "Forbidden for this user."
            assert "dimensions" not in resp.json()
        finally:
            app.dependency_overrides.clear()

    def test_profile_succeeds_with_matching_declared_identity(self, tmp_path: pathlib.Path) -> None:
        """Case d: consent + matching declared identity returns 200 OK."""
        client, _, _ = _client(tmp_path)
        user_id = "matching_user"
        _create_session_with_result(client, user_id)

        resp = client.get(f"/v1/assessment/profile/{user_id}?user_id={user_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == user_id
        assert "dimensions" in data

    def test_profile_succeeds_with_absent_declared_identity(self, tmp_path: pathlib.Path) -> None:
        """Case d: consent + omitted declared identity returns 200 OK (non-regression)."""
        client, _, _ = _client(tmp_path)
        user_id = "omitted_decl_user"
        _create_session_with_result(client, user_id)

        resp = client.get(f"/v1/assessment/profile/{user_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == user_id
        assert "dimensions" in data


class TestSessionResultsConsentAndIdentity:
    """Verifies consent and declared identity checks on
    GET /v1/assessment/sessions/{session_id}/results.
    """

    def test_results_refused_when_consent_never_recorded(self, tmp_path: pathlib.Path) -> None:
        """Case a: unconsented user receives 403, and results are not read."""
        client, app, settings = _client(tmp_path)
        user_id = "unconsented_session_user"
        session_id = _create_session_with_result(client, user_id)

        # Revoke consent
        client.delete(f"/v1/assessment/consent/{user_id}")

        real_assessment_repo = get_assessment_repo(settings)
        failing_assessment_repo = MagicMock(wraps=real_assessment_repo)
        failing_assessment_repo.get_results.side_effect = AssertionError(
            "Assessment repo results must not be read when consent is missing"
        )
        app.dependency_overrides[get_assessment_repo] = lambda: failing_assessment_repo

        try:
            resp = client.get(f"/v1/assessment/sessions/{session_id}/results")
            assert resp.status_code == 403
            assert resp.json()["detail"] == "User has not given active consent."
        finally:
            app.dependency_overrides.clear()

    def test_results_refused_when_declared_user_has_no_consent_before_session_read(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Case a: declared user without consent is refused before any session or results read."""
        client, app, settings = _client(tmp_path)
        unconsented_decl_user = "unconsented_declared_user"

        real_assessment_repo = get_assessment_repo(settings)
        failing_assessment_repo = MagicMock(wraps=real_assessment_repo)
        failing_assessment_repo.get_session.side_effect = AssertionError(
            "Session must not be read when declared user has no consent"
        )
        failing_assessment_repo.get_results.side_effect = AssertionError(
            "Results must not be read when declared user has no consent"
        )
        app.dependency_overrides[get_assessment_repo] = lambda: failing_assessment_repo

        try:
            resp = client.get(
                f"/v1/assessment/sessions/some-session-id/results?user_id={unconsented_decl_user}"
            )
            assert resp.status_code == 403
            assert resp.json()["detail"] == "User has not given active consent."
        finally:
            app.dependency_overrides.clear()

    def test_results_refused_when_session_belongs_to_another_user(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Case b & c: caller declared identity does not match session owner -> 403."""
        client, app, settings = _client(tmp_path)
        owner_user = "session_owner"
        other_user = "other_user"
        session_id = _create_session_with_result(client, owner_user)

        # other_user has consent
        client.post("/v1/assessment/consent", json={"user_id": other_user})

        real_assessment_repo = get_assessment_repo(settings)
        failing_assessment_repo = MagicMock(wraps=real_assessment_repo)
        failing_assessment_repo.get_results.side_effect = AssertionError(
            "Results must not be read when session belongs to another user"
        )
        app.dependency_overrides[get_assessment_repo] = lambda: failing_assessment_repo

        try:
            resp = client.get(f"/v1/assessment/sessions/{session_id}/results?user_id={other_user}")
            assert resp.status_code == 403
            assert resp.json()["detail"] == "Forbidden for this user."
        finally:
            app.dependency_overrides.clear()

    def test_results_succeeds_with_matching_declared_identity(self, tmp_path: pathlib.Path) -> None:
        """Case d: consent + matching declared identity returns 200 OK."""
        client, _, _ = _client(tmp_path)
        user_id = "results_matching_user"
        session_id = _create_session_with_result(client, user_id)

        resp = client.get(f"/v1/assessment/sessions/{session_id}/results?user_id={user_id}")
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)
        assert len(results) >= 1
        assert results[0]["session_id"] == session_id

    def test_results_succeeds_with_absent_declared_identity(self, tmp_path: pathlib.Path) -> None:
        """Case d: consent + omitted declared identity returns 200 OK."""
        client, _, _ = _client(tmp_path)
        user_id = "results_omitted_user"
        session_id = _create_session_with_result(client, user_id)

        resp = client.get(f"/v1/assessment/sessions/{session_id}/results")
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)
        assert len(results) >= 1
        assert results[0]["session_id"] == session_id
