"""Tasks router for CogLayer assessment API.

Endpoints:
- POST /tasks/{task_id}/submit: submit raw task results, score, store, update profile
- GET /tasks: list registered task descriptors
- GET /tasks/{task_id}: get task descriptor for task_id

Requirements: R-002.1, R-005.4, R-006.1
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from coglayer.api.deps import (
    get_assessment_repo,
    get_consent_service,
    get_profile_repo,
    get_profile_service,
    get_scoring_adapters,
    get_task_registry,
)
from coglayer.core.exceptions import DuplicateSubmissionError
from coglayer.core.models import CognitiveProfile, TaskDescriptor, TaskResult
from coglayer.core.protocols import (
    AssessmentRepository,
    ProfileRepository,
    ScoringAdapter,
    TaskRegistry,
)
from coglayer.privacy.consent import ConsentService
from coglayer.profile.service import ProfileService

router = APIRouter(tags=["tasks"])


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

    # 4. Prepare raw result payload with top-level attributes
    raw_payload = dict(body.raw_result)
    raw_payload.setdefault("session_id", body.session_id)
    raw_payload.setdefault("user_id", body.user_id)
    raw_payload.setdefault("task_id", task_id)

    # 5. Score raw result
    try:
        result = scorer.score(raw_payload)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Error scoring task result: {e}",
        ) from e

    # 6. Save result to assessment repository (duplicate check)
    try:
        assessment_repo.save_result(result)
    except DuplicateSubmissionError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate submission for session {body.session_id} and task {task_id}.",
        ) from e

    # 7. Update profile via ProfileService only if quality gate passed
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
        profile_repo.save_profile(updated_profile)

    # 8. Append task_id to session.completed_tasks and persist
    if task_id not in session.completed_tasks:
        session.completed_tasks.append(task_id)
        assessment_repo.save_session(session)

    return result
