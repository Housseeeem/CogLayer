"""Unit tests for the pure IOI scoring service."""

from __future__ import annotations

from datetime import UTC, datetime

from coglayer.core.ioi import IOIScoringService
from coglayer.core.models import (
    IOIComponent,
    IOIEventType,
    IOIObservation,
)

TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def _observation(
    component: IOIComponent,
    opportunity_id: str,
    observed: bool,
    event_id: str | None = None,
    valid: bool = True,
) -> IOIObservation:
    event_types = {
        IOIComponent.CRITICAL_VERIFICATION: IOIEventType.VERIFICATION_OPPORTUNITY,
        IOIComponent.CLARIFICATION: IOIEventType.CLARIFICATION_OPPORTUNITY,
        IOIComponent.ITERATION: IOIEventType.ITERATION_OPPORTUNITY,
        IOIComponent.AUTONOMY: IOIEventType.AUTONOMY_OPPORTUNITY,
        IOIComponent.RESPONSIBLE_USAGE: IOIEventType.RESPONSIBLE_USAGE_OPPORTUNITY,
    }
    return IOIObservation(
        event_id=event_id or f"{component.value}-{opportunity_id}",
        user_id="user-1",
        session_id="session-1",
        component=component,
        event_type=event_types[component],
        opportunity_id=opportunity_id,
        behavior_observed=observed,
        valid=valid,
        timestamp=TIMESTAMP,
        schema_version="1.0",
    )


def test_each_component_needs_three_valid_observations() -> None:
    service = IOIScoringService()

    for component in IOIComponent:
        result = service.score(
            [
                _observation(component, "one", True),
                _observation(component, "two", False),
            ]
        )
        component_result = result.components[component]

        assert component_result.evidence_count == 2
        assert component_result.sufficient is False
        assert component_result.score == 0.5


def test_duplicate_opportunity_is_counted_once() -> None:
    service = IOIScoringService()
    observations = [
        _observation(IOIComponent.CRITICAL_VERIFICATION, "same", True, "event-1"),
        _observation(IOIComponent.CRITICAL_VERIFICATION, "same", False, "event-2"),
    ]

    result = service.score(observations)

    assert result.components[IOIComponent.CRITICAL_VERIFICATION].evidence_count == 1
    assert result.components[IOIComponent.CRITICAL_VERIFICATION].score == 1.0


def test_aggregate_is_unavailable_until_all_components_are_sufficient() -> None:
    service = IOIScoringService()
    observations = [
        _observation(component, f"{component.value}-{i}", i % 2 == 0)
        for component in IOIComponent
        for i in range(3 if component is not IOIComponent.AUTONOMY else 2)
    ]

    result = service.score(observations)

    assert result.aggregate_score is None
    assert result.status == "INSUFFICIENT_EVIDENCE"


def test_aggregate_uses_fixed_weights_without_redistribution() -> None:
    service = IOIScoringService()
    observed_counts = {
        IOIComponent.CRITICAL_VERIFICATION: 3,
        IOIComponent.CLARIFICATION: 2,
        IOIComponent.ITERATION: 1,
        IOIComponent.AUTONOMY: 0,
        IOIComponent.RESPONSIBLE_USAGE: 1,
    }
    observations = [
        _observation(component, f"{component.value}-{i}", i < observed_counts[component])
        for component in IOIComponent
        for i in range(3)
    ]

    result = service.score(observations)

    assert result.aggregate_score == 0.5
    assert result.status == "AVAILABLE"
    assert result.calculation_version == "1.0"


def test_invalid_observations_do_not_count() -> None:
    service = IOIScoringService()

    result = service.score(
        [
            _observation(IOIComponent.ITERATION, "one", True, valid=False),
            _observation(IOIComponent.ITERATION, "two", True),
            _observation(IOIComponent.ITERATION, "three", True),
        ]
    )

    assert result.components[IOIComponent.ITERATION].evidence_count == 2
    assert result.components[IOIComponent.ITERATION].sufficient is False
