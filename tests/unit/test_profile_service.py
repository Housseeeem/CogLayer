"""Unit tests for ProfileService.

Task 10.4 — ProfileService reads result.metrics only, updates dimensions,
builds Evidence records, handles missing metrics gracefully.

Requirements: R-006.1, R-006.2, R-006.3
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coglayer.core.models import (
    CognitiveProfile,
    DataQuality,
    Reading,
    TaskDescriptor,
    TaskResult,
    Trial,
)
from coglayer.profile.service import (
    DIMENSION_MAPPING,
    ProfileService,
    derive_dimension_mapping,
    derive_dimension_mapping_from_descriptors,
)
from coglayer.signals.registry import InMemoryTaskRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

_EMPTY_PROFILE = CognitiveProfile(
    user_id="u1",
    dimensions={},
    evidence_history=[],
    data_quality={},
    uncertainty={},
)


def _make_gng_result(
    nogo_accuracy: float = 0.8,
    nogo_valid_count: float = 10.0,
    session_id: str = "s1",
) -> TaskResult:
    """Minimal go_no_go TaskResult — trials list is empty (ProfileService never reads it)."""
    dq = DataQuality(
        valid_trials=int(nogo_valid_count),
        total_trials=20,
        completeness=nogo_valid_count / 20.0,
        anomalies=[],
    )
    return TaskResult(
        task_id="go_no_go",
        task_version="1.0",
        session_id=session_id,
        user_id="u1",
        trials=[],
        metrics={"nogo_accuracy": nogo_accuracy, "nogo_valid_count": nogo_valid_count},
        signals=[],
        target_dimensions=["response_inhibition"],
        data_quality=dq,
        uncertainty=None,
    )


def _make_span_result(
    ratio: float = 0.6,
    valid_sequence_count: float = 8.0,
) -> TaskResult:
    dq = DataQuality(
        valid_trials=int(valid_sequence_count),
        total_trials=10,
        completeness=valid_sequence_count / 10.0,
        anomalies=[],
    )
    return TaskResult(
        task_id="sequence_span",
        task_version="1.0",
        session_id="s1",
        user_id="u1",
        trials=[],
        metrics={
            "correct_sequences_ratio": ratio,
            "valid_sequence_count": valid_sequence_count,
        },
        signals=[],
        target_dimensions=["sequential_visual_memory"],
        data_quality=dq,
        uncertainty=None,
    )


# ---------------------------------------------------------------------------
# DIMENSION_MAPPING structure tests
# ---------------------------------------------------------------------------


def test_dimension_mapping_has_go_no_go() -> None:
    """DIMENSION_MAPPING includes go_no_go with response_inhibition, nogo_accuracy, count."""
    assert "go_no_go" in DIMENSION_MAPPING
    mappings = DIMENSION_MAPPING["go_no_go"]
    assert any(
        dim == "response_inhibition" and metric == "nogo_accuracy" and count_m == "nogo_valid_count"
        for dim, metric, _, count_m in mappings
    )


def test_dimension_mapping_has_sequence_span() -> None:
    """DIMENSION_MAPPING includes sequence_span with valid_sequence_count."""
    assert "sequence_span" in DIMENSION_MAPPING
    mappings = DIMENSION_MAPPING["sequence_span"]
    assert any(
        dim == "sequential_visual_memory"
        and metric == "correct_sequences_ratio"
        and count_m == "valid_sequence_count"
        for dim, metric, _, count_m in mappings
    )


# ---------------------------------------------------------------------------
# Core ProfileService tests
# ---------------------------------------------------------------------------


def test_update_adds_dimension() -> None:
    """update_from_result adds the mapped dimension to the profile."""
    svc = ProfileService()
    updated = svc.update_from_result(_EMPTY_PROFILE, _make_gng_result())
    assert "response_inhibition" in updated.dimensions


def test_dimension_estimate_interval_contains_mean() -> None:
    """DimensionEstimate has lower <= mean <= upper."""
    svc = ProfileService()
    updated = svc.update_from_result(_EMPTY_PROFILE, _make_gng_result(0.8))
    est = updated.dimensions["response_inhibition"]
    assert est.lower <= est.mean <= est.upper


def test_high_nogo_accuracy_shifts_mean_above_half() -> None:
    """High nogo_accuracy produces mean > 0.5."""
    svc = ProfileService(lambda_=1.0)
    updated = svc.update_from_result(_EMPTY_PROFILE, _make_gng_result(nogo_accuracy=0.95))
    assert updated.dimensions["response_inhibition"].mean > 0.5


def test_low_nogo_accuracy_shifts_mean_below_half() -> None:
    """Low nogo_accuracy produces mean < 0.5."""
    svc = ProfileService(lambda_=1.0)
    updated = svc.update_from_result(_EMPTY_PROFILE, _make_gng_result(nogo_accuracy=0.05))
    assert updated.dimensions["response_inhibition"].mean < 0.5


def test_evidence_appended() -> None:
    """update_from_result appends exactly one Evidence record for go_no_go."""
    svc = ProfileService()
    updated = svc.update_from_result(_EMPTY_PROFILE, _make_gng_result(0.8))
    assert len(updated.evidence_history) == 1
    ev = updated.evidence_history[0]
    assert ev.dimension == "response_inhibition"
    assert ev.task_id == "go_no_go"
    assert ev.source == "active"


def test_evidence_weight_equals_base_times_capped_count() -> None:
    """Evidence.weight == base_weight * min(count, MAX_PSEUDO_COUNT)."""
    from coglayer.profile.model import MAX_PSEUDO_COUNT

    svc = ProfileService()
    count = 5.0
    result = _make_gng_result(nogo_accuracy=0.8, nogo_valid_count=count)
    updated = svc.update_from_result(_EMPTY_PROFILE, result)
    ev = updated.evidence_history[0]
    # base_weight = 1.0, min(5.0, 20.0) = 5.0
    assert ev.weight == pytest.approx(1.0 * min(count, MAX_PSEUDO_COUNT))


def test_zero_count_skips_update() -> None:
    """nogo_valid_count=0 skips the update: no dimension, no evidence."""
    svc = ProfileService()
    result = _make_gng_result(nogo_accuracy=0.8, nogo_valid_count=0.0)
    updated = svc.update_from_result(_EMPTY_PROFILE, result)
    assert "response_inhibition" not in updated.dimensions
    assert len(updated.evidence_history) == 0


def test_larger_count_moves_mean_more() -> None:
    """Larger nogo_valid_count moves the mean further from 0.5 (same accuracy)."""
    svc = ProfileService(lambda_=1.0)
    up_small = svc.update_from_result(_EMPTY_PROFILE, _make_gng_result(0.8, nogo_valid_count=2.0))
    up_large = svc.update_from_result(_EMPTY_PROFILE, _make_gng_result(0.8, nogo_valid_count=15.0))
    mean_small = up_small.dimensions["response_inhibition"].mean
    mean_large = up_large.dimensions["response_inhibition"].mean
    # nogo_accuracy=0.8 > 0.5; larger count pushes mean further above 0.5
    assert mean_large > mean_small


def test_out_of_range_outcome_skips_dimension() -> None:
    """outcome outside [0, 1] is silently skipped (defensive guard)."""
    svc = ProfileService()
    dq = DataQuality(valid_trials=5, total_trials=5, completeness=1.0, anomalies=[])
    result_bad_outcome = TaskResult(
        task_id="go_no_go",
        task_version="1.0",
        session_id="s1",
        user_id="u1",
        trials=[],
        metrics={"nogo_accuracy": 1.5, "nogo_valid_count": 5.0},  # 1.5 is out of [0,1]
        signals=[],
        target_dimensions=["response_inhibition"],
        data_quality=dq,
        uncertainty=None,
    )
    updated = svc.update_from_result(_EMPTY_PROFILE, result_bad_outcome)
    assert "response_inhibition" not in updated.dimensions


def test_unknown_task_returns_profile_unchanged() -> None:
    """An unknown task_id leaves the profile unchanged."""
    svc = ProfileService()
    dq = DataQuality(valid_trials=5, total_trials=5, completeness=1.0, anomalies=[])
    unknown = TaskResult(
        task_id="unknown_task",
        task_version="1.0",
        session_id="s1",
        user_id="u1",
        trials=[],
        metrics={"some_metric": 0.5},
        signals=[],
        target_dimensions=[],
        data_quality=dq,
        uncertainty=None,
    )
    updated = svc.update_from_result(_EMPTY_PROFILE, unknown)
    assert updated.dimensions == _EMPTY_PROFILE.dimensions
    assert updated.evidence_history == _EMPTY_PROFILE.evidence_history


def test_missing_outcome_metric_skips_dimension() -> None:
    """If the outcome metric is absent, the dimension is skipped."""
    svc = ProfileService()
    dq = DataQuality(valid_trials=5, total_trials=5, completeness=1.0, anomalies=[])
    result_no_metric = TaskResult(
        task_id="go_no_go",
        task_version="1.0",
        session_id="s1",
        user_id="u1",
        trials=[],
        metrics={"accuracy": 0.8},  # nogo_accuracy absent
        signals=[],
        target_dimensions=["response_inhibition"],
        data_quality=dq,
        uncertainty=None,
    )
    updated = svc.update_from_result(_EMPTY_PROFILE, result_no_metric)
    assert "response_inhibition" not in updated.dimensions


def test_missing_count_metric_skips_dimension() -> None:
    """If the count metric is absent, the dimension is skipped."""
    svc = ProfileService()
    dq = DataQuality(valid_trials=5, total_trials=5, completeness=1.0, anomalies=[])
    result_no_count = TaskResult(
        task_id="go_no_go",
        task_version="1.0",
        session_id="s1",
        user_id="u1",
        trials=[],
        metrics={"nogo_accuracy": 0.8},  # nogo_valid_count absent
        signals=[],
        target_dimensions=["response_inhibition"],
        data_quality=dq,
        uncertainty=None,
    )
    updated = svc.update_from_result(_EMPTY_PROFILE, result_no_count)
    assert "response_inhibition" not in updated.dimensions


def test_profile_service_never_reads_trials() -> None:
    """ProfileService with trials=[] gives same result as with non-empty trials."""
    svc = ProfileService()
    result_no_trials = _make_gng_result(0.8)
    trial = Trial(
        stimulus="go",
        expected="press",
        response="press",
        rt_ms=250.0,
        timestamp=_TS,
        valid=True,
        invalid_reason=None,
    )
    result_with_trials = TaskResult(
        task_id=result_no_trials.task_id,
        task_version=result_no_trials.task_version,
        session_id=result_no_trials.session_id,
        user_id=result_no_trials.user_id,
        trials=[trial],
        metrics=result_no_trials.metrics,
        signals=result_no_trials.signals,
        target_dimensions=result_no_trials.target_dimensions,
        data_quality=result_no_trials.data_quality,
        uncertainty=result_no_trials.uncertainty,
    )
    up_no = svc.update_from_result(_EMPTY_PROFILE, result_no_trials)
    up_with = svc.update_from_result(_EMPTY_PROFILE, result_with_trials)
    assert up_no.dimensions["response_inhibition"].mean == pytest.approx(
        up_with.dimensions["response_inhibition"].mean
    )


def test_sequential_memory_dimension_updated() -> None:
    """sequence_span updates sequential_visual_memory."""
    svc = ProfileService()
    updated = svc.update_from_result(_EMPTY_PROFILE, _make_span_result(ratio=0.7))
    assert "sequential_visual_memory" in updated.dimensions


def test_n_evidence_increments_across_sessions() -> None:
    """n_evidence increments when the same dimension is updated in a second session."""
    svc = ProfileService()
    p1 = svc.update_from_result(_EMPTY_PROFILE, _make_gng_result(0.8, session_id="s1"))
    p2 = svc.update_from_result(p1, _make_gng_result(0.8, session_id="s2"))
    assert p2.dimensions["response_inhibition"].n_evidence == 2


def test_alpha_beta_persisted_in_dimension_estimate() -> None:
    """DimensionEstimate.alpha/beta_param are stored after update."""
    svc = ProfileService()
    updated = svc.update_from_result(_EMPTY_PROFILE, _make_gng_result(0.8, nogo_valid_count=5.0))
    est = updated.dimensions["response_inhibition"]
    # alpha and beta_param must be non-trivial (not both 1.0)
    assert not (est.alpha == pytest.approx(1.0) and est.beta_param == pytest.approx(1.0))


def test_alpha_beta_round_trips_across_sessions() -> None:
    """alpha/beta from session 1 are used by session 2 (lossless seeding)."""
    svc = ProfileService(lambda_=1.0)
    p1 = svc.update_from_result(_EMPTY_PROFILE, _make_gng_result(1 / 3, nogo_valid_count=3.0))
    # After session 1: alpha=2, beta=3
    est1 = p1.dimensions["response_inhibition"]
    assert est1.alpha == pytest.approx(2.0)
    assert est1.beta_param == pytest.approx(3.0)
    # Session 2: same result; model seeded from alpha=2, beta=3
    p2 = svc.update_from_result(p1, _make_gng_result(1 / 3, nogo_valid_count=3.0, session_id="s2"))
    est2 = p2.dimensions["response_inhibition"]
    # alpha = 2 + 3*(1/3) = 3, beta = 3 + 3*(2/3) = 5
    assert est2.alpha == pytest.approx(3.0)
    assert est2.beta_param == pytest.approx(5.0)
    assert est2.mean == pytest.approx(3.0 / (3.0 + 5.0))


def test_uncertainty_is_upper_minus_mean() -> None:
    """uncertainty[dim] == upper - mean."""
    svc = ProfileService()
    updated = svc.update_from_result(_EMPTY_PROFILE, _make_gng_result(0.8))
    est = updated.dimensions["response_inhibition"]
    unc = updated.uncertainty.get("response_inhibition")
    assert unc == pytest.approx(est.upper - est.mean)


def test_datetimes_are_timezone_aware() -> None:
    """All datetimes in the returned profile are timezone-aware."""
    svc = ProfileService()
    updated = svc.update_from_result(_EMPTY_PROFILE, _make_gng_result(0.8))
    for ev in updated.evidence_history:
        assert ev.timestamp.tzinfo is not None
    for est in updated.dimensions.values():
        assert est.last_update.tzinfo is not None


def test_original_profile_unchanged() -> None:
    """update_from_result does not mutate the input profile."""
    svc = ProfileService()
    original_dims = dict(_EMPTY_PROFILE.dimensions)
    svc.update_from_result(_EMPTY_PROFILE, _make_gng_result(0.8))
    assert _EMPTY_PROFILE.dimensions == original_dims


def test_coverage_line_72_descriptor_without_primary_metric_skipped() -> None:
    """Line 72: Descriptor without primary_metric is skipped in mapping derivation.

    Hand-derived:
      desc has no primary_metric and no parameters['primary_metric'].
      Resulting mapping should be empty {}.
    """
    desc = TaskDescriptor(
        task_id="no_primary_task",
        version="1.0",
        instructions="Instructions",
        target_dimensions=[],
        parameters={},
    )
    mapping = derive_dimension_mapping_from_descriptors([desc])
    # Hand-derived: line 72 triggers 'continue', so "no_primary_task" is not in mapping
    assert mapping == {}


def test_coverage_lines_88_94_derive_dimension_mapping_registry_keyerror() -> None:
    """Lines 88-94: derive_dimension_mapping handles tasks missing version 1.0.

    Hand-derived:
      task_a has v1.0 -> included in mapping: {'task_a': [('dim_a', 'metric_a', 1.0, '')]}
      task_b only has v2.0 -> registry.get('task_b', '1.0') raises KeyError, caught and skipped.
    """
    registry = InMemoryTaskRegistry()
    desc_a = TaskDescriptor(
        task_id="task_a",
        version="1.0",
        instructions="Instructions A",
        target_dimensions=["dim_a"],
        primary_metric="metric_a",
        parameters={},
    )
    desc_b = TaskDescriptor(
        task_id="task_b",
        version="2.0",
        instructions="Instructions B",
        target_dimensions=["dim_b"],
        primary_metric="metric_b",
        parameters={},
    )
    registry.register(desc_a)
    registry.register(desc_b)

    mapping = derive_dimension_mapping(registry)
    # Hand-derived: only task_a is resolved (since registry.get looks up "1.0")
    assert "task_a" in mapping
    assert mapping["task_a"] == [("dim_a", "metric_a", 1.0, "")]
    assert "task_b" not in mapping


def test_coverage_lines_163_167_registry_version_fallback_and_missing() -> None:
    """Lines 163-167: Unregistered task_version adds anomaly and skips update.

    Hand-derived:
      Case 1: result task_version="2.0", registry only has "1.0".
        Profile is NOT updated, anomalies contains 'unknown_task_version'.
      Case 2: svc without registry, result task_version="2.0".
        Profile is NOT updated, anomalies contains 'unknown_task_version'.
      Case 3: unknown task_id not in registry -> returns unchanged profile.
    """
    registry = InMemoryTaskRegistry()
    desc_v1 = TaskDescriptor(
        task_id="custom_fallback_task",
        version="1.0",
        instructions="Test",
        target_dimensions=["custom_dim"],
        primary_metric="custom_metric",
        count_metric="custom_count",
        parameters={},
    )
    registry.register(desc_v1)

    svc = ProfileService(lambda_=1.0, registry=registry)
    dq1 = DataQuality(valid_trials=10, total_trials=10, completeness=1.0, anomalies=[])
    res1 = TaskResult(
        task_id="custom_fallback_task",
        task_version="2.0",
        session_id="s1",
        user_id="u1",
        trials=[],
        metrics={"custom_metric": 0.75, "custom_count": 10.0},
        signals=[],
        target_dimensions=["custom_dim"],
        data_quality=dq1,
        uncertainty=None,
    )
    p1 = svc.update_from_result(_EMPTY_PROFILE, res1)
    # Hand-derived: version 2.0 is not registered -> profile is untouched
    assert p1.dimensions == {}
    assert "unknown_task_version" in res1.data_quality.anomalies

    # Case 2: svc without registry and version != "1.0"
    svc_no_reg = ProfileService(lambda_=1.0, registry=None)
    res2 = _make_gng_result(nogo_accuracy=0.8, nogo_valid_count=10.0).model_copy(
        update={"task_version": "99.0"}
    )
    p2 = svc_no_reg.update_from_result(_EMPTY_PROFILE, res2)
    assert p2.dimensions == {}
    assert "unknown_task_version" in res2.data_quality.anomalies

    # Case 3: registered version "1.0" with svc_no_reg -> updates
    res3 = _make_gng_result(nogo_accuracy=0.8, nogo_valid_count=10.0).model_copy(
        update={"task_version": "1.0"}
    )
    p3 = svc_no_reg.update_from_result(_EMPTY_PROFILE, res3)
    assert "response_inhibition" in p3.dimensions


def test_coverage_line_203_missing_count_metric_with_zero_valid_trials() -> None:
    """Line 203: When count_metric is empty and valid_trials <= 0, raw_count is None and skipped.

    Hand-derived:
      Descriptor has count_metric = "" (no count_metric in parameters).
      Result has valid_trials = 0 and completeness = 0.0.
      raw_count becomes None -> dimension update is skipped. Profile remains unchanged.
      When valid_trials = 5:
      raw_count = 5.0. Outcome 0.6, count 5.0, weight 1.0 -> n_eff = 5.0.
      alpha = 1 + 5 * 0.6 = 4.0, beta = 1 + 5 * 0.4 = 3.0.
      mean = 4.0 / 7.0 = 0.57142857...
    """
    registry = InMemoryTaskRegistry()
    desc = TaskDescriptor(
        task_id="no_count_metric_task",
        version="1.0",
        instructions="Test",
        target_dimensions=["dim_x"],
        primary_metric="metric_x",
        parameters={},  # No count_metric
    )
    registry.register(desc)
    svc = ProfileService(lambda_=1.0, registry=registry)

    # valid_trials = 0 -> line 203 raw_count = None -> skipped
    dq_zero = DataQuality(valid_trials=0, total_trials=10, completeness=0.0, anomalies=[])
    res_zero = TaskResult(
        task_id="no_count_metric_task",
        task_version="1.0",
        session_id="s1",
        user_id="u1",
        trials=[],
        metrics={"metric_x": 0.6},
        signals=[],
        target_dimensions=["dim_x"],
        data_quality=dq_zero,
        uncertainty=None,
    )
    p_zero = svc.update_from_result(_EMPTY_PROFILE, res_zero)
    # Hand-derived: skipped, profile remains empty
    assert "dim_x" not in p_zero.dimensions

    # valid_trials = 5 -> lines 200-201 raw_count = 5.0 -> updated
    dq_five = DataQuality(valid_trials=5, total_trials=10, completeness=0.5, anomalies=[])
    res_five = TaskResult(
        task_id="no_count_metric_task",
        task_version="1.0",
        session_id="s2",
        user_id="u1",
        trials=[],
        metrics={"metric_x": 0.6},
        signals=[],
        target_dimensions=["dim_x"],
        data_quality=dq_five,
        uncertainty=None,
    )
    p_five = svc.update_from_result(_EMPTY_PROFILE, res_five)
    # Hand-derived: alpha = 1 + 5 * 0.6 = 4.0, beta = 1 + 5 * (1 - 0.6) = 3.0
    est = p_five.dimensions["dim_x"]
    assert est.alpha == pytest.approx(4.0)
    assert est.beta_param == pytest.approx(3.0)
    assert est.mean == pytest.approx(4.0 / 7.0)


def test_descriptor_metric_comes_only_from_descriptor_not_parameters() -> None:
    """Primary metric comes only from desc.primary_metric, ignoring parameters['primary_metric'].

    Hand-derived:
      desc_param has primary_metric=None and parameters={'primary_metric': 'param_metric'}.
      derive_dimension_mapping_from_descriptors([desc_param]) must NOT map task_param (returns {}).
      desc_field has primary_metric='field_metric', count_metric='field_count'.
      derive_dimension_mapping_from_descriptors([desc_field]) maps task_field to
      [('dim', 'field_metric', 1.0, 'field_count')].
    """
    desc_param = TaskDescriptor(
        task_id="task_param",
        version="1.0",
        instructions="Instructions",
        target_dimensions=[],
        readings=[Reading(metric="obs", dimension="dim_obs", status="observation")],
        parameters={"primary_metric": "param_metric"},
    )
    mapping_param = derive_dimension_mapping_from_descriptors([desc_param])
    # Hand-derived: parameters['primary_metric'] must NOT be used -> mapping is empty
    assert mapping_param == {}

    desc_field = TaskDescriptor(
        task_id="task_field",
        version="1.0",
        instructions="Instructions",
        target_dimensions=["dim_field"],
        readings=[Reading(metric="field_metric", dimension="dim_field", status="profile")],
        count_metric="field_count",
        parameters={},
    )
    mapping_field = derive_dimension_mapping_from_descriptors([desc_field])
    # Hand-derived: primary_metric and count_metric come from descriptor fields
    assert mapping_field == {"task_field": [("dim_field", "field_metric", 1.0, "field_count")]}


def test_unregistered_task_version_does_not_update_profile_and_sets_anomaly() -> None:
    """If result.task_version is not registered, profile is NOT updated and anomaly is added.

    Hand-derived:
      Prior: alpha=1.0, beta=1.0.
      Result with task_version="9.9" (unregistered for go_no_go):
        alpha stays 1.0, beta stays 1.0.
        result.data_quality.anomalies contains "unknown_task_version".
      Result with task_version="1.0" (registered for go_no_go):
        outcome=0.8, count=10.0, weight=1.0 -> n_eff = 10.0.
        alpha = 1.0 + 10.0 * 0.8 = 9.0.
        beta = 1.0 + 10.0 * (1 - 0.8) = 3.0.
        mean = 9.0 / (9.0 + 3.0) = 0.75.
        Evidence records task_version="1.0".
    """
    registry = InMemoryTaskRegistry()
    desc_v1 = TaskDescriptor(
        task_id="go_no_go",
        version="1.0",
        instructions="Instructions",
        target_dimensions=["response_inhibition"],
        primary_metric="nogo_accuracy",
        count_metric="nogo_valid_count",
        parameters={},
    )
    registry.register(desc_v1)
    svc = ProfileService(lambda_=1.0, registry=registry)

    # Version 9.9 is not registered
    res_9_9 = _make_gng_result(nogo_accuracy=0.8, nogo_valid_count=10.0).model_copy(
        update={"task_version": "9.9"}
    )
    p_after_9_9 = svc.update_from_result(_EMPTY_PROFILE, res_9_9)
    # Profile NOT updated: dimension response_inhibition should not be updated (or prior 1.0/1.0)
    assert "response_inhibition" not in p_after_9_9.dimensions
    assert "unknown_task_version" in res_9_9.data_quality.anomalies

    # Version 1.0 IS registered
    res_1_0 = _make_gng_result(nogo_accuracy=0.8, nogo_valid_count=10.0).model_copy(
        update={"task_version": "1.0"}
    )
    p_after_1_0 = svc.update_from_result(_EMPTY_PROFILE, res_1_0)
    est = p_after_1_0.dimensions["response_inhibition"]
    assert est.alpha == pytest.approx(9.0)
    assert est.beta_param == pytest.approx(3.0)
    assert est.mean == pytest.approx(0.75)
    assert len(p_after_1_0.evidence_history) == 1
    assert p_after_1_0.evidence_history[0].task_version == "1.0"
