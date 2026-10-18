"""Adaptive decision engine for CogLayer.

Pure function, no I/O, no randomness. Determines the next step for a user
given the results collected in the current session.

The engine works from the TaskRegistry instead of a fixed task order, proposing
the next task targeting the dimension whose estimate is the least certain
(widest 90% credible interval). If multiple dimensions are tied for maximum
uncertainty, the tie is broken deterministically by alphabetical order of task_id
(as returned by list_ids()).

Decision rules (applied in strict priority order)
--------------------------------------------------
1. Propose the next task for the dimension with the least certain estimate
   among uncompleted registered tasks (ties broken alphabetically by task_id).
2. When all registered tasks have results, verify data quality:
   any required task with completeness < settings.completeness_threshold
   -> insufficient_data.
3. When all registered tasks have results and all are sufficient -> complete.

Requirements: R-007.1, R-007.2, R-007.3
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from coglayer.core.models import (
    CognitiveProfile,
    EngineDecision,
    TaskDescriptor,
    TaskResult,
)
from coglayer.core.settings import Settings
from coglayer.core.tasks import DEFAULT_TASK_DESCRIPTORS

if TYPE_CHECKING:
    from coglayer.core.protocols import TaskRegistry

__all__ = ["PROTOCOL_ORDER", "AdaptiveDecisionEngine"]

PROTOCOL_ORDER: Final[tuple[str, ...]] = ("go_no_go", "sequence_span")
"""Deprecated protocol order tuple kept for backwards compatibility."""


class AdaptiveDecisionEngine:
    """Determines the next step for a user in a session using the task registry.

    All methods are pure: they read inputs and return an ``EngineDecision``
    with no side effects, no I/O, and no randomness.

    Proposes the next task targeting the cognitive dimension whose estimate is
    the least certain (widest 90% credible interval). If multiple dimensions are
    tied for maximum uncertainty, resolves alphabetically by task_id.

    Requirements: R-007.1, R-007.2, R-007.3
    """

    def __init__(
        self,
        registry: TaskRegistry | None = None,
        interval_fn: Callable[[str], tuple[float, float]] | None = None,
    ) -> None:
        self._registry = registry
        self._interval_fn = interval_fn

    def _get_descriptors(self, registry: TaskRegistry | None = None) -> list[TaskDescriptor]:
        reg = registry or self._registry
        if reg is None:
            return list(DEFAULT_TASK_DESCRIPTORS)
        return list(reg.list_descriptors())

    def _dimension_uncertainty(
        self,
        dimension: str,
        profile: CognitiveProfile | object | None = None,
    ) -> float:
        """Return the uncertainty (width of the 90% credible interval) for dimension."""
        if profile is not None and hasattr(profile, "credible_interval"):
            lo, hi = profile.credible_interval(dimension)
            return float(hi - lo)

        if profile is not None and isinstance(profile, CognitiveProfile):
            est = profile.dimensions.get(dimension)
            if est is not None:
                return float(est.upper - est.lower)

        if self._interval_fn is not None:
            lo, hi = self._interval_fn(dimension)
            return float(hi - lo)

        return 0.90

    def decide(
        self,
        results: list[TaskResult],
        settings: Settings,
        profile: CognitiveProfile | object | None = None,
        registry: TaskRegistry | None = None,
    ) -> EngineDecision:
        """Return the next decision for the current session.

        Parameters
        ----------
        results :
            All TaskResult objects for this session.
        settings :
            Application settings (provides ``completeness_threshold``).
        profile :
            Optional user cognitive profile or profile model.
        registry :
            Optional task registry override.

        Returns
        -------
        EngineDecision
            One of:
            - ``next_task`` -- the next task_id to run with human-readable reason
            - ``insufficient_data`` -- a required result is below threshold
            - ``complete`` -- all required tasks done and sufficient
        """
        descriptors = self._get_descriptors(registry)
        registered_task_ids = {d.task_id for d in descriptors}

        results_by_task: dict[str, TaskResult] = {
            r.task_id: r for r in results if r.task_id in registered_task_ids
        }

        # ------------------------------------------------------------------
        # Rule 1: candidate uncompleted tasks in registry order
        # ------------------------------------------------------------------
        remaining_tasks = [d for d in descriptors if d.task_id not in results_by_task]

        if remaining_tasks:
            task_evaluations: list[tuple[TaskDescriptor, str, float]] = []
            for desc in remaining_tasks:
                dim = desc.target_dimensions[0] if desc.target_dimensions else desc.task_id
                unc = self._dimension_uncertainty(dim, profile=profile)
                task_evaluations.append((desc, dim, unc))

            max_unc = -1.0
            best_task = task_evaluations[0][0]
            best_dim = task_evaluations[0][1]

            for desc, dim, unc in task_evaluations:
                if unc > max_unc:
                    max_unc = unc
                    best_task = desc
                    best_dim = dim

            label = best_dim.replace("_", " ").title()
            widths = [unc for _, _, unc in task_evaluations]
            all_same_width = len(widths) > 1 and all(abs(w - widths[0]) < 1e-5 for w in widths)

            if all_same_width:
                reason = f"We have no evidence yet for {label}, so we start there."
            else:
                reason = f"{label} is where our estimate is least certain, so we test it next."

            return EngineDecision(
                next_task=best_task.task_id,
                status="next_task",
                reason=reason,
            )

        # ------------------------------------------------------------------
        # Rule 2: all tasks done — quality check
        # ------------------------------------------------------------------
        threshold = settings.completeness_threshold
        for desc in descriptors:
            task_id = desc.task_id
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
