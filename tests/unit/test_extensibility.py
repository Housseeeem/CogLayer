"""Tests for system extensibility (REQ-002.5, REQ-011 test_ac_extensibility_third_task).

Verifies that adding a third task (descriptor and scoring adapter) does not
require any changes to signals, profile, or coach source code.
"""

from __future__ import annotations

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
