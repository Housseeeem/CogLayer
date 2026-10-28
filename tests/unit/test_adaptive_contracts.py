"""Unit tests for adaptive recommendation contracts in core/models.py."""

from __future__ import annotations

from coglayer.core.models import (
    AdaptiveDailyPlan,
    AdaptiveGameRecommendation,
    AdaptiveRecommendationCriteria,
)


def test_adaptive_recommendation_criteria_and_plan() -> None:
    criteria = AdaptiveRecommendationCriteria(
        user_id="user-123",
        session_id="session-456",
        historical_completeness=0.95,
        target_dimensions=["working_memory", "cognitive_flexibility"],
        target_game_count=3,
        excluded_task_ids=["go_no_go"],
    )
    assert criteria.user_id == "user-123"
    assert criteria.target_game_count == 3
    assert "go_no_go" in criteria.excluded_task_ids

    rec1 = AdaptiveGameRecommendation(
        task_id="digit_span",
        rationale="Targets verbal working memory with lowest credible interval lower bound.",
        target_dimension="working_memory",
        difficulty_level="medium",
    )
    rec2 = AdaptiveGameRecommendation(
        task_id="stroop",
        rationale="Provides cognitive flexibility practice to resolve semantic interference.",
        target_dimension="cognitive_flexibility",
    )
    rec3 = AdaptiveGameRecommendation(
        task_id="corsi_blocks",
        rationale="Strengthens visuospatial memory span.",
        target_dimension="sequential_visual_memory",
    )

    plan = AdaptiveDailyPlan(
        user_id="user-123",
        plan_date="2026-10-25",
        recommendations=[rec1, rec2, rec3],
        deterministic_seed=42,
    )

    assert plan.user_id == "user-123"
    assert len(plan.recommendations) == 3
    assert plan.recommendations[0].task_id == "digit_span"
    assert plan.recommendations[1].task_id == "stroop"
    assert plan.recommendations[2].task_id == "corsi_blocks"
    # Round-trip JSON serialization
    serialized = plan.model_dump_json()
    deserialized = AdaptiveDailyPlan.model_validate_json(serialized)
    assert deserialized.plan_date == "2026-10-25"
    assert len(deserialized.recommendations) == 3
