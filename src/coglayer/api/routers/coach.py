"""Coach router for CogLayer assessment API.

Endpoints:
- POST /coach/{user_id}: generate supportive coaching feedback from cognitive profile

Requirements: R-008.1, R-008.2, R-008.3, R-008.4, R-008.5
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from coglayer.api.deps import (
    get_assessment_repo,
    get_coach,
    get_consent_service,
    get_conversation_service,
    get_db_settings,
    get_llm_provider,
    get_profile_repo,
)
from coglayer.coach.coach import CognitiveCoach
from coglayer.coach.conversation import ConversationService
from coglayer.core.brain_twin import build_brain_twin_signal
from coglayer.core.models import CognitiveProfile
from coglayer.core.protocols import AssessmentRepository, LLMProvider, ProfileRepository
from coglayer.core.settings import Settings
from coglayer.privacy.consent import ConsentService

router = APIRouter(tags=["coach"])


class CoachFeedbackRequest(BaseModel):
    """Optional payload for coaching feedback request."""

    user_id: str | None = None
    session_id: str | None = None


class StartConversationRequest(BaseModel):
    """Request to start a new conversation."""

    session_id: str | None = None


class MessageRequest(BaseModel):
    """Request to add a message to a conversation."""

    content: str = Field(min_length=1, max_length=8192)


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

    # 2. Consent verification
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )

    # 3. Optional session verification if session_id provided in body
    if body is not None and body.session_id is not None:
        session = assessment_repo.get_session(body.session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Session not found or forbidden for this user.",
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

    signal = build_brain_twin_signal(profile.evidence_history)
    return coach.generate_feedback(
        profile,
        provider=provider,
        settings=settings,
        brain_twin_signal=signal,
    )


@router.post("/coach/{user_id}/conversations")
def start_conversation(
    user_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    coach: Annotated[CognitiveCoach, Depends(get_coach)],
    conversation_service: Annotated[ConversationService, Depends(get_conversation_service)],
    settings: Annotated[Settings, Depends(get_db_settings)],
    request: Request,
    body: StartConversationRequest | None = None,
) -> dict[str, str]:
    """Start a new coaching conversation.

    Validates:
    - Request identity matches target user_id (HTTP 403)
    - User has active consent (HTTP 403)
    - Locked (HTTP 403) until the user has completed at least one protocol session.
    """
    # Identity verification
    req_identity: str | None = None
    if body is not None and hasattr(body, "user_id") and body.user_id is not None:
        req_identity = body.user_id
    elif request.query_params.get("user_id") is not None:
        req_identity = request.query_params.get("user_id")

    if req_identity is not None and req_identity != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden for this user.",
        )

    # Consent verification
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )

    # Coach availability check
    sessions = assessment_repo.get_sessions_by_user(user_id)
    all_session_results = [assessment_repo.get_results(s.session_id) for s in sessions]

    if not coach.is_available(user_id, all_session_results, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assessment not yet complete. Please finish all tasks first.",
        )

    # Start conversation
    session_id = body.session_id if body else None
    conversation = conversation_service.start_conversation(user_id, session_id)

    return {"conversation_id": conversation.conversation_id}


@router.post("/coach/{user_id}/conversations/{conversation_id}/messages")
def add_message(
    user_id: str,
    conversation_id: str,
    body: MessageRequest,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    assessment_repo: Annotated[AssessmentRepository, Depends(get_assessment_repo)],
    profile_repo: Annotated[ProfileRepository, Depends(get_profile_repo)],
    conversation_service: Annotated[ConversationService, Depends(get_conversation_service)],
    provider: Annotated[LLMProvider | None, Depends(get_llm_provider)],
    settings: Annotated[Settings, Depends(get_db_settings)],
) -> dict[str, str]:
    """Add a user message and get an assistant response.

    Validates:
    - User has active consent (HTTP 403)
    - Conversation belongs to the user (HTTP 403)
    """
    # Consent verification
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )

    # Verify conversation ownership
    conversation = conversation_service.get_conversation(conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation not found or forbidden for this user.",
        )

    # Get profile for context
    profile = profile_repo.get_profile(user_id)
    if profile is None:
        profile = CognitiveProfile(
            user_id=user_id,
            dimensions={},
            evidence_history=[],
            data_quality={},
            uncertainty={},
        )

    # Build Brain Twin signal
    signal = build_brain_twin_signal(profile.evidence_history)

    # Add message and get response
    response = conversation_service.add_message_and_get_response(
        conversation_id,
        body.content,
        profile,
        provider,
        settings,
        brain_twin_signal=signal,
    )

    return {"content": response.content}


@router.get("/coach/{user_id}/conversations")
def list_conversations(
    user_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    conversation_service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> list[dict[str, str]]:
    """List all conversations for a user.

    Validates:
    - User has active consent (HTTP 403)
    """
    # Consent verification
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )

    conversations = conversation_service.get_user_conversations(user_id)
    return [
        {
            "conversation_id": conv.conversation_id,
            "session_id": conv.session_id or "",
            "created_at": conv.created_at.isoformat(),
            "message_count": str(len(conv.messages)),
        }
        for conv in conversations
    ]


@router.get("/coach/{user_id}/conversations/{conversation_id}")
def get_conversation(
    user_id: str,
    conversation_id: str,
    consent_service: Annotated[ConsentService, Depends(get_consent_service)],
    conversation_service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> dict[str, object]:
    """Get a conversation with all messages.

    Validates:
    - User has active consent (HTTP 403)
    - Conversation belongs to the user (HTTP 403)
    """
    # Consent verification
    if not consent_service.has_consented(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has not given active consent.",
        )

    # Verify conversation ownership
    conversation = conversation_service.get_conversation(conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation not found or forbidden for this user.",
        )

    return {
        "conversation_id": conversation.conversation_id,
        "session_id": conversation.session_id,
        "created_at": conversation.created_at.isoformat(),
        "messages": [
            {
                "role": msg.role.value,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
            }
            for msg in conversation.messages
        ],
    }
