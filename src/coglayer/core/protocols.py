"""Protocol interfaces for CogLayer domain components.

Defines structural subtype contracts (typing.Protocol) for all cross-boundary
interactions in the system. Concrete implementations live in their respective
modules (signals, api.db, providers, etc.) and satisfy these protocols
structurally -- no explicit inheritance required.

This module has NO circular dependencies: all referenced models are imported
from core.models (including ConsentRecord, which is defined there rather than
in privacy.consent to keep this file self-contained).

Requirements: R-002.2, R-002.3, R-005.6, R-008.4
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from .models import (
    AdaptiveDailyPlan,
    CoachConversation,
    CoachMessage,
    CognitiveProfile,
    ConsentRecord,
    IOIObservation,
    RawTaskResult,
    Session,
    SessionStatus,
    TaskDescriptor,
    TaskResult,
)

__all__ = [
    "AssessmentRepository",
    "ConsentRepository",
    "ConversationRepository",
    "DailyPlanRepository",
    "IOIEventRepository",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "ProfileRepository",
    "ScoringAdapter",
    "TaskRegistry",
    "TaskRunner",
]


# ---------------------------------------------------------------------------
# LLM data models
# ---------------------------------------------------------------------------


class LLMRequest(BaseModel):
    """Request payload sent to an LLM provider.

    Only a neutral prompt string is sent -- never the cognitive profile or any
    raw trial data (R-001.3, R-008.5).
    """

    prompt: str


class LLMResponse(BaseModel):
    """Response payload received from an LLM provider."""

    text: str


# ---------------------------------------------------------------------------
# Task protocols (R-002.2, R-002.3)
# ---------------------------------------------------------------------------


@runtime_checkable
class TaskRunner(Protocol):  # pragma: no cover
    """Executes a cognitive task and returns a raw (unscored) result.

    Each task type has exactly one implementation. The runner is responsible
    for collecting stimulus/response data from the UI and returning it as a
    ``RawTaskResult`` dict. Scoring is delegated to ``ScoringAdapter``.

    Requirements: R-002.2
    """

    def run(
        self,
        session_id: str,
        user_id: str,
        parameters: dict[str, object],
    ) -> RawTaskResult:
        """Run the task and return the unscored raw result.

        Args:
            session_id: Identifier for the current assessment session.
            user_id: Identifier for the participant.
            parameters: Task-specific configuration (e.g. trial counts, ISI).

        Returns:
            A ``RawTaskResult`` dict that ``ScoringAdapter.score()`` can consume.
        """
        ...


@runtime_checkable
class ScoringAdapter(Protocol):  # pragma: no cover
    """Transforms a raw task result into a validated, scored ``TaskResult``.

    Each task type has exactly one implementation. The adapter applies
    exclusion rules, computes metrics, and populates ``DataQuality``.

    Requirements: R-002.3
    """

    def score(self, raw: RawTaskResult) -> TaskResult:
        """Score the raw result and return a fully-populated ``TaskResult``.

        Args:
            raw: Dict produced by ``TaskRunner.run()`` (or submitted via the API).

        Returns:
            A validated ``TaskResult`` with metrics, signals, and data quality.
        """
        ...


# ---------------------------------------------------------------------------
# Task registry protocol (R-002.1, R-002.5)
# ---------------------------------------------------------------------------


@runtime_checkable
class TaskRegistry(Protocol):  # pragma: no cover
    """Registry mapping (task_id, version) to ``TaskDescriptor`` objects.

    Adding a new task requires only calling ``register()`` -- no changes to
    profiling, decision, or coach code (R-002.5).
    """

    def register(self, descriptor: TaskDescriptor) -> None:
        """Register a task descriptor.

        Args:
            descriptor: The task descriptor to register.
        """
        ...

    def get(self, task_id: str, version: str) -> TaskDescriptor:
        """Retrieve a descriptor by task_id and version.

        Args:
            task_id: The task identifier.
            version: The task version string.

        Returns:
            The matching ``TaskDescriptor``.

        Raises:
            KeyError: If no descriptor matches (task_id, version).
        """
        ...

    def list_ids(self) -> list[str]:
        """Return the list of distinct registered task_ids.

        Returns:
            A list of unique task identifiers (versions collapsed).
        """
        ...

    def list_descriptors(self) -> list[TaskDescriptor]:
        """Return all unique registered task descriptors.

        Returns:
            A list of unique TaskDescriptor objects.
        """
        ...


# ---------------------------------------------------------------------------
# Repository protocols (R-005.6)
# ---------------------------------------------------------------------------


@runtime_checkable
class AssessmentRepository(Protocol):  # pragma: no cover
    """Persistence contract for sessions and task results.

    The storage backend for the MVP is SQLite (R-005.6). The protocol
    decouples domain code from the concrete storage implementation.
    """

    def save_session(self, session: Session) -> None:
        """Persist a new session record."""
        ...

    def get_session(self, session_id: str) -> Session | None:
        """Retrieve a session by ID, or ``None`` if not found."""
        ...

    def get_sessions_by_user(self, user_id: str) -> list[Session]:
        """Retrieve all sessions for a user, or empty list if none."""
        ...

    def update_session_status(self, session_id: str, status: SessionStatus) -> None:
        """Update the status field of an existing session."""
        ...

    def save_result(self, result: TaskResult) -> None:
        """Persist a scored ``TaskResult`` including all raw trials.

        Raises:
            DuplicateSubmissionError: If a result for the same
                ``(session_id, task_id)`` already exists (R-005.4).
        """
        ...

    def get_results(self, session_id: str) -> list[TaskResult]:
        """Return all ``TaskResult`` objects for a given session."""
        ...

    def delete_result(self, session_id: str, task_id: str) -> None:
        """Remove a task result and all associated trials, metrics, and quality records."""
        ...

    def delete_user(self, user_id: str) -> None:
        """Remove all sessions, trials, metrics, and quality records for user.

        Satisfies R-001.2: all raw data for the user is deleted.
        """
        ...


@runtime_checkable
class ProfileRepository(Protocol):  # pragma: no cover
    """Persistence contract for cognitive profiles."""

    def save_profile(self, profile: CognitiveProfile) -> None:
        """Persist (create or replace) a ``CognitiveProfile``."""
        ...

    def get_profile(self, user_id: str) -> CognitiveProfile | None:
        """Retrieve the profile for a user, or ``None`` if not found."""
        ...

    def delete_user(self, user_id: str) -> None:
        """Remove the profile record for the given user (R-001.2)."""
        ...


@runtime_checkable
class ConsentRepository(Protocol):  # pragma: no cover
    """Persistence contract for consent records (R-001.4).

    Consent state is persisted so that a user who has already consented does
    not see the consent screen again unless they revoke it.
    """

    def save_consent(self, record: ConsentRecord) -> None:
        """Persist a consent record (create or replace)."""
        ...

    def get_consent(self, user_id: str) -> ConsentRecord | None:
        """Retrieve the consent record for a user, or ``None`` if absent."""
        ...

    def delete_consent(self, user_id: str) -> None:
        """Remove the consent record for a user (R-001.2)."""
        ...


@runtime_checkable
class IOIEventRepository(Protocol):  # pragma: no cover
    """Persistence contract for explicitly recorded IOI observations."""

    def save_event(self, event: IOIObservation) -> bool:
        """Insert an event, returning False for an identical retry."""
        ...

    def get_events(self, user_id: str, session_id: str | None = None) -> list[IOIObservation]:
        """Return a user's IOI events, optionally limited to one session."""
        ...

    def delete_user(self, user_id: str) -> None:
        """Delete all IOI events owned by a user."""
        ...


