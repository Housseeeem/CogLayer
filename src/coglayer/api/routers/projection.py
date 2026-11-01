"""Possible-trajectory projection endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from coglayer.api.deps import get_consent_service, get_profile_repo
from coglayer.core.projection import ProjectionResponse, project_evidence
from coglayer.core.protocols import ProfileRepository
from coglayer.privacy.consent import ConsentService

router = APIRouter(tags=["projection"])


@router.get("/projection/{user_id}", response_model=ProjectionResponse)
def get_projection(
    user_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
) -> ProjectionResponse:
    """Return possible trajectories from stored evidence without ranking dimensions."""
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )
    profile = profile_repo.get_profile(user_id)
    return project_evidence(profile.evidence_history if profile is not None else [])
