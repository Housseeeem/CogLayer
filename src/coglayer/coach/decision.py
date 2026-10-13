"""Adaptive decision engine for CogLayer.

Pure function, no I/O, no randomness.  Determines the next step for a user
given the results collected in the current session.

Protocol order
--------------
The two-task initial protocol runs in this fixed order:

    PROTOCOL_ORDER = ("go_no_go", "sequence_span")

A task is "done" when at least one TaskResult exists for it in ``results``.
Tasks submitted outside PROTOCOL_ORDER are silently ignored by the engine.

Decision rules (applied in strict priority order)
--------------------------------------------------
1. First task in PROTOCOL_ORDER with no result in ``results``
   -> ``next_task`` (for both IN_PROGRESS and INTERRUPTED sessions —
   INTERRUPTED is treated identically).
2. Both tasks have results but any required task has
   ``data_quality.completeness < settings.completeness_threshold``
   -> ``insufficient_data`` (a NEW session is required; a second submit
   for the same session/task returns HTTP 409).
3. Both tasks have results and all are sufficient -> ``complete``.

Requirements: R-007.1, R-007.2, R-007.3
"""

from __future__ import annotations

from typing import Final

from coglayer.core.models import (
    EngineDecision,
    TaskResult,
)
from coglayer.core.settings import Settings

__all__ = ["PROTOCOL_ORDER", "AdaptiveDecisionEngine"]

PROTOCOL_ORDER: Final[tuple[str, ...]] = ("go_no_go", "sequence_span")
"""Fixed execution order for the two-task initial protocol."""


class AdaptiveDecisionEngine:
    """Determines the next step for a user in a session.

    All methods are pure: they read inputs and return an ``EngineDecision``
    with no side effects, no I/O, and no randomness.

    Requirements: R-007.1, R-007.2, R-007.3
    """

    def decide(
        self,
        results: list[TaskResult],
        settings: Settings,
    ) -> EngineDecision:
        """Return the next decision for the current session.

        Parameters
        ----------
        results :
            All TaskResult objects for this session.
        settings :
            Application settings (provides ``completeness_threshold``).

        Returns
        -------
        EngineDecision
            One of:
            - ``next_task`` -- the next task_id to run
            - ``insufficient_data`` -- a required result is below threshold
              (a NEW session is required; resubmitting to this session
              returns HTTP 409)
            - ``complete`` -- all required tasks done and sufficient
        """
        results_by_task: dict[str, TaskResult] = {
            r.task_id: r for r in results if r.task_id in PROTOCOL_ORDER
        }

        # ------------------------------------------------------------------
        # Rule 1: first protocol task with no result -> next_task
        # (applies identically for IN_PROGRESS and INTERRUPTED sessions)
        # ------------------------------------------------------------------
        for task_id in PROTOCOL_ORDER:
            if task_id not in results_by_task:
                return EngineDecision(next_task=task_id, status="next_task")

        # ------------------------------------------------------------------
        # Rule 2: both tasks have results — quality check
        # Any required result below threshold -> insufficient_data
        # ------------------------------------------------------------------
        threshold = settings.completeness_threshold
        for task_id in PROTOCOL_ORDER:
            result = results_by_task[task_id]
            if result.data_quality.completeness < threshold:
                return EngineDecision(
                    next_task=None,
                    status="insufficient_data",
                    reason=(
                        f"Task '{task_id}' completeness "
                        f"{result.data_quality.completeness:.2f} is below "
                        f"threshold {threshold:.2f}. Start a new session to retry."
                    ),
                )

        # ------------------------------------------------------------------
        # Rule 3: all done and sufficient
        # ------------------------------------------------------------------
        return EngineDecision(next_task=None, status="complete")
