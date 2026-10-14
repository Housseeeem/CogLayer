"""Consent router for CogLayer assessment API.

Endpoints:
- POST /consent: record consent for user_id
- DELETE /consent/{user_id}: revoke consent
- GET /consent/{user_id}: check consent status

Requirements: R-001.1, R-001.4
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from coglayer.api.deps import get_consent_service
from coglayer.core.models import ConsentRecord
from coglayer.privacy.consent import ConsentService

router = APIRouter(tags=["consent"])


class ConsentRequest(BaseModel):
    """Payload to record consent."""

    user_id: str


class ConsentStatusResponse(BaseModel):
    """Consent check response."""

    has_consented: bool


@router.post("/consent", response_model=ConsentRecord, status_code=status.HTTP_201_CREATED)
def record_consent(
    body: ConsentRequest,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
) -> ConsentRecord:
    """Record consent for a user."""
    return consent_service.record_consent(body.user_id)


@router.delete("/consent/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_consent(
    user_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
) -> None:
    """Revoke consent for a user."""
    consent_service.revoke_consent(user_id)


@router.get("/consent/{user_id}", response_model=ConsentStatusResponse)
def get_consent_status(
    user_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
) -> ConsentStatusResponse:
    """Check whether a user has active consent."""
    return ConsentStatusResponse(has_consented=consent_service.has_consented(user_id))
