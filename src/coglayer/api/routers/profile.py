"""Profile router for CogLayer assessment API.

Endpoints:
- GET /profile/{user_id}: retrieve cognitive profile for a user

Requirements: R-006.2, R-006.4
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from coglayer.api.deps import (
    get_consent_service,
    get_experience_profile_repo,
    get_profile_repo,
)
from coglayer.core.goals import (
    GoalProgress,
    GoalTrackingResponse,
    compute_goal_progress,
)
from coglayer.core.models import CognitiveProfile
from coglayer.core.protocols import ExperienceProfileRepository, ProfileRepository
from coglayer.core.settings import get_settings
from coglayer.privacy.consent import ConsentService

router = APIRouter(tags=["profile"])


@router.get("/profile/{user_id}", response_model=CognitiveProfile)
def get_profile(
    user_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    request: Request,
) -> CognitiveProfile:
    """Retrieve the cognitive profile for a user.

    Validates:
    - Request identity matches target user_id (HTTP 403)
    - User has active consent (HTTP 403)
    Returns an empty profile if no assessments have been scored yet.
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

    profile = profile_repo.get_profile(user_id)
    if profile is None:
        return CognitiveProfile(
            user_id=user_id,
            dimensions={},
            evidence_history=[],
            data_quality={},
            uncertainty={},
        )
    return profile


@router.get("/profile/{user_id}/goals", response_model=GoalTrackingResponse)
def get_user_goals(
    user_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    experience_repo: Annotated[ExperienceProfileRepository, Depends(get_experience_profile_repo)],
    request: Request,
) -> GoalTrackingResponse:
    """Retrieve goal progress tracking for a user.

    Validates:
    - Request identity matches target user_id (HTTP 403)
    - User has active consent (HTTP 403)
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

    settings = get_settings()
    exp_profile = experience_repo.get_profile(user_id)
    goals = exp_profile.goals if exp_profile is not None and exp_profile.goals else []

    profile = profile_repo.get_profile(user_id)
    profile_data = (
        profile
        if profile is not None
        else CognitiveProfile(
            user_id=user_id,
            dimensions={},
            evidence_history=[],
            data_quality={},
            uncertainty={},
        )
    )

    progress_list: list[GoalProgress] = []
    for goal in goals:
        prog = compute_goal_progress(
            goal,
            profile_data.model_dump(),
            baseline_n=settings.goal_baseline_n_observations,
            target_delta=settings.goal_target_delta,
            min_sessions=settings.goal_min_sessions,
        )
        progress_list.append(prog)

    return GoalTrackingResponse(user_id=user_id, goals=progress_list)
