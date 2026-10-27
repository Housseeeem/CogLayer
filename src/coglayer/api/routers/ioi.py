"""FastAPI routes for structured IOI observations and score snapshots."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from coglayer.api.deps import (
    get_assessment_repo,
    get_consent_service,
    get_ioi_event_repo,
    get_ioi_scoring_service,
)
from coglayer.core.exceptions import (
    DuplicateIOIEventError,
    IOIOpportunityConflictError,
)
from coglayer.core.ioi import IOIScoringService
from coglayer.core.models import IOIObservation, IOIScore
from coglayer.core.protocols import (
    AssessmentRepository,
    IOIEventRepository,
)
from coglayer.privacy.consent import ConsentService

router = APIRouter(tags=["ioi"])


class IOIEventResponse(BaseModel):
    """Response describing whether an IOI event was recorded or retried."""

    status: str
    event_id: str


@router.post(
    "/ioi/events",
    response_model=IOIEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_event(
    event: IOIObservation,
    response: Response,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    event_repo: Annotated[IOIEventRepository, Depends(get_ioi_event_repo)],
) -> IOIEventResponse:
    """Record one explicitly submitted IOI opportunity outcome."""
    if not consent_service.has_consented(event.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )
    session = assessment_repo.get_session(event.session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {event.session_id} not found.",
        )
    if session.user_id != event.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session is not owned by this user.",
        )
    try:
        inserted = event_repo.save_event(event)
    except DuplicateIOIEventError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IOIOpportunityConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not inserted:
        response.status_code = status.HTTP_200_OK
    return IOIEventResponse(
        status="recorded" if inserted else "duplicate",
        event_id=event.event_id,
    )


@router.get("/ioi/{user_id}/score", response_model=IOIScore)
def get_score(
    user_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    event_repo: Annotated[IOIEventRepository, Depends(get_ioi_event_repo)],
    scoring_service: Annotated[IOIScoringService, Depends(get_ioi_scoring_service)],
    session_id: Annotated[str | None, Query()] = None,
) -> IOIScore:
    """Return a user's IOI score, optionally limited to one owned session."""
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )
    if session_id is not None:
        session = assessment_repo.get_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found.",
            )
        if session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session is not owned by this user.",
            )
    events = event_repo.get_events(user_id, session_id=session_id)
    return scoring_service.score(events)
