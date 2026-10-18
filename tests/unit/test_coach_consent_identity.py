"""Tests for coach endpoint consent and identity verification.

Verifies:
- STEP 1.a: User without recorded consent (never consented or revoked) -> HTTP 403 Forbidden,
  no feedback text in response body, refusal happens before profile read or feedback generation.
- STEP 1.b: Request whose identity does not match the user_id in path/query -> HTTP 403 Forbidden,
  refusal happens before profile read or feedback generation.
- STEP 1.c: User with active consent and matching identity -> HTTP 200 OK (non-regression).
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.api.deps import get_assessment_repo, get_coach, get_profile_repo
from coglayer.core.settings import Settings


def _client(tmp_path: pathlib.Path) -> tuple[TestClient, FastAPI, Settings]:
    settings = Settings(
        db_path=str(tmp_path / "test_coach_auth.db"),
        coach_use_llm=False,
    )
    app = create_app(settings)
    return TestClient(app), app, settings


def _complete_assessment_for_user(client: TestClient, user_id: str) -> str:
    """Give consent, create session, submit GNG and Span tasks so coach is unlocked."""
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
        json={"session_id": session_id, "user_id": user_id, "raw_result": {"trials": gng_trials}},
    )

    span_sequences = [
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
        json={
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {"sequences": span_sequences},
        },
    )
    return session_id


class TestCoachConsentVerification:
    """Case a: user without recorded consent is refused with HTTP 403."""

    def test_coach_refused_when_consent_never_recorded(self, tmp_path: pathlib.Path) -> None:
        client, app, settings = _client(tmp_path)
        user_id = "user_never_consented"

        # Assessment completed by another means or partial, but NO consent given
        # Here we mock profile_repo and coach to raise if called
        real_profile_repo = get_profile_repo(settings)
        failing_profile_repo = MagicMock(wraps=real_profile_repo)
        failing_profile_repo.get_profile.side_effect = AssertionError(
            "Profile repo must not be read when consent is missing"
        )
        app.dependency_overrides[get_profile_repo] = lambda: failing_profile_repo

        real_coach = get_coach()
        failing_coach = MagicMock(wraps=real_coach)
        failing_coach.generate_feedback.side_effect = AssertionError(
            "Coach generate_feedback must not be called when consent is missing"
        )
        app.dependency_overrides[get_coach] = lambda: failing_coach

        try:
            resp = client.post(f"/v1/assessment/coach/{user_id}")
            assert resp.status_code == 403
            assert resp.json()["detail"] == "User has not given active consent."
            # No feedback text in body
            assert "Based on these two tasks only" not in resp.text
            assert "Observations:" not in resp.text
        finally:
            app.dependency_overrides.clear()

    def test_coach_refused_when_consent_revoked(self, tmp_path: pathlib.Path) -> None:
        client, app, settings = _client(tmp_path)
        user_id = "user_consent_revoked"
        _complete_assessment_for_user(client, user_id)

        # Revoke consent
        del_resp = client.delete(f"/v1/assessment/consent/{user_id}")
        assert del_resp.status_code == 204

        # Install guards to ensure refusal happens before profile read / feedback generation
        real_profile_repo = get_profile_repo(settings)
        failing_profile_repo = MagicMock(wraps=real_profile_repo)
        failing_profile_repo.get_profile.side_effect = AssertionError(
            "Profile repo must not be read when consent is revoked"
        )
        app.dependency_overrides[get_profile_repo] = lambda: failing_profile_repo

        real_coach = get_coach()
        failing_coach = MagicMock(wraps=real_coach)
        failing_coach.generate_feedback.side_effect = AssertionError(
            "Coach generate_feedback must not be called when consent is revoked"
        )
        app.dependency_overrides[get_coach] = lambda: failing_coach

        try:
            resp = client.post(f"/v1/assessment/coach/{user_id}")
            assert resp.status_code == 403
            assert resp.json()["detail"] == "User has not given active consent."
            # No feedback text in body
            assert "Based on these two tasks only" not in resp.text
            assert "Observations:" not in resp.text
        finally:
            app.dependency_overrides.clear()

    def test_coach_refused_before_session_read_when_consent_missing(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Ordering: unconsented user check refuses before session is read."""
        client, app, settings = _client(tmp_path)
        user_id = "user_unconsented_session"

        real_assessment_repo = get_assessment_repo(settings)
        failing_assessment_repo = MagicMock(wraps=real_assessment_repo)
        failing_assessment_repo.get_session.side_effect = AssertionError(
            "Session must not be read when consent is missing"
        )
        app.dependency_overrides[get_assessment_repo] = lambda: failing_assessment_repo

        try:
            resp = client.post(
                f"/v1/assessment/coach/{user_id}",
                json={"session_id": "any_session_id"},
            )
            assert resp.status_code == 403
            assert resp.json()["detail"] == "User has not given active consent."
        finally:
            app.dependency_overrides.clear()


