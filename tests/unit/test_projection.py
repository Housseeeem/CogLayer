"""Tests for possible-trajectory projections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coglayer.api.routers.projection import get_projection
from coglayer.core.models import CognitiveProfile, Evidence
from coglayer.core.projection import PROJECTION_CAVEAT, project_dimension, project_evidence


def _evidence(dimension: str, outcome: float, index: int) -> Evidence:
    return Evidence(
        dimension=dimension,
        outcome=outcome,
        source="active",
        weight=1.0,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
        reason_code=f"result-{index}",
        task_id=f"{dimension}_task",
        session_id=f"session-{index}",
    )


def test_perfect_linear_data_projects_three_sessions() -> None:
    result = project_dimension("working_memory", [0.2, 0.3, 0.4, 0.5, 0.6])

    assert result.status == "AVAILABLE"
    assert result.slope == pytest.approx(0.1)
    assert [point.mean for point in result.intervals] == pytest.approx([0.7, 0.8, 0.9])
    assert all(point.lower == point.mean == point.upper for point in result.intervals)
    assert result.caveat == PROJECTION_CAVEAT


def test_noisy_data_has_wider_prediction_intervals() -> None:
    result = project_dimension("working_memory", [0.2, 0.35, 0.38, 0.58, 0.6])
    perfect = project_dimension("working_memory", [0.2, 0.3, 0.4, 0.5, 0.6])

    assert result.status == "AVAILABLE"
    assert result.intervals[0].upper - result.intervals[0].lower > (
        perfect.intervals[0].upper - perfect.intervals[0].lower
    )


def test_projection_requires_five_observations_and_rejects_constant_series() -> None:
    assert project_dimension("working_memory", [0.2] * 4).status == "INSUFFICIENT_DATA"
    constant = project_dimension("working_memory", [0.5] * 5)
    assert constant.status == "INSUFFICIENT_DATA"
    assert constant.intervals == []


def test_projection_clamps_mean_and_intervals_to_probability_range() -> None:
    result = project_dimension("working_memory", [0.8, 0.85, 0.9, 0.95, 1.0])

    assert result.status == "AVAILABLE"
    assert all(
        0.0 <= value <= 1.0
        for point in result.intervals
        for value in (point.mean, point.lower, point.upper)
    )


def test_project_evidence_groups_dimensions_and_orders_timestamps() -> None:
    evidence = [
        _evidence("working_memory", value, index)
        for index, value in reversed(list(enumerate([0.2, 0.3, 0.4, 0.5, 0.6])))
    ]

    response = project_evidence(evidence)

    assert response.projections["working_memory"].n_observations == 5
    assert response.projections["working_memory"].status == "AVAILABLE"
    assert response.projections["working_memory"].caveat == PROJECTION_CAVEAT


def test_projection_endpoint_returns_typed_response_without_test_client() -> None:
    class Consent:
        def has_consented(self, user_id: str) -> bool:
            return True

    class Repository:
        def get_profile(self, user_id: str) -> CognitiveProfile:
            return CognitiveProfile(
                user_id=user_id,
                dimensions={},
                evidence_history=[
                    _evidence("working_memory", 0.2 + index * 0.1, index) for index in range(5)
                ],
                data_quality={},
                uncertainty={},
            )

    response = get_projection("user-1", Consent(), Repository())  # type: ignore[arg-type]

    assert response.projections["working_memory"].status == "AVAILABLE"
    assert response.projections["working_memory"].caveat == PROJECTION_CAVEAT
