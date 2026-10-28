"""Onboarding router for CogLayer assessment API.

Endpoints:
- PUT /onboarding/profile/{user_id}: Save or update onboarding profile
- GET /onboarding/profile/{user_id}: Retrieve onboarding profile

Guards:
- User must have active consent
- Request identity must match user_id (ownership)
- For child/teen age groups: guardian_consent must be true
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from coglayer.api.deps import (
    get_consent_repo,
    get_consent_service,
    get_experience_profile_repo,
)
from coglayer.core.models import (
    AgeGroup,
    ExperienceProfile,
    GuidanceLevel,
    InfoStyle,
    LayoutType,
    TechComfort,
    ThemeType,
)
from coglayer.core.protocols import (
    ConsentRepository,
    ExperienceProfileRepository,
)
from coglayer.onboarding.calibration import determine_guidance_level
from coglayer.privacy.consent import ConsentService

router = APIRouter(tags=["onboarding"])


class OnboardingRequest(BaseModel):
    """Payload to save or update onboarding profile."""

    age_group: AgeGroup
    goals: list[str]
    tech_comfort: TechComfort
    info_style: InfoStyle
    layout: LayoutType
    theme: ThemeType
    guidance_level: GuidanceLevel | None = None


class CalibrationRequest(BaseModel):
    """Payload to submit calibration task results."""

    accuracy: float = Field(ge=0.0, le=1.0)
    mean_rt_ms: float = Field(ge=0.0)


@router.put(
    "/onboarding/profile/{user_id}",
    response_model=ExperienceProfile,
    status_code=status.HTTP_200_OK,
)
def save_onboarding_profile(
    user_id: str,
    body: OnboardingRequest,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    consent_repo: Annotated[ConsentRepository, Depends(get_consent_repo)],
    onboarding_repo: Annotated[ExperienceProfileRepository, Depends(get_experience_profile_repo)],
    request: Request,
) -> ExperienceProfile:
    """Save or update onboarding profile for a user.

    Guards:
    - User must have active consent (403 if not)
    - Request identity must match user_id (403 if mismatch)
    - For child/teen age groups: guardian_consent must be true (403 if not)
    """
    # Identity check: user_id from request must match path parameter
    req_identity = request.query_params.get("user_id")
    if req_identity and req_identity != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: identity mismatch",
        )

    # Consent check
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent",
        )

    # Guardian consent check for minors
    consent_record = consent_repo.get_consent(user_id)
    if consent_record and not consent_record.guardian_consent:
        if body.age_group in (AgeGroup.CHILD_7_12, AgeGroup.TEEN_13_17):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Guardian consent required for minors",
            )

    profile = ExperienceProfile(
        user_id=user_id,
        age_group=body.age_group,
        goals=body.goals,
        tech_comfort=body.tech_comfort,
        info_style=body.info_style,
        layout=body.layout,
        theme=body.theme,
        guidance_level=body.guidance_level,
    )
    onboarding_repo.save_profile(profile)
    return profile


@router.get("/onboarding/profile/{user_id}", response_model=ExperienceProfile)
def get_onboarding_profile(
    user_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    onboarding_repo: Annotated[ExperienceProfileRepository, Depends(get_experience_profile_repo)],
    request: Request,
) -> ExperienceProfile:
    """Retrieve onboarding profile for a user.

    Guards:
    - User must have active consent (403 if not)
    - Request identity must match user_id (403 if mismatch)
    """
    # Identity check
    req_identity = request.query_params.get("user_id")
    if req_identity and req_identity != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: identity mismatch",
        )

    # Consent check
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent",
        )

    profile = onboarding_repo.get_profile(user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding profile not found",
        )
    return profile


@router.post("/onboarding/calibration/{user_id}", response_model=ExperienceProfile)
def submit_calibration(
    user_id: str,
    body: CalibrationRequest,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    consent_repo: Annotated[ConsentRepository, Depends(get_consent_repo)],
    onboarding_repo: Annotated[ExperienceProfileRepository, Depends(get_experience_profile_repo)],
    request: Request,
) -> ExperienceProfile:
    """Submit calibration task results and update guidance level.

    Computes guidance level from accuracy and reaction time using age-specific
    thresholds, then updates the existing ExperienceProfile.

    Guards:
    - User must have active consent (403 if not)
    - Request identity must match user_id (403 if mismatch)
    - Experience profile must exist (404 if not)
    """
    # Identity check
    req_identity = request.query_params.get("user_id")
    if req_identity and req_identity != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: identity mismatch",
        )

    # Consent check
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent",
        )

    # Get existing profile
    profile = onboarding_repo.get_profile(user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experience profile not found. Complete onboarding first.",
        )

    # Compute guidance level
    guidance_level = determine_guidance_level(
        accuracy=body.accuracy,
        mean_rt_ms=body.mean_rt_ms,
        age_group=profile.age_group,
    )

    # Update profile with new guidance level
    updated_profile = profile.model_copy(update={"guidance_level": guidance_level})
    onboarding_repo.save_profile(updated_profile)

    return updated_profile
