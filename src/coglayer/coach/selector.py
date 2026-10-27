"""Adaptive daily cognitive game selector.

Deterministic, explainable, and testable service recommending 2 or 3 distinct
cognitive activities per day for each user.
Integrates historical performance, recency, data quality, Brain Twin signals,
and optional coach context without clinical interpretation.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

from coglayer.core.brain_twin import BrainTwinSignal, BrainTwinState
from coglayer.core.models import (
    AdaptiveDailyPlan,
    AdaptiveGameRecommendation,
    AdaptiveRecommendationCriteria,
    Session,
    TaskDescriptor,
    TaskResult,
)
from coglayer.core.tasks import ALL_TASK_DESCRIPTORS

__all__ = ["AdaptiveGameSelector"]

_DEFAULT_TRIO: Final[tuple[str, str, str]] = ("go_no_go", "digit_span", "stroop")


class AdaptiveGameSelector:
    """Selects 2 or 3 distinct cognitive activities for a daily session.

    Pure deterministic decision logic: no network, no LLM, no database access.
    """

    def __init__(
        self,
        descriptors: Sequence[TaskDescriptor] | None = None,
    ) -> None:
        self._descriptors = list(descriptors or ALL_TASK_DESCRIPTORS)

    def select_daily_plan(
        self,
        criteria: AdaptiveRecommendationCriteria,
        results: Sequence[TaskResult] = (),
        sessions: Sequence[Session] = (),
        brain_twin_signal: BrainTwinSignal | None = None,
    ) -> AdaptiveDailyPlan:
        """Generate a deterministic daily plan based on authorized context.

        Parameters
        ----------
        criteria :
            User parameters, target count, date, preferences, and exclusions.
        results :
            Historical task results for this user.
        sessions :
            Historical sessions for this user.
        brain_twin_signal :
            Optional non-clinical Brain Twin baseline signal.

        Returns
        -------
        AdaptiveDailyPlan
            The recommended daily plan.
        """
        plan_date = criteria.plan_date or datetime.now(UTC).strftime("%Y-%m-%d")
        seed_hash = hashlib.sha256(f"{criteria.user_id}:{plan_date}".encode()).hexdigest()
        seed = int(seed_hash, 16) % 1_000_000

        target_count = max(2, min(3, criteria.target_game_count))
        excluded = set(criteria.excluded_task_ids)
        available_descriptors = [d for d in self._descriptors if d.task_id not in excluded]

        if not available_descriptors:
            return AdaptiveDailyPlan(
                user_id=criteria.user_id,
                plan_date=plan_date,
                recommendations=[],
                deterministic_seed=seed,
                session_id=criteria.session_id,
                status="generated",
                factors_used=["no_available_tasks"],
                fallback_strategy="empty_candidates_fallback",
                is_personalized=False,
            )

        # ------------------------------------------------------------------
        # Case 1: No history (New user)
        # ------------------------------------------------------------------
        if not results:
            return self._select_initial_discovery_plan(
                criteria=criteria,
                plan_date=plan_date,
                seed=seed,
                target_count=target_count,
                available_descriptors=available_descriptors,
            )

        # ------------------------------------------------------------------
        # Case 2: Insufficient or low-quality history
        # ------------------------------------------------------------------
        valid_results = [r for r in results if r.data_quality.completeness >= 0.50]
        if not valid_results:
            return self._select_low_quality_fallback_plan(
                criteria=criteria,
                plan_date=plan_date,
                seed=seed,
                target_count=target_count,
                available_descriptors=available_descriptors,
            )

        # ------------------------------------------------------------------
        # Case 3: History available — balanced adaptive selection
        # ------------------------------------------------------------------
        return self._select_personalized_plan(
            criteria=criteria,
            plan_date=plan_date,
            seed=seed,
            target_count=target_count,
            available_descriptors=available_descriptors,
            results=valid_results,
            sessions=sessions,
            brain_twin_signal=brain_twin_signal,
        )

    # ----------------------------------------------------------------------
    # Helper: Initial discovery session for new users
    # ----------------------------------------------------------------------
    def _select_initial_discovery_plan(
        self,
        criteria: AdaptiveRecommendationCriteria,
        plan_date: str,
        seed: int,
        target_count: int,
        available_descriptors: list[TaskDescriptor],
    ) -> AdaptiveDailyPlan:
        chosen_descriptors: list[TaskDescriptor] = []
        covered_dims: set[str] = set()

        # Try default introductory trio first
        by_id = {d.task_id: d for d in available_descriptors}
        for task_id in _DEFAULT_TRIO:
            if len(chosen_descriptors) >= target_count:
                break
            desc = by_id.get(task_id)
            if desc is not None:
                dim = desc.target_dimensions[0] if desc.target_dimensions else "general"
                if dim not in covered_dims:
                    chosen_descriptors.append(desc)
                    covered_dims.add(dim)

        # Fill remaining slots with diversity from available descriptors
        for desc in available_descriptors:
            if len(chosen_descriptors) >= target_count:
                break
            if desc in chosen_descriptors:
                continue
            dim = desc.target_dimensions[0] if desc.target_dimensions else "general"
            if dim not in covered_dims:
                chosen_descriptors.append(desc)
                covered_dims.add(dim)

        # Fallback if dimensions are saturated
        for desc in available_descriptors:
            if len(chosen_descriptors) >= target_count:
                break
            if desc not in chosen_descriptors:
                chosen_descriptors.append(desc)

        recommendations: list[AdaptiveGameRecommendation] = []
        for desc in chosen_descriptors:
            dim = desc.target_dimensions[0] if desc.target_dimensions else "general"
            dim_label = dim.replace("_", " ").title()
            task_version = desc.version or "1.0"
            recommendations.append(
                AdaptiveGameRecommendation(
                    task_id=desc.task_id,
                    rationale=f"Introductory exploration of {dim_label} for new practice.",
                    target_dimension=dim,
                    difficulty_level="introductory",
                    task_version=task_version,
                )
            )

        factors_used = ["initial_diversity", "introductory_baseline"]
        if criteria.subjective_feedback:
            feedback_lower = criteria.subjective_feedback.lower()
            fatigue_terms = ("fatigue", "tired", "exhausted", "low energy")
            if any(term in feedback_lower for term in fatigue_terms):
                factors_used.append("subjective_fatigue_adaptation")

        return AdaptiveDailyPlan(
            user_id=criteria.user_id,
            plan_date=plan_date,
            recommendations=recommendations,
            deterministic_seed=seed,
            session_id=criteria.session_id,
            status="generated",
            factors_used=factors_used,
            fallback_strategy="initial_session_default",
            is_personalized=False,
        )

    # ----------------------------------------------------------------------
    # Helper: Insufficient data / low quality fallback
    # ----------------------------------------------------------------------
    def _select_low_quality_fallback_plan(
        self,
        criteria: AdaptiveRecommendationCriteria,
        plan_date: str,
        seed: int,
        target_count: int,
        available_descriptors: list[TaskDescriptor],
    ) -> AdaptiveDailyPlan:
        chosen_descriptors: list[TaskDescriptor] = []
        covered_dims: set[str] = set()

        for desc in available_descriptors:
            if len(chosen_descriptors) >= target_count:
                break
            dim = desc.target_dimensions[0] if desc.target_dimensions else "general"
            if dim not in covered_dims:
                chosen_descriptors.append(desc)
                covered_dims.add(dim)

        for desc in available_descriptors:
            if len(chosen_descriptors) >= target_count:
                break
            if desc not in chosen_descriptors:
                chosen_descriptors.append(desc)

        recommendations: list[AdaptiveGameRecommendation] = []
        for desc in chosen_descriptors:
            dim = desc.target_dimensions[0] if desc.target_dimensions else "general"
            dim_label = dim.replace("_", " ").title()
            recommendations.append(
                AdaptiveGameRecommendation(
                    task_id=desc.task_id,
                    rationale=(
                        f"Provides an opportunity to obtain a complete measurement of "
                        f"{dim_label} under standard conditions."
                    ),
                    target_dimension=dim,
                    difficulty_level="standard",
                    task_version=desc.version or "1.0",
                )
            )

        return AdaptiveDailyPlan(
            user_id=criteria.user_id,
            plan_date=plan_date,
            recommendations=recommendations,
            deterministic_seed=seed,
            session_id=criteria.session_id,
            status="generated",
            factors_used=["data_quality_verification", "diversity"],
            fallback_strategy="data_sufficiency_fallback",
            is_personalized=False,
        )

    # ----------------------------------------------------------------------
    # Helper: Personalized selection with history
    # ----------------------------------------------------------------------
    def _select_personalized_plan(
        self,
        criteria: AdaptiveRecommendationCriteria,
        plan_date: str,
        seed: int,
        target_count: int,
        available_descriptors: list[TaskDescriptor],
        results: Sequence[TaskResult],
        sessions: Sequence[Session],
        brain_twin_signal: BrainTwinSignal | None,
    ) -> AdaptiveDailyPlan:
        factors_used: list[str] = ["history_performance", "diversity"]
        fallback_strategy: str | None = None

        # Analyze task history
        results_by_task: dict[str, list[TaskResult]] = {}
        for r in results:
            results_by_task.setdefault(r.task_id, []).append(r)

        # Subjective feedback context (optional, non-clinical)
        is_fatigued = False
        if criteria.subjective_feedback:
            feedback_lower = criteria.subjective_feedback.lower()
            fatigue_terms = ("fatigue", "tired", "exhausted", "low energy")
            if any(term in feedback_lower for term in fatigue_terms):
                is_fatigued = True
                factors_used.append("subjective_fatigue_adaptation")

        # Brain Twin context
        variation_flagged = False
        if brain_twin_signal is not None:
            if brain_twin_signal.state is BrainTwinState.VARIATION_FLAGGED:
                variation_flagged = True
                factors_used.append("brain_twin_variation_adjustment")
            elif brain_twin_signal.state is BrainTwinState.NO_VARIATION:
                factors_used.append("brain_twin_stable_baseline")
            elif brain_twin_signal.state is BrainTwinState.INSUFFICIENT_DATA:
                factors_used.append("brain_twin_insufficient_data")

        # Recent tasks from most recent session to prevent excessive repetition
        recent_task_ids: set[str] = set()
        completed_sessions = [s for s in sessions if s.completed_tasks]
        if completed_sessions:
            sorted_sessions = sorted(completed_sessions, key=lambda s: s.start_time, reverse=True)
            recent_task_ids.update(sorted_sessions[0].completed_tasks)

        # Score each candidate task
        scored_candidates: list[tuple[float, TaskDescriptor]] = []
        for desc in available_descriptors:
            task_id = desc.task_id
            dim = desc.target_dimensions[0] if desc.target_dimensions else "general"
            task_hist = results_by_task.get(task_id, [])

            score = 10.0

            # Prevention of excessive repetition (recency penalty)
            if task_id in recent_task_ids:
                score -= 6.0
                if "recency_prevention" not in factors_used:
                    factors_used.append("recency_prevention")

            # Continuity / Fresh measurement bonus
            if not task_hist:
                # Opportunity to explore new task
                score += 3.0
            else:
                # Task practiced previously — steady continuity
                score += 1.5

            # User preference matching
            if criteria.target_dimensions and dim in criteria.target_dimensions:
                score += 5.0
                if "user_preference" not in factors_used:
                    factors_used.append("user_preference")

            # Brain Twin adjustment: prioritize consolidating Go/No-Go reference
            if variation_flagged and task_id == "go_no_go":
                score += 8.0

            scored_candidates.append((score, desc))

        # Deterministic sorting: by score descending, then tie-break alphabetically by task_id
        scored_candidates.sort(key=lambda item: (-item[0], item[1].task_id))

        # Select tasks ensuring dimension diversity
        chosen_descriptors: list[TaskDescriptor] = []
        covered_dims: set[str] = set()

        for _, desc in scored_candidates:
            if len(chosen_descriptors) >= target_count:
                break
            dim = desc.target_dimensions[0] if desc.target_dimensions else "general"
            if dim not in covered_dims:
                chosen_descriptors.append(desc)
                covered_dims.add(dim)

        # If not enough distinct dimensions, fill from next best remaining
        for _, desc in scored_candidates:
            if len(chosen_descriptors) >= target_count:
                break
            if desc not in chosen_descriptors:
                chosen_descriptors.append(desc)

        # Build recommendations
        recommendations: list[AdaptiveGameRecommendation] = []
        for desc in chosen_descriptors:
            task_id = desc.task_id
            dim = desc.target_dimensions[0] if desc.target_dimensions else "general"
            dim_label = dim.replace("_", " ").title()
            task_hist = results_by_task.get(task_id, [])

            # Difficulty assignment
            if is_fatigued:
                difficulty = "introductory"
            elif not task_hist:
                difficulty = "introductory"
            elif len(task_hist) >= 3 and task_hist[-1].data_quality.completeness >= 0.90:
                difficulty = "challenge"
            else:
                difficulty = "standard"

            # Rationale construction
            if variation_flagged and task_id == "go_no_go":
                rationale = (
                    "Selected to consolidate reference measurements "
                    "following an observed variation."
                )
            elif is_fatigued:
                rationale = (
                    f"Targets {dim_label} with introductory pacing to accommodate reported fatigue."
                )
            elif not task_hist:
                rationale = (
                    f"Introduces {dim_label} to broaden practice variety across cognitive domains."
                )
            elif task_id in recent_task_ids:
                rationale = f"Continues practice on {dim_label} with standard reinforcement."
            else:
                rationale = f"Re-engages {dim_label} with comparable exercise conditions."

            recommendations.append(
                AdaptiveGameRecommendation(
                    task_id=task_id,
                    rationale=rationale,
                    target_dimension=dim,
                    difficulty_level=difficulty,
                    task_version=desc.version or "1.0",
                )
            )

        return AdaptiveDailyPlan(
            user_id=criteria.user_id,
            plan_date=plan_date,
            recommendations=recommendations,
            deterministic_seed=seed,
            session_id=criteria.session_id,
            status="generated",
            factors_used=factors_used,
            fallback_strategy=fallback_strategy,
            is_personalized=True,
        )
