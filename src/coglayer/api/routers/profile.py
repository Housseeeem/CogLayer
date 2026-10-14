"""Profile router for CogLayer assessment API.

Endpoints:
- GET /profile/{user_id}: retrieve cognitive profile for a user

Requirements: R-006.2, R-006.4
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from coglayer.api.deps import get_profile_repo
from coglayer.core.models import CognitiveProfile
from coglayer.core.protocols import ProfileRepository

router = APIRouter(tags=["profile"])


@router.get("/profile/{user_id}", response_model=CognitiveProfile)
def get_profile(
    user_id: str,
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
) -> CognitiveProfile:
    """Retrieve the cognitive profile for a user.

    Returns an empty profile if no assessments have been scored yet.
    """
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
