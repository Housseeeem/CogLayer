"""Tests for the transparent EMA variation signal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coglayer.core.brain_twin import (
    BrainTwinState,
    build_brain_twin_analysis,
    build_per_dimension_analysis,
    calculate_ema_signal,
)
from coglayer.core.models import Evidence


def _evidence(
    outcome: float,
    index: int,
    *,
    task_id: str = "go_no_go",
    dimension: str = "response_inhibition",
) -> Evidence:
    return Evidence(
        dimension=dimension,
        outcome=outcome,
        source="active",
        weight=1.0,
        timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index),
        reason_code=f"result-{index}",
        task_id=task_id,
        session_id=f"session-{index}",
    )


def test_ema_uses_previous_prediction_and_withholds_short_history_flags() -> None:
    result = calculate_ema_signal([10.0, 10.0, 10.0])

    assert result.status == "INSUFFICIENT_DATA"
    assert [point.prediction for point in result.points] == [10.0, 10.0, 10.0]
    assert all(not point.flagged for point in result.points)


def test_ema_flags_a_large_late_variation_after_sufficient_history() -> None:
    result = calculate_ema_signal([10.0, 10.0, 10.0, 10.0, 30.0])

    assert result.status == "AVAILABLE"
    assert result.points[-1].residual == pytest.approx(20.0)
    assert result.points[-1].flagged is True


@pytest.mark.parametrize(
    ("alpha", "sigma_multiplier", "minimum_observations"),
    [(0.0, 1.5, 4), (1.1, 1.5, 4), (0.3, 0.0, 4), (0.3, 1.5, 1)],
)
def test_ema_rejects_invalid_configuration(
    alpha: float,
    sigma_multiplier: float,
    minimum_observations: int,
) -> None:
    with pytest.raises(ValueError):
        calculate_ema_signal(
            [1.0, 2.0],
            alpha=alpha,
            sigma_multiplier=sigma_multiplier,
            minimum_observations=minimum_observations,
        )


def test_brain_twin_signal_distinguishes_insufficient_history() -> None:
    _, signal = build_brain_twin_analysis([_evidence(0.8, 0), _evidence(0.8, 1)])

    assert signal.state is BrainTwinState.INSUFFICIENT_DATA
    assert signal.comparable_observation_count == 2
    assert signal.flagged_observation_id is None


def test_brain_twin_signal_reports_no_variation() -> None:
    _, signal = build_brain_twin_analysis([_evidence(0.8, index) for index in range(4)])

    assert signal.state is BrainTwinState.NO_VARIATION
    assert signal.comparable_observation_count == 4
    assert signal.flagged_observation_id is None


def test_brain_twin_signal_associates_flag_with_source_evidence() -> None:
    evidence = [_evidence(value, index) for index, value in enumerate([0.8, 0.8, 0.8, 0.8, 0.1])]

    result, signal = build_brain_twin_analysis(evidence)

    assert result.status == "AVAILABLE"
    assert signal.state is BrainTwinState.VARIATION_FLAGGED
    assert signal.flagged_observation_id is not None
    assert "session-4" in signal.flagged_observation_id
    assert "result-4" in signal.flagged_observation_id


def test_brain_twin_signal_ignores_non_comparable_evidence() -> None:
    evidence = [_evidence(0.8, index) for index in range(4)]
    evidence.append(_evidence(0.1, 4, task_id="sequence_span"))

    _, signal = build_brain_twin_analysis(evidence)

    assert signal.state is BrainTwinState.NO_VARIATION
    assert signal.comparable_observation_count == 4


def test_brain_twin_signal_preserves_positional_identity_despite_identical_values() -> None:
    # Evidence at index 4 and index 5 share the exact same outcome value (0.1).
    # Index 4 is flagged (residual 0.7 exceeds threshold).
    # Index 5 is not flagged (residual 0.49 is within threshold).
    # The signal must associate precisely with session-4 / result-4, not session-5.
    evidence = [
        _evidence(0.8, 0),
        _evidence(0.8, 1),
        _evidence(0.8, 2),
        _evidence(0.8, 3),
        _evidence(0.1, 4),
        _evidence(0.1, 5),
    ]
    result, signal = build_brain_twin_analysis(evidence)
    assert result.status == "AVAILABLE"
    assert signal.state is BrainTwinState.VARIATION_FLAGGED
    assert signal.flagged_observation_id is not None
    assert "session-4" in signal.flagged_observation_id
    assert "result-4" in signal.flagged_observation_id
    assert "session-5" not in signal.flagged_observation_id


def test_per_dimension_analysis_keeps_observations_independent() -> None:
    response = [_evidence(0.8, index) for index in range(4)]
    response.append(_evidence(0.1, 4))
    working_memory = [
        _evidence(0.6, index, task_id="digit_span", dimension="working_memory")
        for index in range(4)
    ]

    result = build_per_dimension_analysis(response + working_memory)

    assert result.dimensions["response_inhibition"].signal.state is BrainTwinState.VARIATION_FLAGGED
    assert result.dimensions["working_memory"].signal.state is BrainTwinState.NO_VARIATION
    assert result.dimensions["working_memory"].signal.comparable_observation_count == 4
    assert result.dimensions["response_inhibition"].signal.flagged_observation_id is not None
    assert "session-4" in result.dimensions["response_inhibition"].signal.flagged_observation_id


def test_per_dimension_analysis_preserves_legacy_response_inhibition_fields() -> None:
    evidence = [_evidence(0.8, index) for index in range(4)]

    result = build_per_dimension_analysis(evidence)
    legacy, _ = build_brain_twin_analysis(evidence)

    assert result.points == legacy.points
    assert result.status == legacy.status
    assert result.alpha == legacy.alpha
    assert result.sigma_multiplier == legacy.sigma_multiplier
