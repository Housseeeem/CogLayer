"""Unit and integration tests for guidance_level adaptation in the game selector.

Tests verify:
- guidance_level == MORE: fewer games per day (2), simpler tasks first.
- guidance_level == SOME: standard behavior (3 games, balanced).
- guidance_level == MINIMAL: more autonomy (3 games, allows challenge difficulty).
- API endpoint /daily-plan/{user_id} takes guidance_level from ExperienceProfile.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.api.db.sqlite import (
    SQLiteAssessmentRepository,
    SQLiteConsentRepository,
    SQLiteExperienceProfileRepository,
)
from coglayer.coach.selector import AdaptiveGameSelector
from coglayer.core.models import (
    AdaptiveRecommendationCriteria,
    AgeGroup,
    ConsentRecord,
    DataQuality,
    ExperienceProfile,
    GuidanceLevel,
    InfoStyle,
    LayoutType,
    Session,
    SessionStatus,
    TaskResult,
    TechComfort,
    ThemeType,
)
from coglayer.core.settings import Settings


def _create_mock_history(
    user_id: str,
    tasks: list[str],
) -> tuple[list[Session], list[TaskResult]]:
    """Create sample session and task results for testing selector."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    sessions: list[Session] = []
    results: list[TaskResult] = []
    for i in range(3):
        sess_id = f"sess_{user_id}_{i}"
        sess_time = now - timedelta(days=2 - i)
        # Most recent session (i=2) only completed one task to allow recency rotation
        completed = ["stroop"] if i == 2 else tasks
        session = Session(
            session_id=sess_id,
            user_id=user_id,
            start_time=sess_time,
            end_time=sess_time,
            status=SessionStatus.COMPLETED,
            completed_tasks=completed,
        )
        sessions.append(session)
        for task_id in tasks:
            results.append(
                TaskResult(
                    task_id=task_id,
                    task_version="1.0",
                    session_id=sess_id,
                    user_id=user_id,
                    trials=[],
                    metrics={},
                    signals=[],
                    target_dimensions=[],
                    data_quality=DataQuality(
                        valid_trials=10,
                        total_trials=10,
                        completeness=0.95,
                        anomalies=[],
                    ),
                    uncertainty=None,
                )
            )
    return sessions, results


def test_guidance_level_more_selects_two_games_and_simpler_first() -> None:
    """GuidanceLevel.MORE recommends 2 games and puts simpler tasks first."""
    selector = AdaptiveGameSelector()
    criteria = AdaptiveRecommendationCriteria(
        user_id="user_more",
        guidance_level=GuidanceLevel.MORE,
        target_game_count=3,
    )
    sessions, results = _create_mock_history("user_more", ["stroop", "n_back", "go_no_go"])

    plan = selector.select_daily_plan(criteria, results=results, sessions=sessions)

    assert len(plan.recommendations) == 2, "MORE guidance must recommend fewer games (2)"
    assert "guidance_scaffolding_more" in plan.factors_used
    # First task should be the simpler/shorter task (e.g. go_no_go)
    assert plan.recommendations[0].task_id in ("go_no_go", "digit_span")
    # All tasks have introductory difficulty
    for rec in plan.recommendations:
        assert rec.difficulty_level == "introductory"


def test_guidance_level_some_standard_behavior() -> None:
    """GuidanceLevel.SOME retains standard count and balanced scaffolding."""
    selector = AdaptiveGameSelector()
    criteria = AdaptiveRecommendationCriteria(
        user_id="user_some",
        guidance_level=GuidanceLevel.SOME,
        target_game_count=3,
    )
    sessions, results = _create_mock_history("user_some", ["stroop", "n_back", "go_no_go"])

    plan = selector.select_daily_plan(criteria, results=results, sessions=sessions)

    assert len(plan.recommendations) == 3
    assert "guidance_balanced_some" in plan.factors_used


def test_guidance_level_minimal_allows_challenge() -> None:
    """GuidanceLevel.MINIMAL offers autonomy and challenge difficulty when qualified."""
    selector = AdaptiveGameSelector()
    criteria = AdaptiveRecommendationCriteria(
        user_id="user_min",
        guidance_level=GuidanceLevel.MINIMAL,
        target_game_count=3,
    )
    sessions, results = _create_mock_history("user_min", ["stroop", "n_back", "go_no_go"])

    plan = selector.select_daily_plan(criteria, results=results, sessions=sessions)

    assert len(plan.recommendations) == 3
    assert "guidance_autonomy_minimal" in plan.factors_used
    # Should contain at least one challenge difficulty task since user has high completeness history
    difficulties = {rec.difficulty_level for rec in plan.recommendations}
    assert "challenge" in difficulties


def test_daily_plan_api_integrates_guidance_level(tmp_path: Path) -> None:
    """GET /daily-plan/{user_id} automatically uses guidance_level from ExperienceProfile."""
    from datetime import UTC, datetime

    db_path = str(tmp_path / "guidance_api_test.db")
    settings = Settings(db_path=db_path)
    now = datetime.now(UTC)

    # Setup user with MORE guidance
    user_id = "user_guided"
    consent_repo = SQLiteConsentRepository(db_path)
    consent_repo.save_consent(ConsentRecord(user_id=user_id, consented_at=now))

    exp_repo = SQLiteExperienceProfileRepository(db_path)
    exp_repo.save_profile(
        ExperienceProfile(
            user_id=user_id,
            age_group=AgeGroup.ADULT_31_60,
            goals=["improve_focus"],
            tech_comfort=TechComfort.COMFORTABLE,
            info_style=InfoStyle.CONVERSATIONAL,
            layout=LayoutType.GUIDED_JOURNEY,
            theme=ThemeType.STANDARD,
            guidance_level=GuidanceLevel.MORE,
        )
    )

    assess_repo = SQLiteAssessmentRepository(db_path)
    sessions, results = _create_mock_history(user_id, ["stroop", "n_back", "go_no_go"])
    for s in sessions:
        assess_repo.save_session(s)
    for r in results:
        assess_repo.save_result(r)

    app = create_app(settings)
    client = TestClient(app)

    resp = client.get(f"/v1/assessment/daily-plan/{user_id}?user_id={user_id}")
    assert resp.status_code == 200
    plan = resp.json()

    assert len(plan["recommendations"]) == 2
    assert "guidance_scaffolding_more" in plan["factors_used"]
    assert plan["recommendations"][0]["task_id"] in ("go_no_go", "digit_span")
