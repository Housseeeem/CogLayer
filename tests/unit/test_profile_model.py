"""Unit and property tests for BetaProfileModel.

Task 10.3 — unit tests and property-based tests.
Requirements: R-006.1, R-006.2, R-006.3
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from coglayer.profile.model import DEFAULT_FORGETTING_FACTOR, MAX_PSEUDO_COUNT, BetaProfileModel

# ---------------------------------------------------------------------------
# Hand-derived exact tests  (lambda_=1.0 so forgetting is zero)
# ---------------------------------------------------------------------------


def test_exact_three_trial_one_correct() -> None:
    """3 valid No-Go, 1 correct: outcome=1/3, count=3 -> mean=2/5=0.4.

    Hand derivation (lambda_=1.0, weight=1.0):
      Prior: alpha=1, beta=1
      n_eff = 1.0 * min(3, 20) = 3
      alpha = 1 + 3 * (1/3) = 2
      beta  = 1 + 3 * (2/3) = 3
      mean  = 2 / (2+3) = 0.4
    """
    m = BetaProfileModel(lambda_=1.0)
    m.update("dim", outcome=1 / 3, weight=1.0, count=3.0)
    assert m.mean("dim") == pytest.approx(2 / 5)
    alpha, beta = m.get_state("dim")
    assert alpha == pytest.approx(2.0)
    assert beta == pytest.approx(3.0)


def test_exact_twelve_trial_four_correct() -> None:
    """12 valid No-Go, 4 correct: outcome=1/3, count=12 -> mean=5/14.

    Hand derivation (lambda_=1.0, weight=1.0):
      n_eff = 1.0 * min(12, 20) = 12
      alpha = 1 + 12 * (1/3) = 5
      beta  = 1 + 12 * (2/3) = 9
      mean  = 5 / (5+9) = 5/14
    """
    m = BetaProfileModel(lambda_=1.0)
    m.update("dim", outcome=1 / 3, weight=1.0, count=12.0)
    assert m.mean("dim") == pytest.approx(5 / 14)
    alpha, beta = m.get_state("dim")
    assert alpha == pytest.approx(5.0)
    assert beta == pytest.approx(9.0)


def test_three_trial_moves_mean_less_than_twelve_trial_same_accuracy() -> None:
    """3-trial session moves mean from 0.5 less than 12-trial at same accuracy.

    Both sessions have outcome=1/3 < 0.5.  The 12-trial session contributes
    more pseudo-observations so it pulls the mean further from 0.5.
      3-trial:  |mean - 0.5| = |0.4 - 0.5| = 0.1
      12-trial: |mean - 0.5| = |5/14 - 0.5| ≈ 0.143
    """
    m3 = BetaProfileModel(lambda_=1.0)
    m3.update("dim", outcome=1 / 3, weight=1.0, count=3.0)
    m12 = BetaProfileModel(lambda_=1.0)
    m12.update("dim", outcome=1 / 3, weight=1.0, count=12.0)
    deviation3 = abs(m3.mean("dim") - 0.5)
    deviation12 = abs(m12.mean("dim") - 0.5)
    assert deviation3 < deviation12


def test_count_zero_is_noop() -> None:
    """count=0 leaves the model unchanged (no forgetting, no alpha/beta change)."""
    m = BetaProfileModel(lambda_=1.0)
    m.update("dim", outcome=0.9, weight=1.0, count=0.0)
    assert m.mean("dim") == pytest.approx(0.5)
    assert m.n_evidence("dim") == 0
    alpha, beta = m.get_state("dim")
    assert alpha == pytest.approx(1.0)
    assert beta == pytest.approx(1.0)


def test_max_pseudo_count_caps_influence() -> None:
    """count > MAX_PSEUDO_COUNT is capped: same as count == MAX_PSEUDO_COUNT."""
    m_capped = BetaProfileModel(lambda_=1.0)
    m_capped.update("dim", outcome=0.8, weight=1.0, count=MAX_PSEUDO_COUNT)
    m_over = BetaProfileModel(lambda_=1.0)
    m_over.update("dim", outcome=0.8, weight=1.0, count=MAX_PSEUDO_COUNT + 100)
    assert m_capped.mean("dim") == pytest.approx(m_over.mean("dim"))


# ---------------------------------------------------------------------------
# Basic unit tests
# ---------------------------------------------------------------------------


def test_default_forgetting_factor() -> None:
    """DEFAULT_FORGETTING_FACTOR is in (0, 1]."""
    assert 0.0 < DEFAULT_FORGETTING_FACTOR <= 1.0


def test_initial_mean_is_half() -> None:
    """Uninitialised dimension has mean 0.5 (uniform prior Beta(1,1))."""
    m = BetaProfileModel()
    assert m.mean("new_dim") == pytest.approx(0.5)


def test_initial_credible_interval_non_degenerate() -> None:
    """90% CI for uniform prior is non-degenerate and contains 0.5."""
    m = BetaProfileModel()
    lo, hi = m.credible_interval("new_dim")
    assert 0.0 < lo < 0.5 < hi < 1.0


def test_interval_contains_mean() -> None:
    """Credible interval always contains the mean."""
    m = BetaProfileModel()
    m.update("dim", outcome=0.7, weight=2.0, count=5.0)
    lo, hi = m.credible_interval("dim")
    assert lo <= m.mean("dim") <= hi


def test_high_outcome_shifts_mean_up() -> None:
    """Repeated high-outcome evidence shifts mean toward 1."""
    m = BetaProfileModel(lambda_=1.0)
    for _ in range(10):
        m.update("dim", outcome=0.9, weight=1.0, count=5.0)
    assert m.mean("dim") > 0.7


def test_low_outcome_shifts_mean_down() -> None:
    """Repeated low-outcome evidence shifts mean toward 0."""
    m = BetaProfileModel(lambda_=1.0)
    for _ in range(10):
        m.update("dim", outcome=0.1, weight=1.0, count=5.0)
    assert m.mean("dim") < 0.3


def test_more_count_moves_mean_more() -> None:
    """Larger count moves the mean further from 0.5 (at same outcome)."""
    m_small = BetaProfileModel(lambda_=1.0)
    m_large = BetaProfileModel(lambda_=1.0)
    m_small.update("dim", outcome=0.8, weight=1.0, count=1.0)
    m_large.update("dim", outcome=0.8, weight=1.0, count=10.0)
    assert m_large.mean("dim") > m_small.mean("dim")


def test_more_evidence_narrows_interval() -> None:
    """Adding a second observation does not widen the credible interval."""
    m = BetaProfileModel(lambda_=1.0)
    m.update("dim", outcome=0.6, weight=1.0, count=5.0)
    lo1, hi1 = m.credible_interval("dim")
    width1 = hi1 - lo1
    m.update("dim", outcome=0.6, weight=1.0, count=5.0)
    lo2, hi2 = m.credible_interval("dim")
    width2 = hi2 - lo2
    assert width2 <= width1


def test_forgetting_near_zero_lambda_resets_state() -> None:
    """With lambda_ near 0, forgetting almost fully resets state."""
    m = BetaProfileModel(lambda_=1e-9)
    m.update("dim", outcome=0.9, weight=1.0, count=10.0)
    # Second update: forgetting resets alpha-1 and beta-1 to ~0
    m.update("dim", outcome=0.5, weight=1.0, count=2.0)
    # After near-full reset to (1,1), update with outcome=0.5, count=2, n_eff=2:
    # alpha ≈ 1 + 2*0.5 = 2, beta ≈ 1 + 2*0.5 = 2 → mean = 0.5
    assert m.mean("dim") == pytest.approx(0.5, abs=0.01)


def test_invalid_lambda_raises() -> None:
    """lambda_ outside (0, 1] raises ValueError."""
    with pytest.raises(ValueError, match="lambda_"):
        BetaProfileModel(lambda_=0.0)
    with pytest.raises(ValueError, match="lambda_"):
        BetaProfileModel(lambda_=1.1)


def test_invalid_outcome_raises() -> None:
    """outcome outside [0, 1] raises ValueError."""
    m = BetaProfileModel()
    with pytest.raises(ValueError, match="outcome"):
        m.update("dim", outcome=1.5, weight=1.0, count=5.0)
    with pytest.raises(ValueError, match="outcome"):
        m.update("dim", outcome=-0.1, weight=1.0, count=5.0)


def test_invalid_weight_raises() -> None:
    """weight <= 0 raises ValueError."""
    m = BetaProfileModel()
    with pytest.raises(ValueError, match="weight"):
        m.update("dim", outcome=0.5, weight=0.0, count=5.0)
    with pytest.raises(ValueError, match="weight"):
        m.update("dim", outcome=0.5, weight=-1.0, count=5.0)


def test_invalid_count_raises() -> None:
    """count < 0 raises ValueError."""
    m = BetaProfileModel()
    with pytest.raises(ValueError, match="count"):
        m.update("dim", outcome=0.5, weight=1.0, count=-1.0)


def test_n_evidence_increments() -> None:
    """n_evidence increments by 1 per update (when count > 0)."""
    m = BetaProfileModel()
    assert m.n_evidence("dim") == 0
    m.update("dim", outcome=0.5, weight=1.0, count=3.0)
    assert m.n_evidence("dim") == 1
    m.update("dim", outcome=0.5, weight=1.0, count=3.0)
    assert m.n_evidence("dim") == 2


def test_n_evidence_not_incremented_when_count_zero() -> None:
    """n_evidence does NOT increment when count == 0."""
    m = BetaProfileModel()
    m.update("dim", outcome=0.5, weight=1.0, count=0.0)
    assert m.n_evidence("dim") == 0


def test_last_update_is_timezone_aware() -> None:
    """last_update returns a timezone-aware datetime."""
    m = BetaProfileModel()
    m.update("dim", outcome=0.5, weight=1.0, count=3.0)
    ts = m.last_update("dim")
    assert ts.tzinfo is not None


def test_independent_dimensions() -> None:
    """Updating one dimension does not affect another."""
    m = BetaProfileModel(lambda_=1.0)
    m.update("dim_a", outcome=0.9, weight=1.0, count=5.0)
    assert m.mean("dim_b") == pytest.approx(0.5)


def test_seed_dimension_and_get_state_round_trip() -> None:
    """seed_dimension -> get_state round-trips exactly."""
    m = BetaProfileModel()
    m.seed_dimension("dim", alpha=3.0, beta=7.0, n_evidence=2, last_update=pytest.approx)  # type: ignore[arg-type]
    # Use a real datetime
    from datetime import UTC, datetime

    ts = datetime(2024, 1, 1, tzinfo=UTC)
    m.seed_dimension("dim", alpha=3.0, beta=7.0, n_evidence=2, last_update=ts)
    alpha, beta = m.get_state("dim")
    assert alpha == pytest.approx(3.0)
    assert beta == pytest.approx(7.0)
    assert m.n_evidence("dim") == 2
    assert m.last_update("dim") == ts


# ---------------------------------------------------------------------------
# Two-session identity test: ProfileService vs BetaProfileModel directly
# ---------------------------------------------------------------------------


def test_two_sessions_via_service_equals_direct_model() -> None:
    """Two sessions through ProfileService produce the same alpha/beta as direct model updates.

    Session 1: nogo_accuracy=1/3, nogo_valid_count=3  -> alpha=2, beta=3
    Session 2: same result again                       -> alpha=2+(1+2*1/3)=?, computed directly

    We verify that the DimensionEstimate alpha/beta stored after two
    ProfileService.update_from_result calls equals two BetaProfileModel.update calls.
    """
    from coglayer.core.models import CognitiveProfile, DataQuality, TaskResult

    lambda_ = 1.0  # no forgetting for clarity
    outcome = 1 / 3
    count = 3.0

    # Direct model path
    m = BetaProfileModel(lambda_=lambda_)
    m.update("response_inhibition", outcome=outcome, weight=1.0, count=count)
    m.update("response_inhibition", outcome=outcome, weight=1.0, count=count)
    model_alpha, model_beta = m.get_state("response_inhibition")

    # ProfileService path
    from coglayer.profile.service import ProfileService

    dq = DataQuality(valid_trials=3, total_trials=10, completeness=0.3, anomalies=[])
    result = TaskResult(
        task_id="go_no_go",
        task_version="1.0",
        session_id="s1",
        user_id="u1",
        trials=[],
        metrics={"nogo_accuracy": outcome, "nogo_valid_count": count},
        signals=[],
        target_dimensions=["response_inhibition"],
        data_quality=dq,
        uncertainty=None,
    )
    empty_profile = CognitiveProfile(
        user_id="u1", dimensions={}, evidence_history=[], data_quality={}, uncertainty={}
    )

    svc = ProfileService(lambda_=lambda_)
    p1 = svc.update_from_result(empty_profile, result)
    p2 = svc.update_from_result(p1, result)

    est = p2.dimensions["response_inhibition"]
    assert est.alpha == pytest.approx(model_alpha)
    assert est.beta_param == pytest.approx(model_beta)
    assert est.mean == pytest.approx(m.mean("response_inhibition"))
    lo_m, hi_m = m.credible_interval("response_inhibition")
    assert est.lower == pytest.approx(lo_m)
    assert est.upper == pytest.approx(hi_m)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    outcome=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    weight=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
    count=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
    lambda_=st.floats(min_value=0.001, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_property_mean_in_unit_interval(
    outcome: float, weight: float, count: float, lambda_: float
) -> None:
    """Property: mean always stays in [0, 1] after any valid update."""
    m = BetaProfileModel(lambda_=lambda_)
    m.update("dim", outcome=outcome, weight=weight, count=count)
    assert 0.0 <= m.mean("dim") <= 1.0


@settings(max_examples=200)
@given(
    outcome=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    weight=st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
    count=st.floats(min_value=0.01, max_value=50.0, allow_nan=False, allow_infinity=False),
    lambda_=st.floats(min_value=0.001, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_property_interval_contains_mean(
    outcome: float, weight: float, count: float, lambda_: float
) -> None:
    """Property: credible interval always contains the mean (when count > 0)."""
    m = BetaProfileModel(lambda_=lambda_)
    m.update("dim", outcome=outcome, weight=weight, count=count)
    lo, hi = m.credible_interval("dim")
    mean_val = m.mean("dim")
    assert lo <= mean_val + 1e-12
    assert mean_val <= hi + 1e-12


@settings(max_examples=100)
@given(
    outcome=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    c1=st.floats(min_value=1.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    c2=st.floats(min_value=1.0, max_value=20.0, allow_nan=False, allow_infinity=False),
)
def test_property_more_evidence_does_not_widen_interval(
    outcome: float, c1: float, c2: float
) -> None:
    """Property: adding a second observation never widens the CI (lambda_=1.0)."""
    m = BetaProfileModel(lambda_=1.0)
    m.update("dim", outcome=outcome, weight=1.0, count=c1)
    lo1, hi1 = m.credible_interval("dim")
    width1 = hi1 - lo1
    m.update("dim", outcome=outcome, weight=1.0, count=c2)
    lo2, hi2 = m.credible_interval("dim")
    width2 = hi2 - lo2
    assert width2 <= width1 + 1e-10  # small tolerance for float precision
