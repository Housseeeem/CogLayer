"""Tests for system extensibility (REQ-002.5, REQ-011 test_ac_extensibility_third_task).

Verifies that adding a third task (descriptor and scoring adapter) does not
require any changes to signals, profile, or coach source code.
"""

from __future__ import annotations

import pathlib

from coglayer.coach.decision import AdaptiveDecisionEngine
from coglayer.core.models import (
    CognitiveProfile,
    DataQuality,
    RawTaskResult,
    TaskDescriptor,
    TaskResult,
)
from coglayer.core.settings import Settings
from coglayer.profile.service import ProfileService
from coglayer.signals.registry import InMemoryTaskRegistry


class DummyThirdTaskScorer:
    """ScoringAdapter for a dummy third task."""

    def score(self, raw: RawTaskResult) -> TaskResult:
        return TaskResult(
            task_id="dummy_task",
            task_version="1.0",
            session_id=str(raw.get("session_id", "s-1")),
            user_id=str(raw.get("user_id", "u-1")),
            trials=[],
            metrics={"dummy_score": 0.85},
            signals=[],
            target_dimensions=["dummy_dimension"],
            data_quality=DataQuality(
                valid_trials=10,
                total_trials=10,
                completeness=1.0,
                anomalies=[],
            ),
            uncertainty=0.1,
        )


def test_ac_extensibility_third_task() -> None:
    """REQ-011 test_ac_extensibility_third_task.

    Registering a dummy third task in a fresh InMemoryTaskRegistry does not
    break the decision engine or the profile service.
    """
    registry = InMemoryTaskRegistry()
    dummy_descriptor = TaskDescriptor(
        task_id="dummy_task",
        version="1.0",
        instructions="Complete the dummy task.",
        target_dimensions=["dummy_dimension"],
        parameters={"trials": 10},
    )
    registry.register(dummy_descriptor)
    assert "dummy_task" in registry.list_ids()
    assert registry.get("dummy_task", "1.0") == dummy_descriptor

    # Instantiate decision engine without modifications
    engine = AdaptiveDecisionEngine()
    settings = Settings()
    # Empty session -> engine still returns "go_no_go" first (protocol order unchanged)
    decision = engine.decide(results=[], settings=settings)
    assert decision.status == "next_task"
    assert decision.next_task == "go_no_go"

    # ProfileService accepts TaskResult for dummy task without raising
    scorer = DummyThirdTaskScorer()
    dummy_result = scorer.score({"session_id": "s-dummy", "user_id": "u-dummy"})

    profile_service = ProfileService()
    profile = CognitiveProfile(
        user_id="u-dummy",
        dimensions={},
        evidence_history=[],
        data_quality={},
        uncertainty={},
    )

    # Since "dummy_task" is not in DIMENSION_MAPPING, update_from_result safely
    # ignores it without raising any exceptions
    updated_profile = profile_service.update_from_result(profile, dummy_result)
    assert isinstance(updated_profile, CognitiveProfile)


class TrivialScorer:
    """Trivial ScoringAdapter for the fake third task."""

    def score(self, raw: RawTaskResult) -> TaskResult:
        raw_val = raw.get("score", 0.85)
        score_val = float(raw_val) if isinstance(raw_val, (int, float, str)) else 0.85
        return TaskResult(
            task_id="fake_pattern_task",
            task_version="1.0",
            session_id=str(raw["session_id"]),
            user_id=str(raw["user_id"]),
            trials=[],
            metrics={"pattern_score": score_val},
            signals=[],
            target_dimensions=["response_inhibition"],
            data_quality=DataQuality(
                valid_trials=10,
                total_trials=10,
                completeness=1.0,
                anomalies=[],
            ),
            uncertainty=0.1,
        )


def test_extensibility_third_task_endpoint_updates_profile(tmp_path: pathlib.Path) -> None:
    """Submit third task through real submit endpoint updates profile for declared dimension.

    Expected derived by hand:
    - fake_pattern_task declares target_dimensions=["response_inhibition"] and metric pattern_score.
    - Score is 0.85.
    - Profile response_inhibition dimension is updated, evidence recorded for pattern_score.
    """
    from fastapi.testclient import TestClient

    from coglayer.api.app import create_app
    from coglayer.api.deps import get_task_registry
    from coglayer.signals.registry import build_default_registry

    db_file = str(tmp_path / "test_ext.db")
    settings = Settings(db_path=db_file)
    app = create_app(settings)

    registry = build_default_registry()
    fake_descriptor = TaskDescriptor(
        task_id="fake_pattern_task",
        version="1.0",
        instructions="Complete the pattern match.",
        target_dimensions=["response_inhibition"],
        primary_metric="pattern_score",
        parameters={"trials": 10},
    )
    scorer = TrivialScorer()
    registry.register(fake_descriptor, scorer=scorer)

    app.dependency_overrides[get_task_registry] = lambda: registry

    client = TestClient(app)
    user_id = "u_third"
    client.post("/v1/assessment/consent", json={"user_id": user_id})
    session_id = client.post("/v1/assessment/sessions", json={"user_id": user_id}).json()[
        "session_id"
    ]

    resp = client.post(
        "/v1/assessment/tasks/fake_pattern_task/submit",
        json={
            "session_id": session_id,
            "user_id": user_id,
            "raw_result": {"score": 0.85},
        },
    )
    assert resp.status_code == 200

    prof_resp = client.get(f"/v1/assessment/profile/{user_id}")
    assert prof_resp.status_code == 200
    profile = prof_resp.json()

    # The profile for response_inhibition must be updated using pattern_score
    assert "response_inhibition" in profile["dimensions"]
    assert profile["dimensions"]["response_inhibition"]["mean"] > 0.5
    evidence_codes = [ev["reason_code"] for ev in profile["evidence_history"]]
    assert "fake_pattern_task:pattern_score" in evidence_codes
