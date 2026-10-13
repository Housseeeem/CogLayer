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

from datetime import UTC, datetime
from typing import Final

from coglayer.core.models import (
    CognitiveProfile,
    DimensionEstimate,
    Evidence,
    TaskResult,
)
from coglayer.profile.model import DEFAULT_FORGETTING_FACTOR, BetaProfileModel

__all__ = ["DIMENSION_MAPPING", "ProfileService"]

# ---------------------------------------------------------------------------
# Dimension mapping
# ---------------------------------------------------------------------------

# Each entry: task_id -> list of (dimension, outcome_metric, weight, count_metric)
# weight scales n_eff = weight * min(count, MAX_PSEUDO_COUNT).
DimMapping = tuple[str, str, float, str]
DIMENSION_MAPPING: Final[dict[str, list[DimMapping]]] = {
    "go_no_go": [
        # response_inhibition: outcome = nogo_accuracy, count = nogo_valid_count.
        # Uses nogo_accuracy (not overall accuracy) to isolate inhibition from RT.
        # count = nogo_valid_count so sessions with more No-Go trials contribute more.
        ("response_inhibition", "nogo_accuracy", 1.0, "nogo_valid_count"),
    ],
    "sequence_span": [
        # sequential_visual_memory: outcome = correct_sequences_ratio,
        # count = valid_sequence_count.
        # Fraction of sequences recalled in full directly measures span.
        ("sequential_visual_memory", "correct_sequences_ratio", 1.0, "valid_sequence_count"),
    ],
}


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
    """

    def __init__(self, lambda_: float = DEFAULT_FORGETTING_FACTOR) -> None:
        self._lambda = lambda_

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def update_from_result(
        self,
        profile: CognitiveProfile,
        result: TaskResult,
    ) -> CognitiveProfile:
        """Return an updated profile incorporating evidence from *result*.

        Only dimensions registered in DIMENSION_MAPPING for
        ``result.task_id`` are updated.  Unknown task_ids are silently
        ignored.  If count == 0 for a dimension, that dimension is skipped
        (no forgetting, no Evidence record, no n_evidence increment).

        Parameters
        ----------
        profile :
            Current profile (treated as read-only; a new profile is returned).
        result :
            Scored task result.  Only ``result.metrics`` is read.

        Returns
        -------
        CognitiveProfile
            Updated profile with new dimensions, evidence_history,
            data_quality dict, and uncertainty dict.
        """
        mappings = DIMENSION_MAPPING.get(result.task_id, [])
        if not mappings:
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
            raw_count = result.metrics.get(count_metric)

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
