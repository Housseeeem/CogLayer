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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from coglayer.api.deps import (
    get_assessment_repo,
    get_consent_service,
    get_db_settings,
    get_decision_engine,
)
from coglayer.coach.decision import AdaptiveDecisionEngine
from coglayer.core.models import EngineDecision, Session, SessionStatus, TaskResult
from coglayer.core.protocols import AssessmentRepository
from coglayer.core.settings import Settings
from coglayer.privacy.consent import ConsentService

router = APIRouter(tags=["sessions"])


class SessionCreateRequest(BaseModel):
    """Payload to create a new assessment session."""

    user_id: str


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
        completed_tasks=[],
    )
    assessment_repo.save_session(session)
    return session


@router.get("/sessions/{session_id}", response_model=Session)
def get_session(
    session_id: str,
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
) -> Session:
    """Retrieve session details by session_id."""
    session = assessment_repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found.",
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
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
) -> list[TaskResult]:
    """Retrieve all scored task results for a session."""
    session = assessment_repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found.",
        )
    return assessment_repo.get_results(session_id)


@router.get("/sessions/{session_id}/decision", response_model=EngineDecision)
def get_session_decision(
    session_id: str,
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
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
    return engine.decide(results=results, settings=settings)