class TestCoachIdentityVerification:
    """Case b: request whose identity does not match user_id in path/query is refused."""

    def test_coach_refused_when_body_identity_mismatches_path(self, tmp_path: pathlib.Path) -> None:
        client, app, settings = _client(tmp_path)
        trusted_user = "trusted_user_id"
        attacker_user = "attacker_user_id"
        _complete_assessment_for_user(client, trusted_user)

        # Guard against profile read or feedback generation on mismatched identity
        real_profile_repo = get_profile_repo(settings)
        failing_profile_repo = MagicMock(wraps=real_profile_repo)
        failing_profile_repo.get_profile.side_effect = AssertionError(
            "Profile repo must not be read when identity mismatches"
        )
        app.dependency_overrides[get_profile_repo] = lambda: failing_profile_repo

        real_coach = get_coach()
        failing_coach = MagicMock(wraps=real_coach)
        failing_coach.generate_feedback.side_effect = AssertionError(
            "Coach generate_feedback must not be called when identity mismatches"
        )
        app.dependency_overrides[get_coach] = lambda: failing_coach

        try:
            resp = client.post(
                f"/v1/assessment/coach/{trusted_user}",
                json={"user_id": attacker_user},
            )
            assert resp.status_code == 403
            # Refused, no feedback in body
            assert "Based on these two tasks only" not in resp.text
        finally:
            app.dependency_overrides.clear()

    def test_coach_refused_when_query_identity_mismatches_path(
        self, tmp_path: pathlib.Path
    ) -> None:
        client, app, settings = _client(tmp_path)
        trusted_user = "trusted_query_user"
        attacker_user = "attacker_query_user"
        _complete_assessment_for_user(client, trusted_user)

        real_profile_repo = get_profile_repo(settings)
        failing_profile_repo = MagicMock(wraps=real_profile_repo)
        failing_profile_repo.get_profile.side_effect = AssertionError(
            "Profile repo must not be read when identity mismatches"
        )
        app.dependency_overrides[get_profile_repo] = lambda: failing_profile_repo

        real_coach = get_coach()
        failing_coach = MagicMock(wraps=real_coach)
        failing_coach.generate_feedback.side_effect = AssertionError(
            "Coach generate_feedback must not be called when identity mismatches"
        )
        app.dependency_overrides[get_coach] = lambda: failing_coach

        try:
            resp = client.post(
                f"/v1/assessment/coach/{trusted_user}?user_id={attacker_user}",
            )
            assert resp.status_code == 403
            assert "Based on these two tasks only" not in resp.text
        finally:
            app.dependency_overrides.clear()

    def test_coach_refused_when_session_belongs_to_another_user(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Case c: user A requests feedback referencing user B's session -> 403."""
        client, _, _ = _client(tmp_path)
        user_a = "user_a"
        user_b = "user_b"
        session_b = _complete_assessment_for_user(client, user_b)
        _complete_assessment_for_user(client, user_a)

        resp = client.post(
            f"/v1/assessment/coach/{user_a}",
            json={"session_id": session_b},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Session not found or forbidden for this user."


class TestCoachNonRegression:
    """Case c: user with consent and matching identity receives feedback."""

    def test_coach_succeeds_with_matching_body_identity(self, tmp_path: pathlib.Path) -> None:
        client, _, _ = _client(tmp_path)
        user_id = "user_matching_body"
        _complete_assessment_for_user(client, user_id)

        resp = client.post(
            f"/v1/assessment/coach/{user_id}",
            json={"user_id": user_id},
        )
        assert resp.status_code == 200
        assert "Based on these two tasks only" in resp.text
        assert "Observations:" in resp.text

    def test_coach_succeeds_with_omitted_body_identity(self, tmp_path: pathlib.Path) -> None:
        client, _, _ = _client(tmp_path)
        user_id = "user_omitted_body"
        _complete_assessment_for_user(client, user_id)

        resp = client.post(f"/v1/assessment/coach/{user_id}")
        assert resp.status_code == 200
        assert "Based on these two tasks only" in resp.text
        assert "Observations:" in resp.text
