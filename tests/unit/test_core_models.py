"""Unit tests for coglayer.core.models.

Covers:
- Round-trip Pydantic serialisation (JSON → model → JSON) for every model.
- Field type checks after deserialisation.
- Property test: DataQuality.completeness validator via Hypothesis.
- DataQuality raises ValueError when completeness is out of [0, 1].

Requirements: R-002.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from coglayer.core.models import (
    CognitiveProfile,
    ConsentRecord,
    DataQuality,
    DimensionEstimate,
    EngineDecision,
    Evidence,
    Reading,
    Session,
    SessionStatus,
    Signal,
    TaskDescriptor,
    TaskResult,
    Trial,
)

# ---------------------------------------------------------------------------
# Helpers — minimal valid fixture dicts
# ---------------------------------------------------------------------------

_NOW = "2024-01-15T10:00:00+00:00"


def _trial_dict(**overrides: object) -> dict:
    base: dict = {
        "stimulus": "go",
        "expected": "press",
        "response": "press",
        "rt_ms": 320.5,
        "timestamp": _NOW,
        "valid": True,
        "invalid_reason": None,
    }
    base.update(overrides)
    return base


def _signal_dict(**overrides: object) -> dict:
    base: dict = {"name": "rt", "value": 320.5}
    base.update(overrides)
    return base


def _data_quality_dict(**overrides: object) -> dict:
    base: dict = {
        "valid_trials": 8,
        "total_trials": 10,
        "completeness": 0.8,
        "anomalies": [],
    }
    base.update(overrides)
    return base


def _task_result_dict(**overrides: object) -> dict:
    base: dict = {
        "task_id": "go_no_go",
        "task_version": "1.0",
        "session_id": "sess-001",
        "user_id": "user-001",
        "trials": [_trial_dict()],
        "metrics": {"accuracy": 0.9},
        "signals": [_signal_dict()],
        "target_dimensions": ["response_inhibition"],
        "data_quality": _data_quality_dict(),
        "uncertainty": 0.1,
    }
    base.update(overrides)
    return base


def _task_descriptor_dict(**overrides: object) -> dict:
    base: dict = {
        "task_id": "go_no_go",
        "version": "1.0",
        "instructions": "Press when you see Go.",
        "target_dimensions": ["response_inhibition"],
        "parameters": {"n_trials": 20, "isi_ms": 800},
        "readings": [
            {"metric": "nogo_accuracy", "dimension": "response_inhibition", "status": "profile"}
        ],
    }
    base.update(overrides)
    return base


def _engine_decision_dict(**overrides: object) -> dict:
    base: dict = {"next_task": "go_no_go", "status": "next_task", "reason": None}
    base.update(overrides)
    return base


def _session_dict(**overrides: object) -> dict:
    base: dict = {
        "session_id": "sess-001",
        "user_id": "user-001",
        "start_time": _NOW,
        "end_time": None,
        "status": "in_progress",
        "completed_tasks": [],
    }
    base.update(overrides)
    return base


def _evidence_dict(**overrides: object) -> dict:
    base: dict = {
        "dimension": "response_inhibition",
        "outcome": 0.75,
        "source": "active",
        "weight": 1.0,
        "timestamp": _NOW,
        "reason_code": "task_score",
        "task_id": "go_no_go",
        "session_id": "sess-001",
    }
    base.update(overrides)
    return base


def _dimension_estimate_dict(**overrides: object) -> dict:
    base: dict = {
        "dimension": "response_inhibition",
        "mean": 0.6,
        "lower": 0.4,
        "upper": 0.8,
        "n_evidence": 1,
        "last_update": _NOW,
    }
    base.update(overrides)
    return base


def _cognitive_profile_dict(**overrides: object) -> dict:
    base: dict = {
        "user_id": "user-001",
        "dimensions": {"response_inhibition": _dimension_estimate_dict()},
        "evidence_history": [_evidence_dict()],
        "data_quality": {"response_inhibition": _data_quality_dict()},
        "uncertainty": {"response_inhibition": 0.2},
    }
    base.update(overrides)
    return base


def _consent_record_dict(**overrides: object) -> dict:
    base: dict = {
        "user_id": "user-001",
        "consented_at": _NOW,
        "revoked_at": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Round-trip serialisation tests
# ---------------------------------------------------------------------------


def _round_trip(model_cls: Any, data: dict) -> object:
    """Deserialise dict → model, serialise back to JSON, re-parse, check equality."""
    instance = model_cls.model_validate(data)
    json_str = instance.model_dump_json()
    re_parsed = model_cls.model_validate_json(json_str)
    # The two in-memory objects must have equal field values.
    assert instance.model_dump() == re_parsed.model_dump()
    return instance


class TestTrialRoundTrip:
    def test_round_trip(self) -> None:
        instance = _round_trip(Trial, _trial_dict())
        assert isinstance(instance, Trial)

    def test_field_types(self) -> None:
        instance = Trial.model_validate(_trial_dict())
        assert isinstance(instance.stimulus, str)
        assert isinstance(instance.expected, str)
        assert isinstance(instance.response, str | type(None))
        assert isinstance(instance.rt_ms, float)
        assert isinstance(instance.timestamp, datetime)
        assert isinstance(instance.valid, bool)
        assert instance.invalid_reason is None

    def test_omission_response_none(self) -> None:
        instance = Trial.model_validate(_trial_dict(response=None))
        assert instance.response is None

    def test_invalid_reason_set(self) -> None:
        instance = Trial.model_validate(_trial_dict(valid=False, invalid_reason="anticipation"))
        assert instance.invalid_reason == "anticipation"


class TestSignalRoundTrip:
    def test_round_trip(self) -> None:
        instance = _round_trip(Signal, _signal_dict())
        assert isinstance(instance, Signal)

    def test_field_types(self) -> None:
        instance = Signal.model_validate(_signal_dict())
        assert isinstance(instance.name, str)
        assert isinstance(instance.value, float)


class TestDataQualityRoundTrip:
    def test_round_trip(self) -> None:
        instance = _round_trip(DataQuality, _data_quality_dict())
        assert isinstance(instance, DataQuality)

    def test_field_types(self) -> None:
        instance = DataQuality.model_validate(_data_quality_dict())
        assert isinstance(instance.valid_trials, int)
        assert isinstance(instance.total_trials, int)
        assert isinstance(instance.completeness, float)
        assert isinstance(instance.anomalies, list)

    def test_completeness_boundary_zero(self) -> None:
        instance = DataQuality.model_validate(
            _data_quality_dict(valid_trials=0, total_trials=0, completeness=0.0)
        )
        assert instance.completeness == 0.0

    def test_completeness_boundary_one(self) -> None:
        instance = DataQuality.model_validate(
            _data_quality_dict(valid_trials=10, total_trials=10, completeness=1.0)
        )
        assert instance.completeness == 1.0


class TestTaskResultRoundTrip:
    def test_round_trip(self) -> None:
        instance = _round_trip(TaskResult, _task_result_dict())
        assert isinstance(instance, TaskResult)

    def test_field_types(self) -> None:
        instance = TaskResult.model_validate(_task_result_dict())
        assert isinstance(instance.task_id, str)
        assert isinstance(instance.task_version, str)
        assert isinstance(instance.session_id, str)
        assert isinstance(instance.user_id, str)
        assert isinstance(instance.trials, list)
        assert isinstance(instance.metrics, dict)
        assert isinstance(instance.signals, list)
        assert isinstance(instance.target_dimensions, list)
        assert isinstance(instance.data_quality, DataQuality)
        assert isinstance(instance.uncertainty, float | type(None))

    def test_nested_trial_types(self) -> None:
        instance = TaskResult.model_validate(_task_result_dict())
        assert all(isinstance(t, Trial) for t in instance.trials)

    def test_nested_signal_types(self) -> None:
        instance = TaskResult.model_validate(_task_result_dict())
        assert all(isinstance(s, Signal) for s in instance.signals)

    def test_uncertainty_none(self) -> None:
        instance = TaskResult.model_validate(_task_result_dict(uncertainty=None))
        assert instance.uncertainty is None


class TestTaskDescriptorRoundTrip:
    def test_round_trip(self) -> None:
        instance = _round_trip(TaskDescriptor, _task_descriptor_dict())
        assert isinstance(instance, TaskDescriptor)

    def test_field_types(self) -> None:
        instance = TaskDescriptor.model_validate(_task_descriptor_dict())
        assert isinstance(instance.task_id, str)
        assert isinstance(instance.version, str)
        assert isinstance(instance.instructions, str)
        assert isinstance(instance.target_dimensions, list)
        assert isinstance(instance.parameters, dict)


class TestEngineDecisionRoundTrip:
    def test_round_trip(self) -> None:
        instance = _round_trip(EngineDecision, _engine_decision_dict())
        assert isinstance(instance, EngineDecision)

    def test_field_types(self) -> None:
        instance = EngineDecision.model_validate(_engine_decision_dict())
        assert isinstance(instance.next_task, str | type(None))
        assert instance.status in ("next_task", "complete", "insufficient_data")

    def test_complete_status(self) -> None:
        instance = EngineDecision.model_validate(
            {"next_task": None, "status": "complete", "reason": None}
        )
        assert instance.status == "complete"
        assert instance.next_task is None

    def test_insufficient_data_with_reason(self) -> None:
        instance = EngineDecision.model_validate(
            {
                "next_task": None,
                "status": "insufficient_data",
                "reason": "completeness below threshold",
            }
        )
        assert instance.status == "insufficient_data"
        assert instance.reason == "completeness below threshold"


class TestSessionRoundTrip:
    def test_round_trip(self) -> None:
        instance = _round_trip(Session, _session_dict())
        assert isinstance(instance, Session)

    def test_field_types(self) -> None:
        instance = Session.model_validate(_session_dict())
        assert isinstance(instance.session_id, str)
        assert isinstance(instance.user_id, str)
        assert isinstance(instance.start_time, datetime)
        assert instance.end_time is None
        assert isinstance(instance.status, SessionStatus)
        assert isinstance(instance.completed_tasks, list)

    def test_all_status_values(self) -> None:
        for status_val in ("pending", "in_progress", "completed", "interrupted"):
            instance = Session.model_validate(_session_dict(status=status_val))
            assert instance.status.value == status_val

    def test_end_time_set(self) -> None:
        instance = Session.model_validate(_session_dict(end_time=_NOW))
        assert isinstance(instance.end_time, datetime)


class TestEvidenceRoundTrip:
    def test_round_trip(self) -> None:
        instance = _round_trip(Evidence, _evidence_dict())
        assert isinstance(instance, Evidence)

    def test_field_types(self) -> None:
        instance = Evidence.model_validate(_evidence_dict())
        assert isinstance(instance.dimension, str)
        assert isinstance(instance.outcome, float)
        assert instance.source in ("active", "passive")
        assert isinstance(instance.weight, float)
        assert isinstance(instance.timestamp, datetime)
        assert isinstance(instance.reason_code, str)
        assert isinstance(instance.task_id, str)
        assert isinstance(instance.session_id, str)


class TestDimensionEstimateRoundTrip:
    def test_round_trip(self) -> None:
        instance = _round_trip(DimensionEstimate, _dimension_estimate_dict())
        assert isinstance(instance, DimensionEstimate)

    def test_field_types(self) -> None:
        instance = DimensionEstimate.model_validate(_dimension_estimate_dict())
        assert isinstance(instance.dimension, str)
        assert isinstance(instance.mean, float)
        assert isinstance(instance.lower, float)
        assert isinstance(instance.upper, float)
        assert isinstance(instance.n_evidence, int)
        assert isinstance(instance.last_update, datetime)


class TestCognitiveProfileRoundTrip:
    def test_round_trip(self) -> None:
        instance = _round_trip(CognitiveProfile, _cognitive_profile_dict())
        assert isinstance(instance, CognitiveProfile)

    def test_field_types(self) -> None:
        instance = CognitiveProfile.model_validate(_cognitive_profile_dict())
        assert isinstance(instance.user_id, str)
        assert isinstance(instance.dimensions, dict)
        assert isinstance(instance.evidence_history, list)
        assert isinstance(instance.data_quality, dict)
        assert isinstance(instance.uncertainty, dict)

    def test_nested_dimension_estimate_type(self) -> None:
        instance = CognitiveProfile.model_validate(_cognitive_profile_dict())
        for val in instance.dimensions.values():
            assert isinstance(val, DimensionEstimate)

    def test_nested_evidence_type(self) -> None:
        instance = CognitiveProfile.model_validate(_cognitive_profile_dict())
        for ev in instance.evidence_history:
            assert isinstance(ev, Evidence)


class TestConsentRecordRoundTrip:
    def test_round_trip(self) -> None:
        instance = _round_trip(ConsentRecord, _consent_record_dict())
        assert isinstance(instance, ConsentRecord)

    def test_field_types(self) -> None:
        instance = ConsentRecord.model_validate(_consent_record_dict())
        assert isinstance(instance.user_id, str)
        assert isinstance(instance.consented_at, datetime)
        assert instance.revoked_at is None

    def test_revoked_at_set(self) -> None:
        instance = ConsentRecord.model_validate(_consent_record_dict(revoked_at=_NOW))
        assert isinstance(instance.revoked_at, datetime)


# ---------------------------------------------------------------------------
# DataQuality validator: completeness out of [0, 1] raises ValueError
# ---------------------------------------------------------------------------


class TestDataQualityValidator:
    def test_completeness_above_one_raises(self) -> None:
        with pytest.raises(ValidationError):
            DataQuality.model_validate(_data_quality_dict(completeness=1.001))

    def test_completeness_below_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            DataQuality.model_validate(_data_quality_dict(completeness=-0.001))

    def test_completeness_exactly_zero_ok(self) -> None:
        dq = DataQuality.model_validate(
            _data_quality_dict(valid_trials=0, total_trials=5, completeness=0.0)
        )
        assert dq.completeness == 0.0

    def test_completeness_exactly_one_ok(self) -> None:
        dq = DataQuality.model_validate(
            _data_quality_dict(valid_trials=5, total_trials=5, completeness=1.0)
        )
        assert dq.completeness == 1.0


# ---------------------------------------------------------------------------
# Property test: DataQuality.completeness = valid / total
# Feature: vertical-slice, Property (task 2.4): DataQuality completeness
# ---------------------------------------------------------------------------


@given(
    valid=st.integers(min_value=0, max_value=100),
    total=st.integers(min_value=0, max_value=100),
)
@settings(max_examples=200)
def test_data_quality_completeness_property(valid: int, total: int) -> None:
    """Validates: Requirements R-002.4

    For any valid/total in [0, 100], when valid <= total:
    - completeness is in [0.0, 1.0]
    - completeness == valid / total when total > 0
    - completeness == 0.0 when total == 0
    """
    # Clamp valid to not exceed total (both drawn independently)
    valid = min(valid, total)

    if total == 0:
        completeness = 0.0
    else:
        completeness = valid / total

    dq = DataQuality.model_validate(
        {
            "valid_trials": valid,
            "total_trials": total,
            "completeness": completeness,
            "anomalies": [],
        }
    )

    # Completeness must be in [0, 1]
    assert 0.0 <= dq.completeness <= 1.0

    if total > 0:
        assert dq.completeness == pytest.approx(valid / total)
    else:
        assert dq.completeness == 0.0


# ---------------------------------------------------------------------------
# LLMRequest / LLMResponse model tests (Fix A2 — these are real Pydantic
# models in protocols.py, not Protocol stubs, so they need coverage)
# ---------------------------------------------------------------------------


def test_llm_request_response_models() -> None:
    """LLMRequest and LLMResponse are real Pydantic models; verify round-trip."""
    from coglayer.core.protocols import LLMRequest, LLMResponse

    req = LLMRequest(prompt="hello world")
    assert req.prompt == "hello world"
    assert LLMRequest.model_validate_json(req.model_dump_json()).prompt == "hello world"

    resp = LLMResponse(text="feedback text")
    assert resp.text == "feedback text"
    assert LLMResponse.model_validate_json(resp.model_dump_json()).text == "feedback text"


# ---------------------------------------------------------------------------
# Step 5 — Interpretation rules and Reading model tests
# ---------------------------------------------------------------------------


def test_real_task_descriptors_have_exactly_one_profile_reading() -> None:
    """Descriptor of each real task has exactly one profile reading for its target dimension.

    Hand-derived:
      go_no_go:
        target_dimensions: ['response_inhibition']
        readings:
          nogo_accuracy -> response_inhibition [profile]
          go_accuracy -> engagement [quality]
          omission_errors -> engagement [quality]
          mean_rt_ms -> speed [observation, caveat]
          rt_std_ms -> attention_regularity [observation, caveat]
        primary_metric derived: 'nogo_accuracy'

      sequence_span:
        target_dimensions: ['sequential_visual_memory']
        readings:
          correct_sequences_ratio -> sequential_visual_memory [profile]
          completeness -> engagement [quality]
          mean_rt_ms -> speed [observation, caveat]
        primary_metric derived: 'correct_sequences_ratio'
    """
    from coglayer.core.tasks import GO_NO_GO_DESCRIPTOR, SEQUENCE_SPAN_DESCRIPTOR

    # go_no_go
    gng_profiles = [r for r in GO_NO_GO_DESCRIPTOR.readings if r.status == "profile"]
    assert len(gng_profiles) == 1
    assert gng_profiles[0].metric == "nogo_accuracy"
    assert gng_profiles[0].dimension == "response_inhibition"
    assert GO_NO_GO_DESCRIPTOR.primary_metric == "nogo_accuracy"
    assert len(GO_NO_GO_DESCRIPTOR.readings) == 5

    # sequence_span
    span_profiles = [r for r in SEQUENCE_SPAN_DESCRIPTOR.readings if r.status == "profile"]
    assert len(span_profiles) == 1
    assert span_profiles[0].metric == "correct_sequences_ratio"
    assert span_profiles[0].dimension == "sequential_visual_memory"
    assert SEQUENCE_SPAN_DESCRIPTOR.primary_metric == "correct_sequences_ratio"
    assert len(SEQUENCE_SPAN_DESCRIPTOR.readings) == 3


def test_readings_validator_rejects_duplicate_profile_reading_per_dimension() -> None:
    """Validator rejects two status='profile' readings for one dimension.

    Hand-derived:
      target_dimensions: ['dim_a']
      readings:
        m1 -> dim_a [profile]
        m2 -> dim_a [profile]
      Must raise ValidationError because only 1 profile reading per dimension is allowed.
    """
    with pytest.raises(ValidationError, match="profile"):
        TaskDescriptor(
            task_id="dup_profile",
            version="1.0",
            instructions="Test",
            target_dimensions=["dim_a"],
            parameters={},
            readings=[
                Reading(metric="m1", dimension="dim_a", status="profile"),
                Reading(metric="m2", dimension="dim_a", status="profile"),
            ],
        )


def test_reading_without_status_rejected() -> None:
    """Pydantic rejects a Reading without a valid status.

    Hand-derived:
      status is required and must be Literal['profile', 'observation', 'quality'].
    """
    with pytest.raises(ValidationError):
        Reading.model_validate({"metric": "m", "dimension": "d"})  # missing status

    with pytest.raises(ValidationError):
        Reading.model_validate({"metric": "m", "dimension": "d", "status": "invalid_status"})


def test_validator_rejects_numeric_weights_anywhere() -> None:
    """Validator rejects numeric weights anywhere in TaskDescriptor.

    Hand-derived:
      parameters={'weight': 1.0} must raise ValidationError.
    """
    with pytest.raises(ValidationError, match=r"[Ww]eight"):
        TaskDescriptor(
            task_id="weighted_task",
            version="1.0",
            instructions="Test",
            target_dimensions=["dim_a"],
            parameters={"weight": 1.0},
            readings=[
                Reading(metric="m1", dimension="dim_a", status="profile"),
            ],
        )
