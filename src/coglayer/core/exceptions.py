"""Domain exceptions for CogLayer.

These exceptions cross module boundaries and are therefore defined in core.

Requirements: R-005.4
"""

from __future__ import annotations

__all__ = ["DuplicateSubmissionError"]


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
