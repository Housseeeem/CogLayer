"""Unit tests for onboarding calibration module.

Tests guidance level determination logic and isolation from Bayesian profile.
"""

from __future__ import annotations

import pytest

from coglayer.core.models import AgeGroup, CognitiveProfile, GuidanceLevel
from coglayer.onboarding.calibration import (
    CALIBRATION_ISI_MS,
    CALIBRATION_N_TRIALS,
    CALIBRATION_NOGO_PROPORTION,
    determine_guidance_level,
)
from coglayer.profile.service import ProfileService


def test_calibration_constants() -> None:
    """Calibration task parameters are defined as documented."""
    assert CALIBRATION_N_TRIALS == 5
    assert CALIBRATION_NOGO_PROPORTION == 0.25
    assert CALIBRATION_ISI_MS == 800


def test_determine_guidance_level_child_low_accuracy() -> None:
    """Children with low accuracy get MORE guidance."""
    level = determine_guidance_level(accuracy=0.2, mean_rt_ms=500.0, age_group=AgeGroup.CHILD_7_12)
    assert level == GuidanceLevel.MORE


def test_determine_guidance_level_child_medium_accuracy() -> None:
    """Children with medium accuracy get SOME guidance."""
    level = determine_guidance_level(accuracy=0.5, mean_rt_ms=500.0, age_group=AgeGroup.CHILD_7_12)
    assert level == GuidanceLevel.SOME


def test_determine_guidance_level_child_high_accuracy() -> None:
    """Children with high accuracy get MINIMAL guidance."""
    level = determine_guidance_level(accuracy=0.8, mean_rt_ms=500.0, age_group=AgeGroup.CHILD_7_12)
    assert level == GuidanceLevel.MINIMAL


def test_determine_guidance_level_teen_low_accuracy() -> None:
    """Teens with low accuracy get MORE guidance."""
    level = determine_guidance_level(accuracy=0.2, mean_rt_ms=500.0, age_group=AgeGroup.TEEN_13_17)
    assert level == GuidanceLevel.MORE


def test_determine_guidance_level_teen_medium_accuracy() -> None:
    """Teens with medium accuracy get SOME guidance."""
    level = determine_guidance_level(accuracy=0.5, mean_rt_ms=500.0, age_group=AgeGroup.TEEN_13_17)
    assert level == GuidanceLevel.SOME


def test_determine_guidance_level_teen_high_accuracy() -> None:
    """Teens with high accuracy get MINIMAL guidance."""
    level = determine_guidance_level(accuracy=0.8, mean_rt_ms=500.0, age_group=AgeGroup.TEEN_13_17)
    assert level == GuidanceLevel.MINIMAL


def test_determine_guidance_level_adult_low_accuracy() -> None:
    """Adults with low accuracy get MORE guidance."""
    level = determine_guidance_level(accuracy=0.2, mean_rt_ms=500.0, age_group=AgeGroup.ADULT_31_60)
    assert level == GuidanceLevel.MORE


def test_determine_guidance_level_adult_medium_accuracy() -> None:
    """Adults with medium accuracy get SOME guidance."""
    level = determine_guidance_level(
        accuracy=0.45, mean_rt_ms=500.0, age_group=AgeGroup.ADULT_31_60
    )
    assert level == GuidanceLevel.SOME


def test_determine_guidance_level_adult_high_accuracy() -> None:
    """Adults with high accuracy get MINIMAL guidance."""
    level = determine_guidance_level(accuracy=0.7, mean_rt_ms=500.0, age_group=AgeGroup.ADULT_31_60)
    assert level == GuidanceLevel.MINIMAL


def test_determine_guidance_level_threshold_boundary_child() -> None:
    """Test exact threshold boundaries for children."""
    # Below MORE threshold
    assert determine_guidance_level(0.39, 500.0, AgeGroup.CHILD_7_12) == GuidanceLevel.MORE
    # At MORE threshold (boundary, should be MORE since < 0.4)
    assert determine_guidance_level(0.399, 500.0, AgeGroup.CHILD_7_12) == GuidanceLevel.MORE
    # Above MORE threshold, below SOME
    assert determine_guidance_level(0.41, 500.0, AgeGroup.CHILD_7_12) == GuidanceLevel.SOME
    # At SOME threshold (boundary, should be SOME since < 0.7)
    assert determine_guidance_level(0.699, 500.0, AgeGroup.CHILD_7_12) == GuidanceLevel.SOME
    # Above SOME threshold
    assert determine_guidance_level(0.71, 500.0, AgeGroup.CHILD_7_12) == GuidanceLevel.MINIMAL


