"""Daily adaptive game recommendation router for CogLayer assessment API.

Endpoints:
- GET /daily-plan/{user_id}: get or generate daily cognitive game plan
- PATCH /daily-plan/{user_id}/status: update daily plan lifecycle status

Status lifecycle:
- generated: plan created, no activity started.
- started: at least one recommended activity started, plan not yet complete.
- completed: all recommended activities finished (verified against session data).

Allowed transitions via PATCH:
    generated → started
    started   → started   (idempotent)
    started   → completed (only when all tasks verified)
    completed → completed (idempotent)
All other transitions are rejected with HTTP 409.
Force-regeneration is a separate GET operation, not a PATCH.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, field_validator

from coglayer.api.deps import (
    get_assessment_repo,
    get_consent_service,
    get_daily_plan_repo,
    get_daily_selector,
    get_profile_repo,
)
from coglayer.coach.selector import AdaptiveGameSelector
from coglayer.core.brain_twin import build_brain_twin_signal
from coglayer.core.models import (
    AdaptiveDailyPlan,
    AdaptiveRecommendationCriteria,
)
from coglayer.core.protocols import (
    AssessmentRepository,
    DailyPlanRepository,
    ProfileRepository,
)
from coglayer.privacy.consent import ConsentService

router = APIRouter(tags=["daily-plan"])
logger = logging.getLogger(__name__)

# Valid status transitions for daily plans.
# Key is the current status, value is the set of allowed target statuses.
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "generated": {"generated", "started"},
    "started": {"started", "completed"},
    "completed": {"completed"},
}


class DailyPlanStatusUpdateRequest(BaseModel):
    """Payload to update daily plan status."""

    plan_date: str
    status: Literal["generated", "started", "completed"]
    session_id: str | None = None

    @field_validator("plan_date")
    @classmethod
    def _validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"plan_date must be in YYYY-MM-DD format, got {v!r}") from e
        return v


def _get_verified_completed_task_ids(
    plan: AdaptiveDailyPlan,
    assessment_repo: AssessmentRepository,
) -> set[str]:
    """Return the set of recommended task IDs with valid persisted results in the plan's session.

    Guarantees:
    - The plan has a session_id.
    - The session exists and belongs to plan.user_id.
    - Result exists in assessment_repo for (session_id, task_id).
    - Result belongs to session_id and plan.user_id.
    - Result has valid_trials > 0.
    """
    if not plan.session_id or not plan.recommendations:
        return set()
    session = assessment_repo.get_session(plan.session_id)
    if session is None or session.user_id != plan.user_id:
        return set()

    results = assessment_repo.get_results(plan.session_id)
    required_ids = {rec.task_id for rec in plan.recommendations}
    return {
        res.task_id
        for res in results
        if res.task_id in required_ids
        and res.session_id == plan.session_id
        and res.user_id == plan.user_id
        and res.data_quality.is_sufficient_for_completion()
    }


def _check_plan_completion(
    plan: AdaptiveDailyPlan,
    assessment_repo: AssessmentRepository,
) -> bool:
    """Return True if all recommended tasks have valid persisted results in the plan's session.

    Returns False when the plan has no session_id, no recommendations, the session
    cannot be found, does not belong to the user, or results are missing/invalid.
    """
    if not plan.recommendations:
        return False
    required_ids = {rec.task_id for rec in plan.recommendations}
    verified_ids = _get_verified_completed_task_ids(plan, assessment_repo)
    return required_ids.issubset(verified_ids)


def _reconcile_plan_status(
    plan: AdaptiveDailyPlan,
    daily_plan_repo: DailyPlanRepository,
    assessment_repo: AssessmentRepository,
) -> AdaptiveDailyPlan:
    """Reconcile a plan's status against actual session completion data.

    Read-repair: if the stored status is stale (e.g. started but all tasks are
    done), update the persisted plan and return the corrected version.
    """
    if plan.status == "completed":
        return plan
    if not plan.session_id:
        return plan

    session = assessment_repo.get_session(plan.session_id)
    if session is None or session.user_id != plan.user_id:
        return plan

    required_ids = {rec.task_id for rec in plan.recommendations}
    if not required_ids:
        return plan

    verified_ids = _get_verified_completed_task_ids(plan, assessment_repo)

    new_status: Literal["generated", "started", "completed"] = plan.status
    if required_ids.issubset(verified_ids):
        new_status = "completed"
    elif plan.status == "generated" and (required_ids & verified_ids):
        new_status = "started"

    if new_status != plan.status:
        daily_plan_repo.update_plan_status(
            user_id=plan.user_id,
            plan_date=plan.plan_date,
            status=new_status,
            session_id=plan.session_id,
        )
        refreshed = daily_plan_repo.get_plan(plan.user_id, plan.plan_date)
        if refreshed is not None:
            return refreshed
    return plan


@router.get(
    "/daily-plan/{user_id}",
    response_model=AdaptiveDailyPlan,
    status_code=status.HTTP_200_OK,
)
def get_daily_plan(
    user_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    daily_plan_repo: Annotated[DailyPlanRepository, Depends(get_daily_plan_repo)],
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    daily_selector: Annotated[AdaptiveGameSelector, Depends(get_daily_selector)],
    request: Request,
    plan_date: str | None = Query(default=None),
    target_game_count: int = Query(default=3, ge=2, le=3),
    force_regenerate: bool = Query(default=False),
    subjective_feedback: str | None = Query(default=None),
) -> AdaptiveDailyPlan:
    """Retrieve or generate the daily cognitive game plan for a user.

    Enforces active consent and user identity. Preserves stability across calls
    on the same day unless force_regenerate is explicitly True.

    On retrieval of an existing plan, reconciles the status against actual
    session completion data (read-repair).
    """
    req_identity = request.query_params.get("user_id")
    if req_identity is not None and req_identity != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden for this user.",
        )

    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )

    if plan_date is not None:
        try:
            datetime.strptime(plan_date, "%Y-%m-%d")
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="plan_date must be in YYYY-MM-DD format.",
            ) from e

    effective_date = plan_date or datetime.now(UTC).strftime("%Y-%m-%d")

    # Idempotent retrieval for daily stability
    existing_plan = daily_plan_repo.get_plan(user_id, effective_date)
    if not force_regenerate and existing_plan is not None:
        return _reconcile_plan_status(existing_plan, daily_plan_repo, assessment_repo)

    # Context collection
    sessions = assessment_repo.get_sessions_by_user(user_id)
    all_results = [
        result for session in sessions for result in assessment_repo.get_results(session.session_id)
    ]

    profile = profile_repo.get_profile(user_id)
    evidence = profile.evidence_history if profile is not None else []
    brain_twin_signal = build_brain_twin_signal(evidence)

    # Determine session_id for the plan:
    # If force_regenerate is True:
    # - If plan was completed OR if session already has submitted results, do NOT reuse
    #   the session (prevents phantom completion and HTTP 409 duplicate submission errors).
    # - If plan was started but has NO submitted results yet, preserve session_id (unless foreign).
    # Otherwise, preserve session_id (unless foreign).
    session_to_link: str | None = None
    if existing_plan is not None and existing_plan.session_id:
        existing_session = assessment_repo.get_session(existing_plan.session_id)
        is_foreign = existing_session is not None and existing_session.user_id != user_id
        if not is_foreign:
            if force_regenerate:
                has_existing_results = bool(assessment_repo.get_results(existing_plan.session_id))
                if existing_plan.status != "completed" and not has_existing_results:
                    session_to_link = existing_plan.session_id
            else:
                session_to_link = existing_plan.session_id

    criteria = AdaptiveRecommendationCriteria(
        user_id=user_id,
        session_id=session_to_link,
        plan_date=effective_date,
        target_game_count=target_game_count,
        subjective_feedback=subjective_feedback,
    )

    plan = daily_selector.select_daily_plan(
        criteria=criteria,
        results=all_results,
        sessions=sessions,
        brain_twin_signal=brain_twin_signal,
    )

    daily_plan_repo.save_plan(plan)
    return plan


@router.patch(
    "/daily-plan/{user_id}/status",
    response_model=AdaptiveDailyPlan,
    status_code=status.HTTP_200_OK,
)
def update_daily_plan_status(
    user_id: str,
    body: DailyPlanStatusUpdateRequest,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    daily_plan_repo: Annotated[DailyPlanRepository, Depends(get_daily_plan_repo)],
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    request: Request,
) -> AdaptiveDailyPlan:
    """Update the lifecycle status of a daily plan.

    Validates transitions against the allowed transition map.
    Rejects invalid transitions with HTTP 409 Conflict.
    Transitioning to 'completed' requires all recommended tasks to be actually
    completed in the linked session.
    """
    req_identity = request.query_params.get("user_id")
    if req_identity is not None and req_identity != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden for this user.",
        )

    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )

    plan = daily_plan_repo.get_plan(user_id, body.plan_date)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Daily plan not found for this date.",
        )

    # Validate session ownership if a session_id is provided in the request
    if body.session_id is not None:
        session = assessment_repo.get_session(body.session_id)
        if session is not None and session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session is not owned by this user.",
            )

    # Validate transition
    allowed = _VALID_TRANSITIONS.get(plan.status, set())
    if body.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Invalid status transition: '{plan.status}' → '{body.status}'. "
                f"Allowed targets from '{plan.status}': {sorted(allowed)}."
            ),
        )

    # When transitioning to completed, verify all tasks are actually done
    if body.status == "completed":
        session_id = body.session_id or plan.session_id
        plan_with_session = plan.model_copy(update={"session_id": session_id})
        if not _check_plan_completion(plan_with_session, assessment_repo):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot mark plan as completed: not all recommended tasks are finished.",
            )

    daily_plan_repo.update_plan_status(
        user_id=user_id,
        plan_date=body.plan_date,
        status=body.status,
        session_id=body.session_id,
    )
    updated = daily_plan_repo.get_plan(user_id, body.plan_date)
    if updated is None:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Update failed.",
        )
    return updated
