"""Bayesian Beta profile model for CogLayer.

Each cognitive dimension is modelled as a Beta(alpha, beta) distribution
over a [0, 1] outcome space.

Update rule
-----------
1. Apply forgetting: alpha' = 1 + (alpha - 1) * lambda_
                     beta'  = 1 + (beta  - 1) * lambda_
   where lambda_ is the forgetting factor (default 0.98).  This shrinks
   the posterior back toward the uniform prior Beta(1, 1) without fully
   discarding history.  With lambda_ = 1.0 there is no forgetting.

2. Compute effective pseudo-observation count:
       n_eff = weight * min(count, MAX_PSEUDO_COUNT)
   where ``count`` is the number of valid stimulus-specific trials
   (e.g. nogo_valid_count for response_inhibition) and
   MAX_PSEUDO_COUNT = 20 caps the influence of any single session.
   If ``count == 0`` the entire update is skipped (no forgetting, no
   n_evidence increment, no Evidence record appended).

3. Bayesian update (pseudo-observation approach):
       alpha += n_eff * outcome
       beta  += n_eff * (1.0 - outcome)

4. Credible interval: 90% interval from
       lower = scipy.stats.beta.ppf(0.05, alpha, beta)
       upper = scipy.stats.beta.ppf(0.95, alpha, beta)

Forgetting factor rule
----------------------
With lambda_ = 0.98 and weight = 1.0, a piece of evidence from N sessions
ago retains approximately 0.98^N of its original influence.  After 50
sessions this is ~36%.  With lambda_ = 1.0 evidence never decays
(pure accumulation).

Persisting state
----------------
``BetaProfileModel`` exposes its internal alpha/beta for each dimension via
``get_state`` so callers can persist them in ``DimensionEstimate.alpha`` and
``DimensionEstimate.beta``.  Use the ``seed_from_estimate`` classmethod or
``seed_dimension`` to reconstruct the model from persisted estimates before
the next update; this avoids lossy method-of-moments reconstruction.

Requirements: R-006.1, R-006.2, R-006.3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from scipy.stats import beta as _beta_dist

__all__ = ["DEFAULT_FORGETTING_FACTOR", "MAX_PSEUDO_COUNT", "BetaProfileModel"]

DEFAULT_FORGETTING_FACTOR: Final[float] = 0.98
"""Default exponential forgetting factor lambda_ in (0, 1]."""

MAX_PSEUDO_COUNT: Final[float] = 20.0
"""Maximum pseudo-observation count from a single session.

Caps n_eff = weight * min(count, MAX_PSEUDO_COUNT) so that a single
unusually large session does not dominate the lifetime posterior.
"""

_CI_LOWER: Final[float] = 0.05
_CI_UPPER: Final[float] = 0.95


@dataclass
class _BetaState:
    """Mutable Beta(alpha, beta) state for one dimension."""

    alpha: float = 1.0
    beta: float = 1.0
    n_evidence: int = 0
    last_update: datetime = field(default_factory=lambda: datetime.now(UTC))


class BetaProfileModel:
    """Maintains a Beta-distribution estimate for each cognitive dimension.

    Parameters
    ----------
    lambda_ :
        Forgetting factor in (0, 1].  Default 0.98.  Values closer to 1.0
        retain more history; 1.0 means no forgetting at all.
    """

    def __init__(self, lambda_: float = DEFAULT_FORGETTING_FACTOR) -> None:
        if not (0.0 < lambda_ <= 1.0):
            raise ValueError(f"lambda_ must be in (0, 1], got {lambda_!r}")
        self._lambda = lambda_
        self._states: dict[str, _BetaState] = {}

    # ------------------------------------------------------------------
    # Public interface — update
    # ------------------------------------------------------------------

    def update(
        self,
        dimension: str,
        outcome: float,
        weight: float,
        count: float,
    ) -> None:
        """Update the Beta estimate for *dimension*.

        If ``count == 0`` the update is skipped entirely (no forgetting,
        no n_evidence increment).

        Parameters
        ----------
        dimension :
            Dimension key (e.g. ``"response_inhibition"``).
        outcome :
            Normalised score in [0, 1].
        weight :
            Base evidence weight (task-level, from DIMENSION_MAPPING).
        count :
            Number of valid trials for this stimulus type (e.g.
            ``nogo_valid_count`` for response_inhibition).  If 0, the
            update is a no-op.
        """
        if not (0.0 <= outcome <= 1.0):
            raise ValueError(f"outcome must be in [0, 1], got {outcome!r}")
        if weight <= 0.0:
            raise ValueError(f"weight must be > 0, got {weight!r}")
        if count < 0.0:
            raise ValueError(f"count must be >= 0, got {count!r}")

        # count == 0: no valid trials — skip update entirely
        if count == 0.0:
            return

        state = self._states.setdefault(dimension, _BetaState())

        # Step 1: forgetting — shrink back toward uniform Beta(1, 1)
        state.alpha = 1.0 + (state.alpha - 1.0) * self._lambda
        state.beta = 1.0 + (state.beta - 1.0) * self._lambda

        # Step 2: effective pseudo-observation count (capped at MAX_PSEUDO_COUNT)
        n_eff = weight * min(count, MAX_PSEUDO_COUNT)

        # Step 3: Bayesian update (add pseudo-observations)
        state.alpha += n_eff * outcome
        state.beta += n_eff * (1.0 - outcome)
        state.n_evidence += 1
        state.last_update = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Public interface — query
    # ------------------------------------------------------------------

    def mean(self, dimension: str) -> float:
        """Posterior mean for *dimension* (0.5 if no evidence — uniform prior)."""
        s = self._states.get(dimension)
        if s is None:
            return 0.5
        return s.alpha / (s.alpha + s.beta)

    def credible_interval(self, dimension: str) -> tuple[float, float]:
        """90% credible interval (lower, upper) for *dimension*."""
        s = self._states.get(dimension)
        a, b = (s.alpha, s.beta) if s is not None else (1.0, 1.0)
        lower = float(_beta_dist.ppf(_CI_LOWER, a, b))
        upper = float(_beta_dist.ppf(_CI_UPPER, a, b))
        return lower, upper

    def n_evidence(self, dimension: str) -> int:
        """Number of evidence updates applied to *dimension*."""
        s = self._states.get(dimension)
        return 0 if s is None else s.n_evidence

    def last_update(self, dimension: str) -> datetime:
        """Timestamp of the last update to *dimension*."""
        s = self._states.get(dimension)
        return s.last_update if s is not None else datetime.now(UTC)

    def get_state(self, dimension: str) -> tuple[float, float]:
        """Return the raw (alpha, beta) parameters for *dimension*.

        Returns (1.0, 1.0) — the uniform prior — if no update has been made.
        Use this to persist state in DimensionEstimate.alpha/beta.
        """
        s = self._states.get(dimension)
        if s is None:
            return 1.0, 1.0
        return s.alpha, s.beta

    def seed_dimension(
        self, dimension: str, alpha: float, beta: float, n_evidence: int, last_update: datetime
    ) -> None:
        """Seed persisted state for *dimension* directly from stored alpha/beta.

        Call this before ``update`` to reconstruct the model from a
        persisted DimensionEstimate rather than using lossy method-of-moments.
        Overwrites any existing state for the dimension.
        """
        self._states[dimension] = _BetaState(
            alpha=alpha,
            beta=beta,
            n_evidence=n_evidence,
            last_update=last_update,
        )
