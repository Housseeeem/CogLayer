"""Coach router for CogLayer assessment API.

Endpoints:
- POST /coach/{user_id}: generate supportive coaching feedback from cognitive profile

Requirements: R-008.1, R-008.2, R-008.3, R-008.4, R-008.5
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from coglayer.api.deps import (
    get_assessment_repo,
    get_coach,
    get_consent_service,
    get_db_settings,
    get_llm_provider,
    get_profile_repo,
)
from coglayer.coach.coach import CognitiveCoach
from coglayer.core.models import CognitiveProfile
from coglayer.core.protocols import AssessmentRepository, LLMProvider, ProfileRepository
from coglayer.core.settings import Settings
from coglayer.privacy.consent import ConsentService

router = APIRouter(tags=["coach"])


class CoachFeedbackRequest(BaseModel):
    """Optional payload for coaching feedback request."""

    user_id: str | None = None
    session_id: str | None = None


@router.post(
    "/coach/{user_id}",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
)
def get_coaching_feedback(
    user_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    coach: Annotated[CognitiveCoach, Depends(get_coach)],
    provider: Annotated[LLMProvider | None, Depends(get_llm_provider)],
    settings: Annotated[Settings, Depends(get_db_settings)],
    request: Request,
    body: CoachFeedbackRequest | None = None,
) -> str:
    """Generate supportive coaching feedback for a user.

    Validates:
    - Request identity matches target user_id (HTTP 403)
    - User has active consent (HTTP 403)
    - Locked (HTTP 403) until the user has completed at least one protocol session.
    """
    # 1. Identity verification
    req_identity: str | None = None
    if body is not None and body.user_id is not None:
        req_identity = body.user_id
    elif request.query_params.get("user_id") is not None:
        req_identity = request.query_params.get("user_id")

    if req_identity is not None and req_identity != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden for this user.",
        )

    # 1.5 Optional session verification if session_id provided in body
    if body is not None and body.session_id is not None:
        session = assessment_repo.get_session(body.session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session not found or forbidden for this user.",
            )

    # 2. Consent verification
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )

    sessions = assessment_repo.get_sessions_by_user(user_id)
    all_session_results = [assessment_repo.get_results(s.session_id) for s in sessions]

    if not coach.is_available(user_id, all_session_results, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assessment not yet complete. Please finish all tasks first.",
        )

    profile = profile_repo.get_profile(user_id)
    if profile is None:
        profile = CognitiveProfile(
            user_id=user_id,
            dimensions={},
            evidence_history=[],
            data_quality={},
            uncertainty={},
        )

    return coach.generate_feedback(profile, provider=provider, settings=settings)
