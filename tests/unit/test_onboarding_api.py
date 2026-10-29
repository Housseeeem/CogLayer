"""Unit tests for onboarding API endpoints.

Tests verify PUT and GET /onboarding/profile/{user_id} with consent,
ownership, and guardian consent guards.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.core.settings import Settings


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Create a FastAPI TestClient with isolated SQLite database."""
    settings = Settings(db_path=str(tmp_path / "onboarding_test.db"))
    app = create_app(settings)
    return TestClient(app)


def test_save_profile_success_adult(client: TestClient) -> None:
    """Adult user can save profile with consent."""
    user_id = "adult_user"

    # Give consent
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    # Save profile
    response = client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
        json={
            "age_group": "adult_31_60",
            "goals": ["improve_focus"],
            "tech_comfort": "comfortable",
            "info_style": "detailed",
            "layout": "dashboard",
            "theme": "standard",
            "guidance_level": "some",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id
    assert data["age_group"] == "adult_31_60"
    assert data["goals"] == ["improve_focus"]


def test_save_profile_without_consent(client: TestClient) -> None:
    """Saving profile without consent returns 403."""
    user_id = "no_consent_user"

    response = client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
        json={
            "age_group": "adult_31_60",
            "goals": ["goal1"],
            "tech_comfort": "comfortable",
            "info_style": "detailed",
            "layout": "dashboard",
            "theme": "standard",
        },
    )

    assert response.status_code == 403
    assert "consent" in response.json()["detail"].lower()


def test_save_profile_child_without_guardian_consent(client: TestClient) -> None:
    """Child user without guardian consent returns 403."""
    user_id = "child_user"

    # Give consent WITHOUT guardian_consent
    client.post(
        "/v1/assessment/consent",
        json={"user_id": user_id, "guardian_consent": False, "guardian_id": None},
    )

    response = client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
        json={
            "age_group": "child_7_12",
            "goals": ["attention"],
            "tech_comfort": "some_experience",
            "info_style": "short_simple",
            "layout": "guided_journey",
            "theme": "softer_colors",
            "guidance_level": "more",
        },
    )

    assert response.status_code == 403
    assert "guardian" in response.json()["detail"].lower()


def test_save_profile_child_with_guardian_consent(client: TestClient) -> None:
    """Child user with guardian consent can save profile."""
    user_id = "child_with_guardian"

    # Give consent WITH guardian_consent
    client.post(
        "/v1/assessment/consent",
        json={
            "user_id": user_id,
            "guardian_consent": True,
            "guardian_id": "parent123",
        },
    )

    response = client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
        json={
            "age_group": "child_7_12",
            "goals": ["attention"],
            "tech_comfort": "some_experience",
            "info_style": "short_simple",
            "layout": "guided_journey",
            "theme": "softer_colors",
            "guidance_level": "more",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["age_group"] == "child_7_12"


def test_save_profile_identity_mismatch(client: TestClient) -> None:
    """Saving profile with identity mismatch returns 403."""
    user_id = "user1"

    # Give consent
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    # Try to save with different user_id in query
    response = client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id=other_user",
        json={
            "age_group": "adult_31_60",
            "goals": ["goal1"],
            "tech_comfort": "comfortable",
            "info_style": "detailed",
            "layout": "dashboard",
            "theme": "standard",
        },
    )

    assert response.status_code == 403
    assert "identity" in response.json()["detail"].lower()


def test_get_profile_success(client: TestClient) -> None:
    """User can retrieve their profile with consent."""
    user_id = "get_user"

    # Give consent
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    # Save profile first
    client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
        json={
            "age_group": "young_adult_18_30",
            "goals": ["learn_skills"],
            "tech_comfort": "very_comfortable",
            "info_style": "visual",
            "layout": "conversation_first",
            "theme": "brighter_colors",
        },
    )

    # Get profile
    response = client.get(f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id
    assert data["age_group"] == "young_adult_18_30"
    assert data["goals"] == ["learn_skills"]


def test_get_profile_not_found(client: TestClient) -> None:
    """Getting non-existent profile returns 404."""
    user_id = "ghost_user"

    # Give consent
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    response = client.get(f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_profile_without_consent(client: TestClient) -> None:
    """Getting profile without consent returns 403."""
    user_id = "no_consent_get"

    response = client.get(f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}")

    assert response.status_code == 403
    assert "consent" in response.json()["detail"].lower()


def test_get_profile_identity_mismatch(client: TestClient) -> None:
    """Getting profile with identity mismatch returns 403."""
    user_id = "user1"

    # Give consent and save profile
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
        json={
            "age_group": "adult_31_60",
            "goals": ["goal1"],
            "tech_comfort": "comfortable",
            "info_style": "detailed",
            "layout": "dashboard",
            "theme": "standard",
        },
    )

    # Try to get with different user_id in query
    response = client.get(f"/v1/assessment/onboarding/profile/{user_id}?user_id=other_user")

    assert response.status_code == 403
    assert "identity" in response.json()["detail"].lower()


def test_save_profile_upsert(client: TestClient) -> None:
    """Saving profile twice replaces the existing profile."""
    user_id = "upsert_user"

    # Give consent
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    # First save
    client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
        json={
            "age_group": "adult_31_60",
            "goals": ["goal1"],
            "tech_comfort": "comfortable",
            "info_style": "detailed",
            "layout": "dashboard",
            "theme": "standard",
        },
    )

    # Second save with different data
    response = client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
        json={
            "age_group": "adult_31_60",
            "goals": ["goal1", "goal2"],
            "tech_comfort": "very_comfortable",
            "info_style": "visual",
            "layout": "minimal",
            "theme": "high_contrast",
            "guidance_level": "minimal",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["goals"]) == 2
    assert data["tech_comfort"] == "very_comfortable"
    assert data["guidance_level"] == "minimal"


