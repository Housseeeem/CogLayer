"""Admin router for CogLayer assessment API.

Endpoints:
- DELETE /users/{user_id}: delete all data for a user across all repositories

Requirements: R-001.2
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from coglayer.api.deps import (
    get_assessment_repo,
    get_consent_repo,
    get_conversation_repo,
    get_experience_profile_repo,
    get_profile_repo,
)
from coglayer.core.protocols import (
    AssessmentRepository,
    ConsentRepository,
    ConversationRepository,
    ExperienceProfileRepository,
    ProfileRepository,
)

router = APIRouter(tags=["admin"])


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_data(
    user_id: str,
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    consent_repo: Annotated[ConsentRepository, Depends(get_consent_repo)],
    conversation_repo: Annotated[ConversationRepository, Depends(get_conversation_repo)],
    experience_profile_repo: Annotated[
        ExperienceProfileRepository, Depends(get_experience_profile_repo)
    ],
) -> None:
    """Delete all assessment sessions, trials, metrics, profiles, consent,
    conversation records, and experience profiles for the specified user (R-001.2).
    """
    assessment_repo.delete_user(user_id)
    profile_repo.delete_user(user_id)
    consent_repo.delete_consent(user_id)
    conversation_repo.delete_user(user_id)
    experience_profile_repo.delete_user(user_id)
