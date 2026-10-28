"""Sessions router for CogLayer assessment API.

Endpoints:
- POST /sessions: create new session (requires consent, 403 if not consented)
- GET /sessions/{session_id}: get session details
- PATCH /sessions/{session_id}/status: update session status
- GET /sessions/{session_id}/results: get all task results for session
- GET /sessions/{session_id}/decision: evaluate next task / completion decision

Requirements: R-001.1, R-005.2, R-007.1, REQ-011 test_ac_new_session_after_consent
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from coglayer.api.deps import (
    get_assessment_repo,
    get_consent_service,
    get_db_settings,
    get_decision_engine,
    get_profile_repo,
)
from coglayer.coach.decision import AdaptiveDecisionEngine
from coglayer.core.models import EngineDecision, Session, SessionStatus, SessionType, TaskResult
from coglayer.core.protocols import AssessmentRepository, ProfileRepository
from coglayer.core.settings import Settings
from coglayer.privacy.consent import ConsentService

router = APIRouter(tags=["sessions"])


class SessionCreateRequest(BaseModel):
    """Payload to create a new assessment session."""

    user_id: str
    session_type: SessionType = SessionType.ASSESSMENT


class SessionStatusUpdateRequest(BaseModel):
    """Payload to update session status."""

    status: SessionStatus


@router.post("/sessions", response_model=Session, status_code=status.HTTP_201_CREATED)
def create_session(
    body: SessionCreateRequest,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
) -> Session:
    """Create a new assessment session with status=PENDING.

    Requires prior user consent; returns HTTP 403 Forbidden if not consented.
    """
    if not consent_service.has_consented(body.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent for cognitive assessment.",
        )

    session = Session(
        session_id=str(uuid.uuid4()),
        user_id=body.user_id,
        start_time=datetime.now(UTC),
        end_time=None,
        status=SessionStatus.PENDING,
        session_type=body.session_type,
        completed_tasks=[],
    )
    assessment_repo.save_session(session)
    return session


@router.get("/sessions", response_model=list[Session])
def list_sessions(
    user_id: Annotated[str, Query(min_length=1)],
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
) -> list[Session]:
    """List pending and in-progress sessions owned by a consented user."""
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )
    return [
        session
        for session in assessment_repo.get_sessions_by_user(user_id)
        if session.status in (SessionStatus.PENDING, SessionStatus.IN_PROGRESS)
    ]


@router.get("/sessions/{session_id}", response_model=Session)
def get_session(
    session_id: str,
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    user_id: Annotated[str | None, Query()] = None,
) -> Session:
    """Retrieve session details by session_id."""
    session = assessment_repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found.",
        )
    if user_id is not None and session.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session is not owned by this user.",
        )
    return session


@router.patch("/sessions/{session_id}/status", response_model=Session)
def update_session_status(
    session_id: str,
    body: SessionStatusUpdateRequest,
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
) -> Session:
    """Update lifecycle status of an assessment session."""
    session = assessment_repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found.",
        )

    assessment_repo.update_session_status(session_id, body.status)
    session.status = body.status
    if (
        body.status in (SessionStatus.COMPLETED, SessionStatus.INTERRUPTED)
        and session.end_time is None
    ):
        session.end_time = datetime.now(UTC)
        assessment_repo.save_session(session)
    return session


@router.get("/sessions/{session_id}/results", response_model=list[TaskResult])
def get_session_results(
    session_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    request: Request,
) -> list[TaskResult]:
    """Retrieve all scored task results for a session.

    Validates:
    - If declared user_id is provided, checks its consent and match with session owner (HTTP 403)
    - Session existence (HTTP 404)
    - User consent for session owner (HTTP 403)
    """
    req_identity = request.query_params.get("user_id")

    # If caller declares an identity, verify consent before any session/results read
    if req_identity is not None and not consent_service.has_consented(req_identity):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )

    session = assessment_repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found.",
        )

    # Verify session ownership against declared identity
    if req_identity is not None and session.user_id != req_identity:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden for this user.",
        )

    # Verify active consent of the session owner
    if not consent_service.has_consented(session.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )

    return assessment_repo.get_results(session_id)


@router.get("/sessions/{session_id}/decision", response_model=EngineDecision)
def get_session_decision(
    session_id: str,
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    engine: Annotated[AdaptiveDecisionEngine, Depends(get_decision_engine)],
    settings: Annotated[Settings, Depends(get_db_settings)],
) -> EngineDecision:
    """Evaluate AdaptiveDecisionEngine for this session."""
    session = assessment_repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found.",
        )
    results = assessment_repo.get_results(session_id)
    profile = profile_repo.get_profile(session.user_id)
    return engine.decide(results=results, settings=settings, profile=profile)
