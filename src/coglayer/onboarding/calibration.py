"""Calibration task for onboarding.

Provides a short Go/No-Go variant and guidance level determination logic.
Calibration results are isolated from the Bayesian cognitive profile and only
affect ExperienceProfile.guidance_level.

Non-clinical: this is an adaptive behavior calibration, not a diagnostic.
"""

from __future__ import annotations

from typing import Final

from coglayer.core.models import AgeGroup, GuidanceLevel

__all__ = [
    "CALIBRATION_ISI_MS",
    "CALIBRATION_NOGO_PROPORTION",
    "CALIBRATION_N_TRIALS",
    "determine_guidance_level",
]

# ---------------------------------------------------------------------------
# Calibration task parameters (short Go/No-Go variant)
# ---------------------------------------------------------------------------

# Number of scored trials for calibration (short variant for quick onboarding)
CALIBRATION_N_TRIALS: Final[int] = 5

# Proportion of No-Go trials in calibration (balanced for quick assessment)
CALIBRATION_NOGO_PROPORTION: Final[float] = 0.25

# Inter-stimulus interval in milliseconds (shorter for faster calibration)
CALIBRATION_ISI_MS: Final[int] = 800

# ---------------------------------------------------------------------------
# Guidance level determination thresholds
# ---------------------------------------------------------------------------

# Thresholds for children (more lenient, default to more guidance)
_CHILD_MORE_THRESHOLD: Final[float] = 0.4
_CHILD_SOME_THRESHOLD: Final[float] = 0.7

# Thresholds for adults (stricter, allow minimal guidance)
_ADULT_MORE_THRESHOLD: Final[float] = 0.3
_ADULT_SOME_THRESHOLD: Final[float] = 0.6


def determine_guidance_level(
    accuracy: float,
    mean_rt_ms: float,
    age_group: AgeGroup,
) -> GuidanceLevel:
    """Determine guidance level from calibration performance.

    Pure function mapping accuracy and reaction time to GuidanceLevel.
    Higher accuracy and faster RT indicate need for less guidance.

    Parameters
    ----------
    accuracy:
        Proportion of correct trials in [0, 1].
    mean_rt_ms:
        Mean reaction time in milliseconds for correct Go trials.
    age_group:
        User's age group; children get more guidance by default.

    Returns
    -------
    GuidanceLevel
        'more' for users needing strong scaffolding,
        'some' for balanced support,
        'minimal' for users needing little guidance.

    Notes
    -----
    - Children (7-12) and teens (13-17) use more lenient thresholds.
    - Adults use stricter thresholds allowing minimal guidance.
    - Thresholds are constants documented above for transparency.
    - This is a non-clinical adaptive behavior setting, not a diagnosis.
    """
    if not (0.0 <= accuracy <= 1.0):
        raise ValueError(f"accuracy must be in [0, 1], got {accuracy}")

    if mean_rt_ms < 0:
        raise ValueError(f"mean_rt_ms must be non-negative, got {mean_rt_ms}")

    # Children and teens use more lenient thresholds
    if age_group in (AgeGroup.CHILD_7_12, AgeGroup.TEEN_13_17):
        if accuracy < _CHILD_MORE_THRESHOLD:
            return GuidanceLevel.MORE
        if accuracy < _CHILD_SOME_THRESHOLD:
            return GuidanceLevel.SOME
        return GuidanceLevel.MINIMAL

    # Adults use stricter thresholds
    if accuracy < _ADULT_MORE_THRESHOLD:
        return GuidanceLevel.MORE
    if accuracy < _ADULT_SOME_THRESHOLD:
        return GuidanceLevel.SOME
    return GuidanceLevel.MINIMAL