@runtime_checkable
class DailyPlanRepository(Protocol):  # pragma: no cover
    """Persistence contract for adaptive daily cognitive game plans."""

    def save_plan(self, plan: AdaptiveDailyPlan) -> None:
        """Persist or update an adaptive daily plan."""
        ...

    def get_plan(self, user_id: str, plan_date: str) -> AdaptiveDailyPlan | None:
        """Retrieve the daily plan for a user on a given date, or None."""
        ...

    def get_plan_by_session(self, user_id: str, session_id: str) -> AdaptiveDailyPlan | None:
        """Retrieve the daily plan linked to a session for a user, or None."""
        ...

    def update_plan_status(
        self,
        user_id: str,
        plan_date: str,
        status: str,
        session_id: str | None = None,
    ) -> None:
        """Update lifecycle status and optional session ID of a daily plan."""
        ...

    def delete_user(self, user_id: str) -> None:
        """Remove all daily plans for the given user."""
        ...


# ---------------------------------------------------------------------------
# LLM provider protocol (R-008.4)
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):  # pragma: no cover
    """Interface for language model backends.

    The coach accesses the LLM exclusively through this protocol (R-008.4).
    A deterministic ``FakeProvider`` is used in all tests.

    The profile is NEVER sent through this interface (R-008.5).
    """

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to the LLM.

        Args:
            request: The prompt to send. Must not contain the cognitive profile
                or any raw trial data.

        Returns:
            The model's text response.
        """
        ...


@runtime_checkable
class ConversationRepository(Protocol):  # pragma: no cover
    """Persistence contract for coaching conversations."""

    def save_conversation(self, conversation: CoachConversation) -> None:
        """Persist a new conversation."""
        ...

    def get_conversation(self, conversation_id: str) -> CoachConversation | None:
        """Retrieve a conversation by ID, or None if not found."""
        ...

    def get_conversations_by_user(self, user_id: str) -> list[CoachConversation]:
        """Retrieve all conversations for a user, most recent first."""
        ...

    def save_message(self, message: CoachMessage) -> None:
        """Persist a new message."""
        ...

    def get_messages(self, conversation_id: str) -> list[CoachMessage]:
        """Retrieve all messages for a conversation in chronological order."""
        ...

    def delete_user(self, user_id: str) -> None:
        """Remove all conversations and messages for a user."""
        ...