def test_determine_guidance_level_threshold_boundary_adult() -> None:
    """Test exact threshold boundaries for adults."""
    # Below MORE threshold
    assert determine_guidance_level(0.29, 500.0, AgeGroup.ADULT_31_60) == GuidanceLevel.MORE
    # At MORE threshold (boundary, should be MORE since < 0.3)
    assert determine_guidance_level(0.299, 500.0, AgeGroup.ADULT_31_60) == GuidanceLevel.MORE
    # Above MORE threshold, below SOME
    assert determine_guidance_level(0.31, 500.0, AgeGroup.ADULT_31_60) == GuidanceLevel.SOME
    # At SOME threshold (boundary, should be SOME since < 0.6)
    assert determine_guidance_level(0.599, 500.0, AgeGroup.ADULT_31_60) == GuidanceLevel.SOME
    # Above SOME threshold
    assert determine_guidance_level(0.61, 500.0, AgeGroup.ADULT_31_60) == GuidanceLevel.MINIMAL


def test_determine_guidance_level_invalid_accuracy() -> None:
    """Accuracy outside [0, 1] raises ValueError."""
    with pytest.raises(ValueError, match="accuracy must be in \\[0, 1\\]"):
        determine_guidance_level(1.5, 500.0, AgeGroup.ADULT_31_60)

    with pytest.raises(ValueError, match="accuracy must be in \\[0, 1\\]"):
        determine_guidance_level(-0.1, 500.0, AgeGroup.ADULT_31_60)


def test_determine_guidance_level_invalid_rt() -> None:
    """Negative reaction time raises ValueError."""
    with pytest.raises(ValueError, match="mean_rt_ms must be non-negative"):
        determine_guidance_level(0.5, -100.0, AgeGroup.ADULT_31_60)


def test_calibration_isolated_from_bayesian_profile() -> None:
    """Calibration sessions do not update the Bayesian cognitive profile.

    This is a critical isolation test: ProfileService.update_from_result
    with session_type="calibration" must return the profile unchanged.
    """
    from datetime import UTC, datetime

    from coglayer.core.models import DataQuality, DimensionEstimate, TaskResult

    # Create a profile with a seeded dimension to allow updates
    profile = CognitiveProfile(
        user_id="test_user",
        dimensions={
            "response_inhibition": DimensionEstimate(
                dimension="response_inhibition",
                mean=0.5,
                lower=0.3,
                upper=0.7,
                n_evidence=1,
                last_update=datetime.now(UTC),
                alpha=1.0,
                beta_param=1.0,
            )
        },
        evidence_history=[],
        data_quality={},
        uncertainty={},
    )

    service = ProfileService()

    # Create a mock TaskResult with valid metrics
    result = TaskResult(
        task_id="go_no_go",
        task_version="1.0",
        session_id="calib_session",
        user_id="test_user",
        trials=[],
        metrics={"nogo_accuracy": 0.8, "nogo_valid_count": 2.0},
        signals=[],
        target_dimensions=["response_inhibition"],
        data_quality=DataQuality(valid_trials=5, total_trials=5, completeness=1.0, anomalies=[]),
        uncertainty=None,
    )

    # With calibration session_type, profile should be unchanged
    updated = service.update_from_result(profile, result, session_type="calibration")

    assert updated.dimensions == profile.dimensions
    assert updated.evidence_history == profile.evidence_history
    assert updated.data_quality == profile.data_quality
    assert updated.uncertainty == profile.uncertainty

    # With assessment session_type, profile should be updated
    updated_assessment = service.update_from_result(profile, result, session_type="assessment")

    # Evidence should be added for assessment
    assert len(updated_assessment.evidence_history) > len(profile.evidence_history)
