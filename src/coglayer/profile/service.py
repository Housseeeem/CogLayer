"""ProfileService: updates a user CognitiveProfile from scored TaskResults.

The service reads ``result.metrics`` only — it never inspects
``result.trials``.  This keeps the profile layer decoupled from raw trial
data and makes the update logic independently testable.

DIMENSION_MAPPING
-----------------
Maps task_id -> list of (dimension, outcome_metric, weight, count_metric) tuples.

The count_metric is read from result.metrics and passed as ``count`` to
``BetaProfileModel.update``; it determines how many pseudo-observations
this session contributes.  If count == 0, the update is skipped entirely.

* ``response_inhibition`` (task ``go_no_go``)
  - outcome metric: ``nogo_accuracy``        weight: 1.0
  - count  metric:  ``nogo_valid_count``
  ``nogo_accuracy`` isolates inhibition performance from Go-trial RT.
  ``nogo_valid_count`` is the number of valid No-Go trials, so a session
  with more No-Go trials moves the profile more than one with fewer.

* ``sequential_visual_memory`` (task ``sequence_span``)
  - outcome metric: ``correct_sequences_ratio``    weight: 1.0
  - count  metric:  ``valid_sequence_count``
  The fraction of sequences recalled correctly in full order directly
  measures visual working memory span.

Requirements: R-006.1, R-006.2, R-006.3
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Final

from coglayer.core.models import (
    CognitiveProfile,
    DimensionEstimate,
    Evidence,
    TaskDescriptor,
    TaskResult,
)
from coglayer.core.protocols import TaskRegistry
from coglayer.core.tasks import ALL_TASK_DESCRIPTORS
from coglayer.profile.model import DEFAULT_FORGETTING_FACTOR, BetaProfileModel

__all__ = [
    "DIMENSION_MAPPING",
    "ProfileService",
    "derive_dimension_mapping",
    "derive_dimension_mapping_from_descriptors",
]

# ---------------------------------------------------------------------------
# Dimension mapping
# ---------------------------------------------------------------------------

# Each entry: task_id -> list of (dimension, outcome_metric, weight, count_metric)
# weight scales n_eff = weight * min(count, MAX_PSEUDO_COUNT).
DimMapping = tuple[str, str, float, str]


def derive_dimension_mapping_from_descriptors(
    descriptors: Iterable[TaskDescriptor],
) -> dict[str, list[DimMapping]]:
    """Derive task-to-dimension mappings from task descriptors (single source of truth)."""
    mapping: dict[str, list[DimMapping]] = {}
    for desc in descriptors:
        primary = desc.primary_metric
        if not primary:
            continue
        weight_val = desc.parameters.get("weight", 1.0)
        weight = float(weight_val) if isinstance(weight_val, (int, float, str)) else 1.0
        count_m = desc.count_metric or str(desc.parameters.get("count_metric", ""))
        entries: list[DimMapping] = []
        for dim in desc.target_dimensions:
            entries.append((dim, primary, weight, count_m))
        if entries:
            mapping[desc.task_id] = entries
    return mapping


def derive_dimension_mapping(
    registry: TaskRegistry,
) -> dict[str, list[DimMapping]]:
    """Derive dimension mappings from a TaskRegistry."""
    descriptors: list[TaskDescriptor] = []
    for task_id in registry.list_ids():
        try:
            descriptors.append(registry.get(task_id, "1.0"))
        except KeyError:
            continue
    return derive_dimension_mapping_from_descriptors(descriptors)


# Derived from ALL_TASK_DESCRIPTORS (no duplicated literals)
DIMENSION_MAPPING: Final[dict[str, list[DimMapping]]] = derive_dimension_mapping_from_descriptors(
    ALL_TASK_DESCRIPTORS
)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ProfileService:
    """Updates a CognitiveProfile from new TaskResult evidence.

    Only ``result.metrics`` is read; ``result.trials`` is never accessed.

    Parameters
    ----------
    lambda_ :
        Forgetting factor passed to BetaProfileModel.  Default 0.98.
    registry :
        Optional TaskRegistry to look up descriptors dynamically.
    """

    def __init__(
        self,
        lambda_: float = DEFAULT_FORGETTING_FACTOR,
        registry: TaskRegistry | None = None,
    ) -> None:
        self._lambda = lambda_
        self._registry = registry

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def update_from_result(
        self,
        profile: CognitiveProfile,
        result: TaskResult,
        session_type: str = "assessment",
    ) -> CognitiveProfile:
        """Return an updated profile incorporating evidence from *result*.

        Only dimensions registered in the task descriptor or DIMENSION_MAPPING for
        ``result.task_id`` are updated.  Unknown task_ids are silently
        ignored.  If count == 0 for a dimension, that dimension is skipped
        (no forgetting, no Evidence record, no n_evidence increment).

        Calibration sessions (session_type="calibration") are skipped and
        the profile is returned unchanged to isolate calibration from the
        Bayesian cognitive profile.

        Parameters
        ----------
        profile :
            Current profile (treated as read-only; a new profile is returned).
        result :
            Scored task result.  Only ``result.metrics`` is read.
        session_type :
            Type of session ("assessment" or "calibration"). Calibration sessions
            are skipped to prevent Bayesian profile updates.

        Returns
        -------
        CognitiveProfile
            Updated profile with new dimensions, evidence_history,
            data_quality dict, and uncertainty dict. Unchanged for calibration.
        """
        # Skip Bayesian update for calibration sessions
        if session_type == "calibration":
            return profile
        mappings: list[DimMapping] = []
        if self._registry is not None:
            desc: TaskDescriptor | None = None
            try:
                desc = self._registry.get(result.task_id, result.task_version)
            except KeyError:
                if "unknown_task_version" not in result.data_quality.anomalies:
                    result.data_quality.anomalies.append("unknown_task_version")
                return profile
            if desc is not None:
                primary = desc.primary_metric
                weight_val = desc.parameters.get("weight", 1.0)
                weight = float(weight_val) if isinstance(weight_val, (int, float, str)) else 1.0
                count_m = desc.count_metric or str(desc.parameters.get("count_metric", ""))
                for dim in desc.target_dimensions:
                    if primary:
                        mappings.append((dim, primary, weight, count_m))
        else:
            if result.task_version != "1.0":
                if "unknown_task_version" not in result.data_quality.anomalies:
                    result.data_quality.anomalies.append("unknown_task_version")
                return profile
            mappings = DIMENSION_MAPPING.get(result.task_id, [])

        if not mappings or result.data_quality.anomalies:
            return profile

        # Build a BetaProfileModel seeded from persisted alpha/beta
        model = BetaProfileModel(lambda_=self._lambda)
        for dim, est in profile.dimensions.items():
            model.seed_dimension(
                dimension=dim,
                alpha=est.alpha,
                beta=est.beta_param,
                n_evidence=est.n_evidence,
                last_update=est.last_update,
            )

        new_evidence: list[Evidence] = []

        for dimension, outcome_metric, weight, count_metric in mappings:
            raw_outcome = result.metrics.get(outcome_metric)
            if count_metric:
                raw_count = result.metrics.get(count_metric)
            elif result.data_quality.valid_trials > 0:
                raw_count = float(result.data_quality.valid_trials)
            else:
                raw_count = None

            if raw_outcome is None or raw_count is None:
                continue  # required metric absent — skip
            outcome = float(raw_outcome)
            count = float(raw_count)

            if not (0.0 <= outcome <= 1.0):
                continue  # out-of-range — skip (defensive)

            prev_n = model.n_evidence(dimension)
            model.update(
                dimension=dimension,
                outcome=outcome,
                weight=weight,
                count=count,
            )
            new_n = model.n_evidence(dimension)

            # Only append evidence if update actually ran (count > 0)
            if new_n > prev_n:
                new_evidence.append(
                    Evidence(
                        dimension=dimension,
                        outcome=outcome,
                        source="active",
                        weight=weight * min(count, 20.0),
                        timestamp=datetime.now(UTC),
                        reason_code=f"{result.task_id}:{outcome_metric}",
                        task_id=result.task_id,
                        session_id=result.session_id,
                        task_version=result.task_version,
                    )
                )

        # Build updated dimension estimates, data_quality, uncertainty dicts
        new_dimensions = dict(profile.dimensions)
        new_data_quality = dict(profile.data_quality)
        new_uncertainty = dict(profile.uncertainty)

        for dimension, _outcome_metric, _weight, _count_metric in mappings:
            n = model.n_evidence(dimension)
            if n == 0:
                continue  # no update happened for this dimension
            lower, upper = model.credible_interval(dimension)
            mean_val = model.mean(dimension)
            alpha_val, beta_val = model.get_state(dimension)

            new_dimensions[dimension] = DimensionEstimate(
                dimension=dimension,
                mean=mean_val,
                lower=lower,
                upper=upper,
                n_evidence=n,
                last_update=model.last_update(dimension),
                alpha=alpha_val,
                beta_param=beta_val,
            )
            new_data_quality[dimension] = result.data_quality
            new_uncertainty[dimension] = upper - mean_val

        return CognitiveProfile(
            user_id=profile.user_id,
            dimensions=new_dimensions,
            evidence_history=list(profile.evidence_history) + new_evidence,
            data_quality=new_data_quality,
            uncertainty=new_uncertainty,
        )
