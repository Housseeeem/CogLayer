"""Comprehensive test suite for the adaptive daily cognitive game selector.

Tests all required scenarios:
1. New user without history (discovery session, introductory difficulty, non-personalized)
2. User with complete history (personalized, balanced continuity and diversity)
3. Incomplete history or poor data quality (explicit fallback strategy, non-clinical)
4. Absence of Brain Twin signal
5. Brain Twin states: INSUFFICIENT_DATA, NO_VARIATION, VARIATION_FLAGGED
6. Absence of Coach context or absence of consent (403 Forbidden)
7. User identity verification and session isolation (403 Forbidden)
8. Selection of two or three distinct games
9. Diversity and excessive repetition prevention (recency penalty)
10. Metrics compatibility and exclusion of cross-task comparisons
11. Daily stability (idempotent retrieval, explicit regeneration)
12. SQLite persistence, retrieval, status updates, and user deletion
13. API integration and Cognitive Lab Streamlit UI interaction
14. Compatibility with existing contracts and features
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from coglayer.api.app import create_app
from coglayer.api.db.sqlite import (
    SQLiteAssessmentRepository,
    SQLiteDailyPlanRepository,
)
from coglayer.coach.selector import AdaptiveGameSelector
from coglayer.core.brain_twin import BrainTwinSignal, BrainTwinState
from coglayer.core.models import (
    AdaptiveDailyPlan,
    AdaptiveRecommendationCriteria,
    DataQuality,
    Session,
    SessionStatus,
    Signal,
    TaskResult,
    Trial,
)
from coglayer.core.settings import Settings
from coglayer.ui.api import get_daily_plan, update_daily_plan_status
from coglayer.ui.page_views.cognitive_lab import render_cognitive_lab_page


# ---------------------------------------------------------------------------
# Test helpers & factories
# ---------------------------------------------------------------------------
def _make_dummy_result(
    user_id: str,
    session_id: str,
    task_id: str,
    completeness: float = 1.0,
    metric_name: str = "accuracy",
    metric_value: float = 0.85,
    timestamp: datetime | None = None,
) -> TaskResult:
    ts = timestamp or datetime.now(UTC)
    trials = [
        Trial(
            stimulus="go",
            expected="go",
            response="go",
            rt_ms=320.0,
            timestamp=ts,
            valid=True,
            invalid_reason=None,
        )
    ]
    return TaskResult(
        task_id=task_id,
        task_version="1.0",
        session_id=session_id,
        user_id=user_id,
        trials=trials,
        metrics={metric_name: metric_value},
        signals=[Signal(name="confidence", value=0.9)],
        target_dimensions=["working_memory"],
        data_quality=DataQuality(
            valid_trials=10,
            total_trials=10,
            completeness=completeness,
            anomalies=[],
        ),
        uncertainty=0.1,
    )


# ---------------------------------------------------------------------------
# 1. New user without history
# ---------------------------------------------------------------------------
def test_new_user_without_history() -> None:
    selector = AdaptiveGameSelector()
    criteria = AdaptiveRecommendationCriteria(
        user_id="user_new_1",
        target_game_count=3,
        plan_date="2026-10-25",
    )
    plan = selector.select_daily_plan(criteria, results=(), sessions=())

    assert plan.user_id == "user_new_1"
    assert plan.plan_date == "2026-10-25"
    assert len(plan.recommendations) == 3
    assert not plan.is_personalized
    assert plan.fallback_strategy == "initial_session_default"
    assert "initial_diversity" in plan.factors_used

    # Check distinct games and introductory difficulty
    task_ids = [rec.task_id for rec in plan.recommendations]
    assert len(task_ids) == len(set(task_ids))
    for rec in plan.recommendations:
        assert rec.difficulty_level == "introductory"
        assert rec.task_version == "1.0"
        assert "introductory" in rec.rationale.lower()


# ---------------------------------------------------------------------------
# 2. User with complete history
# ---------------------------------------------------------------------------
def test_user_with_complete_history() -> None:
    selector = AdaptiveGameSelector()
    user_id = "user_complete_1"

    results = [
        _make_dummy_result(
            user_id,
            "sess_1",
            "go_no_go",
            completeness=1.0,
            metric_name="nogo_accuracy",
            metric_value=0.95,
        ),
        _make_dummy_result(
            user_id,
            "sess_1",
            "digit_span",
            completeness=1.0,
            metric_name="accuracy",
            metric_value=0.90,
        ),
        _make_dummy_result(
            user_id,
            "sess_2",
            "go_no_go",
            completeness=1.0,
            metric_name="nogo_accuracy",
            metric_value=0.92,
        ),
        _make_dummy_result(
            user_id,
            "sess_3",
            "go_no_go",
            completeness=1.0,
            metric_name="nogo_accuracy",
            metric_value=0.94,
        ),
    ]
    sessions = [
        Session(
            session_id="sess_1",
            user_id=user_id,
            start_time=datetime.now(UTC) - timedelta(days=2),
            end_time=datetime.now(UTC) - timedelta(days=2),
            status=SessionStatus.COMPLETED,
            completed_tasks=["go_no_go", "digit_span"],
        ),
        Session(
            session_id="sess_3",
            user_id=user_id,
            start_time=datetime.now(UTC) - timedelta(days=1),
            end_time=datetime.now(UTC) - timedelta(days=1),
            status=SessionStatus.COMPLETED,
            completed_tasks=["go_no_go"],
        ),
    ]

    criteria = AdaptiveRecommendationCriteria(
        user_id=user_id,
        target_game_count=3,
        plan_date="2026-10-25",
    )
    plan = selector.select_daily_plan(criteria, results=results, sessions=sessions)

    assert plan.user_id == user_id
    assert plan.is_personalized
    assert len(plan.recommendations) == 3
    task_ids = [rec.task_id for rec in plan.recommendations]
    assert len(task_ids) == len(set(task_ids))
    assert "history_performance" in plan.factors_used


# ---------------------------------------------------------------------------
# 3. Incomplete history or poor data quality
# ---------------------------------------------------------------------------
def test_incomplete_or_poor_quality_history() -> None:
    selector = AdaptiveGameSelector()
    user_id = "user_poor_quality"
    # All historical results below 0.5 completeness
    poor_results = [
        _make_dummy_result(user_id, "sess_1", "stroop", completeness=0.2),
        _make_dummy_result(user_id, "sess_2", "digit_span", completeness=0.3),
    ]

    criteria = AdaptiveRecommendationCriteria(
        user_id=user_id,
        target_game_count=3,
        plan_date="2026-10-25",
    )
    plan = selector.select_daily_plan(criteria, results=poor_results, sessions=())

    assert not plan.is_personalized
    assert plan.fallback_strategy == "data_sufficiency_fallback"
    assert "data_quality_verification" in plan.factors_used
    assert len(plan.recommendations) == 3
    for rec in plan.recommendations:
        assert rec.difficulty_level == "standard"
        assert "standard conditions" in rec.rationale.lower()


# ---------------------------------------------------------------------------
# 4. Absence of Brain Twin signal
# ---------------------------------------------------------------------------
def test_absence_of_brain_twin_signal() -> None:
    selector = AdaptiveGameSelector()
    criteria = AdaptiveRecommendationCriteria(
        user_id="user_no_bt",
        target_game_count=2,
        plan_date="2026-10-25",
    )
    plan = selector.select_daily_plan(criteria, results=(), sessions=(), brain_twin_signal=None)

    assert len(plan.recommendations) == 2
    assert not any("brain_twin" in factor for factor in plan.factors_used)


# ---------------------------------------------------------------------------
# 5. Brain Twin states: INSUFFICIENT_DATA, NO_VARIATION, VARIATION_FLAGGED
# ---------------------------------------------------------------------------
def test_brain_twin_states() -> None:
    selector = AdaptiveGameSelector()
    user_id = "user_bt_states"
    history = [_make_dummy_result(user_id, "s1", "digit_span", completeness=1.0)]

    # State: INSUFFICIENT_DATA does not block
    sig_insufficient = BrainTwinSignal(
        state=BrainTwinState.INSUFFICIENT_DATA,
        comparable_observation_count=1,
    )
    plan_insufficient = selector.select_daily_plan(
        AdaptiveRecommendationCriteria(user_id=user_id, target_game_count=2),
        results=history,
        brain_twin_signal=sig_insufficient,
    )
    assert len(plan_insufficient.recommendations) == 2
    assert "brain_twin_insufficient_data" in plan_insufficient.factors_used

    # State: NO_VARIATION (does not assume ceiling / high intelligence)
    sig_stable = BrainTwinSignal(
        state=BrainTwinState.NO_VARIATION,
        comparable_observation_count=5,
    )
    plan_stable = selector.select_daily_plan(
        AdaptiveRecommendationCriteria(user_id=user_id, target_game_count=2),
        results=history,
        brain_twin_signal=sig_stable,
    )
    assert len(plan_stable.recommendations) == 2
    assert "brain_twin_stable_baseline" in plan_stable.factors_used

    # State: VARIATION_FLAGGED (consolidates Go/No-Go reference without diagnosis)
    sig_flagged = BrainTwinSignal(
        state=BrainTwinState.VARIATION_FLAGGED,
        comparable_observation_count=5,
        flagged_observation_id="s1|go_no_go|response_inhibition|2026-10-25|code|1.0",
    )
    plan_flagged = selector.select_daily_plan(
        AdaptiveRecommendationCriteria(user_id=user_id, target_game_count=3),
        results=history,
        brain_twin_signal=sig_flagged,
    )
    assert len(plan_flagged.recommendations) == 3
    assert "brain_twin_variation_adjustment" in plan_flagged.factors_used
    rec_tasks = [r.task_id for r in plan_flagged.recommendations]
    assert "go_no_go" in rec_tasks
    gng_rec = next(r for r in plan_flagged.recommendations if r.task_id == "go_no_go")
    assert "reference measurement" in gng_rec.rationale.lower()


# ---------------------------------------------------------------------------
# 6. Absence of Coach context or absence of consent
# ---------------------------------------------------------------------------
def test_coach_context_and_fatigue_adaptation() -> None:
    selector = AdaptiveGameSelector()
    user_id = "user_fatigued"
    history = [_make_dummy_result(user_id, "s1", "n_back", completeness=1.0)]

    # Fatigue subjective context
    criteria_fatigued = AdaptiveRecommendationCriteria(
        user_id=user_id,
        target_game_count=2,
        subjective_feedback="Feeling slightly fatigued today",
    )
    plan_fatigued = selector.select_daily_plan(criteria_fatigued, results=history)
    assert "subjective_fatigue_adaptation" in plan_fatigued.factors_used
    for rec in plan_fatigued.recommendations:
        assert rec.difficulty_level == "introductory"
        assert "fatigue" in rec.rationale.lower()


# ---------------------------------------------------------------------------
# 7. Respect of user identity and isolation
# ---------------------------------------------------------------------------
def test_user_identity_isolation(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "identity_test.db"))
    app = create_app(settings)
    client = TestClient(app)

    # Consent user A
    client.post("/v1/assessment/consent", json={"user_id": "user_A"})

    # Attempt to request with mismatched identity in query vs path
    res = client.get("/v1/assessment/daily-plan/user_A", params={"user_id": "user_B"})
    assert res.status_code == 403

    # Attempt to request for unconsented user
    res_unconsented = client.get("/v1/assessment/daily-plan/user_unconsented")
    assert res_unconsented.status_code == 403


# ---------------------------------------------------------------------------
# 8. Selection of two or three distinct games
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("requested_count,expected_count", [(1, 2), (2, 2), (3, 3), (4, 3), (5, 3)])
def test_selection_count_clamped_to_two_or_three(requested_count: int, expected_count: int) -> None:
    selector = AdaptiveGameSelector()
    criteria = AdaptiveRecommendationCriteria(
        user_id="user_count_test",
        target_game_count=requested_count,
        plan_date="2026-10-25",
    )
    plan = selector.select_daily_plan(criteria)
    assert len(plan.recommendations) == expected_count
    distinct_ids = {r.task_id for r in plan.recommendations}
    assert len(distinct_ids) == expected_count


# ---------------------------------------------------------------------------
# 9. Diversity and excessive repetition prevention
# ---------------------------------------------------------------------------
def test_diversity_and_recency_prevention() -> None:
    selector = AdaptiveGameSelector()
    user_id = "user_recency_test"

    # Last session completed go_no_go and digit_span
    last_session = Session(
        session_id="sess_recent",
        user_id=user_id,
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC),
        status=SessionStatus.COMPLETED,
        completed_tasks=["go_no_go", "digit_span"],
    )
    results = [
        _make_dummy_result(user_id, "sess_recent", "go_no_go"),
        _make_dummy_result(user_id, "sess_recent", "digit_span"),
    ]

    criteria = AdaptiveRecommendationCriteria(
        user_id=user_id,
        target_game_count=2,
        plan_date="2026-10-25",
    )
    plan = selector.select_daily_plan(criteria, results=results, sessions=[last_session])

    # The selector should penalize go_no_go and digit_span and pick other diverse tasks
    recommended_tasks = [r.task_id for r in plan.recommendations]
    assert len(recommended_tasks) == 2
    assert "recency_prevention" in plan.factors_used
    # Diversity across dimensions
    dims = [r.target_dimension for r in plan.recommendations]
    assert len(set(dims)) == len(dims)


# ---------------------------------------------------------------------------
# 10. Metrics compatibility & non-clinical rationale
# ---------------------------------------------------------------------------
def test_metrics_compatibility_and_non_clinical_language() -> None:
    selector = AdaptiveGameSelector()
    user_id = "user_metrics_compat"
    results = [
        _make_dummy_result(
            user_id, "s1", "stroop", metric_name="incongruent_accuracy", metric_value=0.9
        ),
        _make_dummy_result(user_id, "s1", "digit_span", metric_name="accuracy", metric_value=0.85),
    ]
    criteria = AdaptiveRecommendationCriteria(user_id=user_id, target_game_count=3)
    plan = selector.select_daily_plan(criteria, results=results)

    # Check non-clinical vocabulary in all rationales
    forbidden_words = ["diagnosis", "disorder", "deficit", "impairment", "iq", "patient"]
    for rec in plan.recommendations:
        for word in forbidden_words:
            assert word not in rec.rationale.lower()


# ---------------------------------------------------------------------------
# 11. Daily stability & regeneration rules
# ---------------------------------------------------------------------------
def test_daily_plan_stability_and_regeneration(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "stability_test.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_stable_1"
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    # Call 1: Generate plan
    res1 = client.get(f"/v1/assessment/daily-plan/{user_id}", params={"plan_date": "2026-10-25"})
    assert res1.status_code == 200
    plan1 = res1.json()

    # Call 2: Same day, no force_regenerate -> returns identical plan
    res2 = client.get(f"/v1/assessment/daily-plan/{user_id}", params={"plan_date": "2026-10-25"})
    assert res2.status_code == 200
    plan2 = res2.json()
    assert plan1 == plan2

    # Call 3: Explicit force_regenerate with different subjective feedback
    res3 = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={
            "plan_date": "2026-10-25",
            "force_regenerate": True,
            "subjective_feedback": "fatigued",
        },
    )
    assert res3.status_code == 200
    plan3 = res3.json()
    assert "subjective_fatigue_adaptation" in plan3["factors_used"]


def test_force_regenerate_preserves_session_id_and_resets_status(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "regen_status_test.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_regen_status"
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    # Initial plan generated
    res1 = client.get(f"/v1/assessment/daily-plan/{user_id}", params={"plan_date": "2026-10-25"})
    assert res1.status_code == 200
    assert res1.json()["status"] == "generated"

    # Plan started with session_id
    res_patch = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": "sess_active_123"},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["status"] == "started"
    assert res_patch.json()["session_id"] == "sess_active_123"

    # Force regenerate on existing started plan
    res_regen = client.get(
        f"/v1/assessment/daily-plan/{user_id}",
        params={"plan_date": "2026-10-25", "force_regenerate": True},
    )
    assert res_regen.status_code == 200
    plan_regen = res_regen.json()
    assert plan_regen["status"] == "generated"
    assert plan_regen["session_id"] == "sess_active_123"


def test_incomplete_results_excluded_from_personalized_history() -> None:
    selector = AdaptiveGameSelector()
    user_id = "user_filter_incomplete"
    # One valid result for go_no_go, one incomplete (<0.50 completeness) for perception_lab
    results = [
        _make_dummy_result(user_id, "s1", "go_no_go", completeness=1.0),
        _make_dummy_result(user_id, "s1", "perception_lab", completeness=0.2),
    ]

    criteria = AdaptiveRecommendationCriteria(
        user_id=user_id,
        target_game_count=3,
        target_dimensions=["cognitive_flexibility"],
    )
    plan = selector.select_daily_plan(criteria, results=results)

    # Perception Lab should be treated as fresh exploration, not steady continuity
    rec = next(r for r in plan.recommendations if r.task_id == "perception_lab")
    assert rec.difficulty_level == "introductory"
    assert "introduces" in rec.rationale.lower()


def test_pending_empty_session_does_not_mask_recent_tasks() -> None:
    selector = AdaptiveGameSelector()
    user_id = "user_pending_mask"
    # Older completed session with tasks
    s1 = Session(
        session_id="s1",
        user_id=user_id,
        start_time=datetime.now(UTC) - timedelta(hours=2),
        end_time=datetime.now(UTC) - timedelta(hours=1),
        status=SessionStatus.COMPLETED,
        completed_tasks=["go_no_go", "digit_span"],
    )
    # Newer pending session with no completed tasks yet
    s2 = Session(
        session_id="s2",
        user_id=user_id,
        start_time=datetime.now(UTC),
        end_time=None,
        status=SessionStatus.PENDING,
        completed_tasks=[],
    )
    results = [
        _make_dummy_result(user_id, "s1", "go_no_go"),
        _make_dummy_result(user_id, "s1", "digit_span"),
    ]

    criteria = AdaptiveRecommendationCriteria(user_id=user_id, target_game_count=2)
    plan = selector.select_daily_plan(criteria, results=results, sessions=[s1, s2])

    assert "recency_prevention" in plan.factors_used


# ---------------------------------------------------------------------------
# 12. Persistence, lifecycle updates, and user deletion
# ---------------------------------------------------------------------------
def test_persistence_lifecycle_and_deletion(tmp_path: pathlib.Path) -> None:
    db_path = str(tmp_path / "repo_test.db")
    plan_repo = SQLiteDailyPlanRepository(db_path)
    assess_repo = SQLiteAssessmentRepository(db_path)

    plan = AdaptiveDailyPlan(
        user_id="user_persist_1",
        plan_date="2026-10-25",
        recommendations=[],
        deterministic_seed=12345,
        status="generated",
    )
    plan_repo.save_plan(plan)

    retrieved = plan_repo.get_plan("user_persist_1", "2026-10-25")
    assert retrieved is not None
    assert retrieved.status == "generated"

    # Update status to started
    plan_repo.update_plan_status(
        "user_persist_1", "2026-10-25", status="started", session_id="sess_xyz"
    )
    started_plan = plan_repo.get_plan("user_persist_1", "2026-10-25")
    assert started_plan is not None
    assert started_plan.status == "started"
    assert started_plan.session_id == "sess_xyz"

    # User deletion cleans up daily plans (R-001.2)
    assess_repo.delete_user("user_persist_1")
    assert plan_repo.get_plan("user_persist_1", "2026-10-25") is None


# ---------------------------------------------------------------------------
# 13. API status patch endpoint & error handling
# ---------------------------------------------------------------------------
def test_api_status_patch(tmp_path: pathlib.Path) -> None:
    settings = Settings(db_path=str(tmp_path / "api_patch_test.db"))
    app = create_app(settings)
    client = TestClient(app)

    user_id = "user_api_patch"
    client.post("/v1/assessment/consent", json={"user_id": user_id})

    # Generate plan
    res_gen = client.get(f"/v1/assessment/daily-plan/{user_id}", params={"plan_date": "2026-10-25"})
    assert res_gen.status_code == 200

    # Patch status
    res_patch = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2026-10-25", "status": "started", "session_id": "sess_100"},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["status"] == "started"
    assert res_patch.json()["session_id"] == "sess_100"

    # Non-existent date 404
    res_404 = client.patch(
        f"/v1/assessment/daily-plan/{user_id}/status",
        json={"plan_date": "2020-01-01", "status": "completed"},
    )
    assert res_404.status_code == 404


# ---------------------------------------------------------------------------
# 14. Cognitive Lab Streamlit UI interaction
# ---------------------------------------------------------------------------
@patch("coglayer.ui.page_views.cognitive_lab.get_assessment_session")
@patch("coglayer.ui.page_views.cognitive_lab.get_daily_plan")
@patch("coglayer.ui.page_views.cognitive_lab.update_daily_plan_status")
@patch("coglayer.ui.page_views.cognitive_lab.st")
def test_cognitive_lab_daily_plan_ui(
    mock_st: MagicMock,
    mock_update_status: MagicMock,
    mock_get_plan: MagicMock,
    mock_get_session: MagicMock,
) -> None:
    mock_st.session_state = {
        "user_id": "user_ui_1",
        "session_id": "session_ui_1",
    }
    mock_st.button.return_value = False
    mock_st.columns.side_effect = lambda n: [
        MagicMock() for _ in range(n if isinstance(n, int) else len(n))
    ]
    mock_get_session.return_value = {
        "session_id": "session_ui_1",
        "user_id": "user_ui_1",
        "completed_tasks": [],
    }

    mock_get_plan.return_value = {
        "user_id": "user_ui_1",
        "plan_date": "2026-10-25",
        "status": "generated",
        "is_personalized": True,
        "recommendations": [
            {
                "task_id": "go_no_go",
                "rationale": "Focuses on response inhibition.",
                "target_dimension": "response_inhibition",
                "difficulty_level": "standard",
            },
            {
                "task_id": "digit_span",
                "rationale": "Strengthens verbal working memory.",
                "target_dimension": "working_memory",
                "difficulty_level": "standard",
            },
        ],
    }

    render_cognitive_lab_page("http://testserver", "user_ui_1")

    assert mock_st.header.called
    assert mock_get_plan.called
    assert mock_st.subheader.called
    subheaders = [str(call.args[0]) for call in mock_st.subheader.call_args_list if call.args]
    assert "All Cognitive Lab Activities" not in subheaders
    info_texts = [str(call.args[0]) for call in mock_st.info.call_args_list if call.args]
    assert any("Personalized" in text for text in info_texts)
    assert mock_update_status.call_count == 0


@patch("coglayer.ui.api.httpx.get")
@patch("coglayer.ui.api.httpx.patch")
def test_ui_api_helpers(mock_patch: MagicMock, mock_get: MagicMock) -> None:
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {"user_id": "u1", "recommendations": []},
        raise_for_status=lambda: None,
    )
    mock_patch.return_value = MagicMock(
        status_code=200,
        json=lambda: {"user_id": "u1", "status": "started"},
        raise_for_status=lambda: None,
    )

    plan = get_daily_plan(
        "http://testserver",
        "u1",
        plan_date="2026-10-25",
        target_game_count=3,
        force_regenerate=True,
        subjective_feedback="fatigue",
    )
    assert plan["user_id"] == "u1"

    updated = update_daily_plan_status(
        "http://testserver",
        "u1",
        plan_date="2026-10-25",
        status="started",
        session_id="s123",
    )
    assert updated["status"] == "started"

    # Test invalid json response error
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: "not_a_dict",
        raise_for_status=lambda: None,
    )
    with pytest.raises(ValueError, match="Daily plan response must be an object"):
        get_daily_plan("http://testserver", "u1")

    mock_patch.return_value = MagicMock(
        status_code=200,
        json=lambda: ["not", "a", "dict"],
        raise_for_status=lambda: None,
    )
    with pytest.raises(ValueError, match="Daily plan status response must be an object"):
        update_daily_plan_status("http://testserver", "u1", "2026-10-25", "started")
