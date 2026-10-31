"""Unit tests for goal tracking and dimension mapping.

Tests:
- Goal mapping (canonical, keyword, fallback)
- Progress maths (insufficient data, active progress, capped target, completed status)
- API endpoint GET /v1/assessment/profile/{user_id}/goals
- Dashboard formatting and rendering smoke test
"""

from __future__ import annotations

import pathlib
from unittest.mock import patch

from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.core.goals import (
    compute_goal_progress,
    map_goal_to_dimensions,
)
from coglayer.core.settings import Settings
from coglayer.ui.dashboard import build_goal_display_data, render_goal_tracking


def test_goal_mapping_canonical() -> None:
    """Canonical onboarding goals map to expected dimensions."""
    dims_focus = map_goal_to_dimensions("Improve focus during homework")
    assert dims_focus == ["response_inhibition"]

    dims_instruct = map_goal_to_dimensions("Get better at following instructions")
    assert "working_memory" in dims_instruct
    assert "sequential_visual_memory" in dims_instruct

    dims_think = map_goal_to_dimensions("Practice quick thinking")
    assert "cognitive_flexibility" in dims_think


def test_goal_mapping_keywords() -> None:
    """Custom goal strings map via keyword heuristics."""
    dims_hw = map_goal_to_dimensions("Better concentration while doing homework")
    assert "response_inhibition" in dims_hw

    dims_seq = map_goal_to_dimensions("Remember spatial block sequences")
    assert "sequential_visual_memory" in dims_seq

    dims_mem = map_goal_to_dimensions("Remember long number sequences")
    assert "working_memory" in dims_mem or "sequential_visual_memory" in dims_mem


def test_goal_mapping_fallback() -> None:
    """Unrecognized goal strings default to reasonable cognitive dimensions."""
    dims = map_goal_to_dimensions("xyzabc completely unrelated string")
    assert len(dims) >= 1
    assert "working_memory" in dims or "response_inhibition" in dims


def test_progress_insufficient_data() -> None:
    """When fewer than min_sessions observations exist, status is insufficient_data."""
    profile_data = {
        "dimensions": {
            "response_inhibition": {
                "mean": 0.75,
                "lower": 0.60,
                "upper": 0.85,
                "n_evidence": 1,
            }
        },
        "evidence_history": [
            {
                "dimension": "response_inhibition",
                "outcome": 0.70,
                "weight": 1.0,
                "timestamp": "2026-10-01T10:00:00Z",
            }
        ],
    }
    progress = compute_goal_progress(
        "Improve focus during homework",
        profile_data,
        min_sessions=3,
    )
    assert progress.status == "insufficient_data"
    assert progress.status_text == "Not enough data yet"
    assert progress.n_sessions == 1


def test_progress_math_active() -> None:
    """With sufficient sessions, computes baseline, current, target (+10%), and active status."""
    profile_data = {
        "dimensions": {
            "response_inhibition": {
                "mean": 0.64,
                "lower": 0.55,
                "upper": 0.72,
                "n_evidence": 3,
            }
        },
        "evidence_history": [
            {
                "dimension": "response_inhibition",
                "outcome": 0.60,
                "weight": 5.0,
                "timestamp": "2026-10-01T10:00:00Z",
            },
            {
                "dimension": "response_inhibition",
                "outcome": 0.68,
                "weight": 5.0,
                "timestamp": "2026-10-02T10:00:00Z",
            },
            {
                "dimension": "response_inhibition",
                "outcome": 0.75,
                "weight": 5.0,
                "timestamp": "2026-10-03T10:00:00Z",
            },
        ],
    }
    progress = compute_goal_progress(
        "Improve focus during homework",
        profile_data,
        baseline_n=1,
        target_delta=0.10,
        min_sessions=3,
    )
    assert progress.status == "active"
    assert progress.status_text == "In progress"
    assert progress.n_sessions == 3
    assert progress.baseline is not None
    assert progress.current == 0.64
    assert progress.target is not None
    # target should be baseline + 0.10
    assert abs(progress.target - (progress.baseline + 0.10)) < 1e-4
    assert progress.lower == 0.55
    assert progress.upper == 0.72


