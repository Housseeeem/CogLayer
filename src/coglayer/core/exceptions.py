"""Domain exceptions for CogLayer.

These exceptions cross module boundaries and are therefore defined in core.

Requirements: R-005.4
"""

from __future__ import annotations

__all__ = [
    "DuplicateIOIEventError",
    "DuplicateSubmissionError",
    "IOIOpportunityConflictError",
    "IOISessionOwnershipError",
]


class DuplicateSubmissionError(Exception):
    """Raised when a task result for (session_id, task_id) already exists.

    The existing result is left intact (R-005.4).

    Attributes:
        session_id: The session identifier involved.
        task_id: The task identifier involved.
    """

    def __init__(self, session_id: str, task_id: str) -> None:
        self.session_id = session_id
        self.task_id = task_id
        super().__init__(
            f"Result for session_id={session_id!r}, task_id={task_id!r} already exists."
        )


class DuplicateIOIEventError(Exception):
    """Raised when an event ID is reused with different event data."""

    def __init__(self, event_id: str) -> None:
        self.event_id = event_id
        super().__init__(f"IOI event_id={event_id!r} already exists with different data.")


class IOIOpportunityConflictError(Exception):
    """Raised when an opportunity is submitted more than once with different data."""

    def __init__(self, user_id: str, component: str, opportunity_id: str) -> None:
        self.user_id = user_id
        self.component = component
        self.opportunity_id = opportunity_id
        super().__init__(
            f"IOI opportunity {opportunity_id!r} for user={user_id!r}, "
            f"component={component!r} already exists with different data."
        )


class IOISessionOwnershipError(Exception):
    """Raised when an IOI event user does not own its session."""

    def __init__(self, user_id: str, session_id: str) -> None:
        self.user_id = user_id
        self.session_id = session_id
        super().__init__(f"IOI session_id={session_id!r} is not owned by user_id={user_id!r}.")
