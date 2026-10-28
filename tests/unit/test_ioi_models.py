"""Unit tests for IOI contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from coglayer.core.models import IOIComponent, IOIEventType, IOIObservation


def _observation(**overrides: object) -> IOIObservation:
    values: dict[str, object] = {
        "event_id": "event-1",
        "user_id": "user-1",
        "session_id": "session-1",
        "component": IOIComponent.CRITICAL_VERIFICATION,
        "event_type": IOIEventType.VERIFICATION_OPPORTUNITY,
        "opportunity_id": "opportunity-1",
        "behavior_observed": True,
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        "schema_version": "1.0",
        "metadata": {"source": "button"},
    }
    values.update(overrides)
    return IOIObservation.model_validate(values)


def test_observation_accepts_explicit_component_event_pair() -> None:
    observation = _observation()

    assert observation.component is IOIComponent.CRITICAL_VERIFICATION
    assert observation.event_type is IOIEventType.VERIFICATION_OPPORTUNITY


def test_observation_rejects_event_type_for_wrong_component() -> None:
    with pytest.raises(ValidationError, match="not allowed"):
        _observation(
            component=IOIComponent.CLARIFICATION,
            event_type=IOIEventType.VERIFICATION_OPPORTUNITY,
        )


def test_observation_rejects_raw_text_shaped_metadata() -> None:
    with pytest.raises(ValidationError, match="metadata"):
        _observation(metadata={"prompt": "Please verify this answer"})


def test_observation_rejects_oversized_metadata() -> None:
    with pytest.raises(ValidationError, match="metadata"):
        _observation(metadata={f"key_{i}": i for i in range(9)})