def test_progress_math_capped_target() -> None:
    """Target is capped at 1.0 (100%) even if baseline + delta exceeds 1.0."""
    profile_data = {
        "dimensions": {
            "response_inhibition": {
                "mean": 0.96,
                "lower": 0.90,
                "upper": 0.99,
                "n_evidence": 4,
            }
        },
        "evidence_history": [
            {
                "dimension": "response_inhibition",
                "outcome": 0.98,
                "weight": 10.0,
                "timestamp": "2026-10-01T10:00:00Z",
            },
            {
                "dimension": "response_inhibition",
                "outcome": 0.95,
                "weight": 10.0,
                "timestamp": "2026-10-02T10:00:00Z",
            },
            {
                "dimension": "response_inhibition",
                "outcome": 0.96,
                "weight": 10.0,
                "timestamp": "2026-10-03T10:00:00Z",
            },
        ],
    }
    progress = compute_goal_progress(
        "Improve focus during homework",
        profile_data,
        target_delta=0.15,
        min_sessions=3,
    )
    assert progress.target == 1.0
    assert progress.target <= 1.0


def test_progress_math_completed_status() -> None:
    """When current posterior mean reaches or exceeds target, status is completed."""
    profile_data = {
        "dimensions": {
            "response_inhibition": {
                "mean": 0.85,
                "lower": 0.75,
                "upper": 0.92,
                "n_evidence": 3,
            }
        },
        "evidence_history": [
            {
                "dimension": "response_inhibition",
                "outcome": 0.65,
                "weight": 5.0,
                "timestamp": "2026-10-01T10:00:00Z",
            },
            {
                "dimension": "response_inhibition",
                "outcome": 0.78,
                "weight": 5.0,
                "timestamp": "2026-10-02T10:00:00Z",
            },
            {
                "dimension": "response_inhibition",
                "outcome": 0.88,
                "weight": 5.0,
                "timestamp": "2026-10-03T10:00:00Z",
            },
        ],
    }
    progress = compute_goal_progress(
        "Improve focus during homework",
        profile_data,
        target_delta=0.05,
        min_sessions=3,
    )
    assert progress.status == "completed"
    assert progress.status_text == "Target reached"


def test_goals_api_endpoint(tmp_path: pathlib.Path) -> None:
    """GET /v1/assessment/profile/{user_id}/goals checks consent and returns goal tracking."""
    settings = Settings(db_path=str(tmp_path / "test_goals.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "goal_test_user"

    # 1. 403 Forbidden without consent
    res_unauth = client.get(f"/v1/assessment/profile/{user_id}/goals")
    assert res_unauth.status_code == 403

    # 2. Grant consent
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    # 3. Post onboarding experience profile with goals
    res_onboarding = client.put(
        f"/v1/assessment/onboarding/profile/{user_id}",
        json={
            "age_group": "adult_31_60",
            "goals": ["Improve work focus", "Maintain mental sharpness"],
            "tech_comfort": "comfortable",
            "info_style": "detailed",
            "layout": "dashboard",
            "theme": "standard",
        },
    )
    assert res_onboarding.status_code == 200

    # 4. GET goals tracking response
    res = client.get(f"/v1/assessment/profile/{user_id}/goals")
    assert res.status_code == 200
    data = res.json()
    assert data["user_id"] == user_id
    assert "disclaimer" in data
    assert len(data["goals"]) == 2
    for g in data["goals"]:
        assert g["status"] == "insufficient_data"
        assert g["status_text"] == "Not enough data yet"


def test_dashboard_goal_helpers_smoke() -> None:
    """Test dashboard data parsing and render_goal_tracking smoke test."""
    sample_response = {
        "user_id": "u1",
        "goals": [
            {
                "goal": "Improve focus during homework",
                "target_dimensions": ["response_inhibition"],
                "status": "active",
                "status_text": "In progress",
                "n_sessions": 4,
                "baseline": 0.65,
                "current": 0.75,
                "target": 0.75,
                "lower": 0.68,
                "upper": 0.82,
                "progress_ratio": 1.0,
            },
            {
                "goal": "Get better at following instructions",
                "target_dimensions": ["working_memory"],
                "status": "insufficient_data",
                "status_text": "Not enough data yet",
                "n_sessions": 1,
            },
        ],
    }

    display_rows = build_goal_display_data(sample_response)
    assert len(display_rows) == 2
    assert display_rows[0]["status"] == "active"
    assert display_rows[1]["status"] == "insufficient_data"

    # Smoke test rendering with mocked streamlit
    with patch("streamlit.subheader") as mock_sub, patch("streamlit.progress") as mock_prog:
        render_goal_tracking("http://localhost:8000", "u1", goals_data=sample_response)
        assert mock_sub.called
        assert mock_prog.called