def test_save_profile_without_guidance_level(client: TestClient) -> None:
    """Profile can be saved without guidance_level."""
    user_id = "no_guidance_api"

    # Give consent
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    response = client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
        json={
            "age_group": "senior_60_plus",
            "goals": ["memory"],
            "tech_comfort": "new",
            "info_style": "step_by_step",
            "layout": "guided_journey",
            "theme": "larger_text",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["guidance_level"] is None


# ---------------------------------------------------------------------------
# Problem 1: Guardian consent guard on calibration endpoint
# ---------------------------------------------------------------------------


def _setup_profile(client: TestClient, user_id: str, age_group: str) -> None:
    """Helper: save an onboarding profile so calibration can find it."""
    client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
        json={
            "age_group": age_group,
            "goals": ["focus"],
            "tech_comfort": "comfortable",
            "info_style": "detailed",
            "layout": "dashboard",
            "theme": "standard",
        },
    )


def test_calibration_minor_without_guardian_refused(client: TestClient) -> None:
    """Child without guardian consent is refused on calibration (403)."""
    user_id = "cal_child_no_guardian"

    # First grant consent WITH guardian so we can save a child profile
    client.post(
        "/v1/assessment/consent",
        json={"user_id": user_id, "guardian_consent": True, "guardian_id": "p1"},
    )
    _setup_profile(client, user_id, "child_7_12")

    # Now re-record consent WITHOUT guardian_consent
    client.post(
        "/v1/assessment/consent",
        json={"user_id": user_id, "guardian_consent": False, "guardian_id": None},
    )

    response = client.post(
        f"/v1/assessment/onboarding/calibration/{user_id}?user_id={user_id}",
        json={"accuracy": 0.8, "mean_rt_ms": 350.0},
    )

    assert response.status_code == 403
    assert "guardian" in response.json()["detail"].lower()


def test_calibration_minor_with_guardian_accepted(client: TestClient) -> None:
    """Child with guardian consent can submit calibration."""
    user_id = "cal_child_with_guardian"

    # Consent WITH guardian_consent
    client.post(
        "/v1/assessment/consent",
        json={
            "user_id": user_id,
            "guardian_consent": True,
            "guardian_id": "parent456",
        },
    )
    _setup_profile(client, user_id, "child_7_12")

    response = client.post(
        f"/v1/assessment/onboarding/calibration/{user_id}?user_id={user_id}",
        json={"accuracy": 0.8, "mean_rt_ms": 350.0},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["guidance_level"] is not None


def test_calibration_adult_accepted(client: TestClient) -> None:
    """Adult can submit calibration without guardian consent."""
    user_id = "cal_adult"

    client.post("/v1/assessment/consent", json={"user_id": user_id})
    _setup_profile(client, user_id, "adult_31_60")

    response = client.post(
        f"/v1/assessment/onboarding/calibration/{user_id}?user_id={user_id}",
        json={"accuracy": 0.8, "mean_rt_ms": 350.0},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["guidance_level"] is not None


def test_guidance_level_survives_final_put(client: TestClient) -> None:
    """A final PUT without guidance_level does not overwrite calibrated guidance_level."""
    user_id = "surviving_guidance_user"

    # 1. User consents
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    # 2. Initial profile saved at entry of step 6 (no guidance_level yet)
    initial_put_resp = client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
        json={
            "age_group": "adult_31_60",
            "goals": ["improve_focus"],
            "tech_comfort": "comfortable",
            "info_style": "detailed",
            "layout": "dashboard",
            "theme": "standard",
        },
    )
    assert initial_put_resp.status_code == 200
    assert initial_put_resp.json()["guidance_level"] is None

    # 3. Calibration submitted during step 6
    cal_resp = client.post(
        f"/v1/assessment/onboarding/calibration/{user_id}?user_id={user_id}",
        json={"accuracy": 0.8, "mean_rt_ms": 350.0},
    )
    assert cal_resp.status_code == 200
    cal_guidance = cal_resp.json()["guidance_level"]
    assert cal_guidance is not None

    # 4. Final PUT at step 7 without guidance_level (guidance_level=None)
    final_put_resp = client.put(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
        json={
            "age_group": "adult_31_60",
            "goals": ["improve_focus"],
            "tech_comfort": "comfortable",
            "info_style": "detailed",
            "layout": "dashboard",
            "theme": "standard",
        },
    )
    assert final_put_resp.status_code == 200
    assert final_put_resp.json()["guidance_level"] == cal_guidance

    # 5. GET confirms guidance_level persisted
    get_resp = client.get(
        f"/v1/assessment/onboarding/profile/{user_id}?user_id={user_id}",
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["guidance_level"] == cal_guidance
