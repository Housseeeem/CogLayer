"""Coach router for CogLayer assessment API.

Endpoints:
- POST /coach/{user_id}: generate supportive coaching feedback from cognitive profile

Requirements: R-008.1, R-008.2, R-008.3, R-008.4, R-008.5
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse

from coglayer.api.deps import (
    get_assessment_repo,
    get_coach,
    get_db_settings,
    get_llm_provider,
    get_profile_repo,
)
from coglayer.coach.coach import CognitiveCoach
from coglayer.core.models import CognitiveProfile
from coglayer.core.protocols import AssessmentRepository, LLMProvider, ProfileRepository
from coglayer.core.settings import Settings

router = APIRouter(tags=["coach"])


@router.post(
    "/coach/{user_id}",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
)
def get_coaching_feedback(
    user_id: str,
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    coach: Annotated[CognitiveCoach, Depends(get_coach)],
    provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    settings: Annotated[Settings, Depends(get_db_settings)],
) -> str:
    """Generate supportive coaching feedback for a user.

    Locked (HTTP 403) until the user has completed at least one protocol session.
    """
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

    return coach.generate_feedback(profile, provider)
