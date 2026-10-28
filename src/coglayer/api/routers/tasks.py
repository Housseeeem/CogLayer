"""Tasks router for CogLayer assessment API.

Endpoints:
- POST /tasks/{task_id}/submit: submit raw task results, score, store, update profile
- GET /tasks: list registered task descriptors
- GET /tasks/{task_id}: get task descriptor for task_id

Requirements: R-002.1, R-005.4, R-006.1
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from coglayer.api.deps import (
    get_assessment_repo,
    get_consent_service,
    get_daily_plan_repo,
    get_profile_repo,
    get_profile_service,
    get_scoring_adapters,
    get_task_registry,
)
from coglayer.core.exceptions import DuplicateSubmissionError
from coglayer.core.models import CognitiveProfile, Session, TaskDescriptor, TaskResult
from coglayer.core.protocols import (
    AssessmentRepository,
    DailyPlanRepository,
    ProfileRepository,
    ScoringAdapter,
    TaskRegistry,
)
from coglayer.privacy.consent import ConsentService
from coglayer.profile.service import ProfileService

router = APIRouter(tags=["tasks"])
logger = logging.getLogger(__name__)


class TaskSubmitRequest(BaseModel):
    """Payload to submit task results for scoring and storage."""

    session_id: str
    user_id: str
    raw_result: dict[str, Any]


@router.get("/tasks", response_model=list[str])
def list_tasks(
    registry: Annotated[TaskRegistry, Depends(get_task_registry)],
) -> list[str]:
    """List distinct registered task IDs."""
    return registry.list_ids()


@router.get("/tasks/{task_id}", response_model=TaskDescriptor)
def get_task(
    task_id: str,
    registry: Annotated[TaskRegistry, Depends(get_task_registry)],
    version: str = "1.0",
) -> TaskDescriptor:
    """Get descriptor for a task."""
    try:
        return registry.get(task_id, version)
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} (version {version}) not found in registry.",
        ) from e


@router.post("/tasks/{task_id}/submit", response_model=TaskResult, status_code=status.HTTP_200_OK)
def submit_task_result(
    task_id: str,
    body: TaskSubmitRequest,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    profile_service: Annotated[ProfileService, Depends(get_profile_service)],
    scorers: Annotated[dict[str, ScoringAdapter], Depends(get_scoring_adapters)],
    registry: Annotated[TaskRegistry, Depends(get_task_registry)],
    daily_plan_repo: Annotated[DailyPlanRepository, Depends(get_daily_plan_repo)],
) -> TaskResult:
    """Submit raw task result, score it, persist result and update profile.

    Validates:
    - User has active consent (HTTP 403)
    - Session exists and belongs to user_id (HTTP 403)
    - Duplicate submission rejected (HTTP 409)
    """
    # 1. Consent verification
    if not consent_service.has_consented(body.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )

    # 2. Session verification
    session = assessment_repo.get_session(body.session_id)
    if session is None or session.user_id != body.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session not found or forbidden for this user.",
        )

    # 3. Resolve scorer
    scorer = scorers.get(task_id)
    if scorer is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No scoring adapter registered for task_id {task_id}.",
        )

    # 4. Force identity fields from the checked request (never trust raw_result)
    raw_payload = dict(body.raw_result)
    raw_payload["session_id"] = body.session_id
    raw_payload["user_id"] = body.user_id
    raw_payload["task_id"] = task_id

    # 5. Score raw result
    try:
        result = scorer.score(raw_payload)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Error scoring task result: {e}",
        ) from e

    # 5.5 Check task_version registration
    try:
        registry.get(task_id, result.task_version)
    except KeyError:
        if "unknown_task_version" not in result.data_quality.anomalies:
            result.data_quality.anomalies.append("unknown_task_version")

    # 6. Compute updated profile (pure computation) BEFORE save_result
    updated_profile: CognitiveProfile | None = None
    if not result.data_quality.anomalies:
        existing_profile = profile_repo.get_profile(body.user_id)
        if existing_profile is None:
            existing_profile = CognitiveProfile(
                user_id=body.user_id,
                dimensions={},
                evidence_history=[],
                data_quality={},
                uncertainty={},
            )
        updated_profile = profile_service.update_from_result(existing_profile, result)

    # 7. Save result to assessment repository (duplicate check)
    try:
        assessment_repo.save_result(result)
    except DuplicateSubmissionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate submission for session {body.session_id} and task {task_id}.",
        ) from e

    # 8. Persist profile update (with compensation if save_profile fails)
    if updated_profile is not None:
        try:
            profile_repo.save_profile(updated_profile)
        except Exception as exc:
            try:
                assessment_repo.delete_result(body.session_id, task_id)
            except Exception as del_exc:
                logger.warning(
                    "Failed to compensate task result deletion for session %s task %s: %s",
                    body.session_id,
                    task_id,
                    del_exc,
                )
            raise exc

    # 9. Append task_id to session.completed_tasks and persist (only if sufficient for completion)
    if (
        task_id not in session.completed_tasks
        and result.data_quality.is_sufficient_for_completion()
    ):
        session.completed_tasks.append(task_id)
        assessment_repo.save_session(session)

    # 10. Auto-update daily plan status if this session is linked to one
    _update_daily_plan_after_completion(
        daily_plan_repo=daily_plan_repo,
        assessment_repo=assessment_repo,
        session=session,
        user_id=body.user_id,
        task_id=task_id,
    )

    return result


def _update_daily_plan_after_completion(
    daily_plan_repo: DailyPlanRepository,
    assessment_repo: AssessmentRepository,
    session: Session,
    user_id: str,
    task_id: str,
) -> None:
    """Check if the daily plan should transition after a task completion.

    Finds the plan linked to this session, or an unlinked plan for the session date
    if the completed task belongs to the plan's recommendations.
    Transitions status based on persisted valid task results in the session.
    """
    if session.user_id != user_id:
        return

    # 1. Try finding a plan already linked to this session
    plan = daily_plan_repo.get_plan_by_session(user_id, session.session_id)

    # 2. If no plan linked, check if an unlinked plan exists for the session's date
    if plan is None:
        session_date = session.start_time.strftime("%Y-%m-%d")
        candidate = daily_plan_repo.get_plan(user_id, session_date)
        if (
            candidate is not None
            and candidate.session_id is None
            and candidate.status in ("generated", "started")
        ):
            recommended_ids = {rec.task_id for rec in candidate.recommendations}
            # Only associate if the submitted task belongs to the plan's recommendations
            if task_id in recommended_ids:
                daily_plan_repo.update_plan_status(
                    user_id=user_id,
                    plan_date=candidate.plan_date,
                    status="started",
                    session_id=session.session_id,
                )
                plan = candidate.model_copy(
                    update={"session_id": session.session_id, "status": "started"}
                )

    if plan is None or plan.status == "completed":
        return
    if plan.session_id != session.session_id:
        return

    required_ids = {rec.task_id for rec in plan.recommendations}
    if not required_ids:
        return

    # Check verified persisted results in the exact session
    results = assessment_repo.get_results(session.session_id)
    verified_ids = {
        res.task_id
        for res in results
        if res.task_id in required_ids
        and res.session_id == session.session_id
        and res.user_id == user_id
        and res.data_quality.is_sufficient_for_completion()
    }

    if required_ids.issubset(verified_ids):
        daily_plan_repo.update_plan_status(
            user_id=user_id,
            plan_date=plan.plan_date,
            status="completed",
            session_id=session.session_id,
        )
    elif plan.status == "generated" and (required_ids & verified_ids):
        daily_plan_repo.update_plan_status(
            user_id=user_id,
            plan_date=plan.plan_date,
            status="started",
            session_id=session.session_id,
        )
