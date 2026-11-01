"""Transparent Brain Twin baseline endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from coglayer.api.deps import get_consent_service, get_profile_repo
from coglayer.core.brain_twin import (
    PerDimensionBrainTwinResult,
    build_per_dimension_analysis,
)
from coglayer.core.protocols import ProfileRepository
from coglayer.privacy.consent import ConsentService

router = APIRouter(tags=["brain-twin"])


@router.get("/brain-twin/{user_id}", response_model=PerDimensionBrainTwinResult)
def get_brain_twin(
    user_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
) -> PerDimensionBrainTwinResult:
    """Return non-clinical EMA signals for comparable dimension outcomes."""
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )
    profile = profile_repo.get_profile(user_id)
    if profile is None:
        return build_per_dimension_analysis([])
    return build_per_dimension_analysis(profile.evidence_history)
