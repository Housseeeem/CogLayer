"""Onboarding module for CogLayer.

Provides calibration task and guidance level determination for personalized
experience profiles. Calibration sessions are isolated from the Bayesian
cognitive profile and only affect ExperienceProfile.guidance_level.
"""

from __future__ import annotations

from coglayer.onboarding.calibration import (
    CALIBRATION_ISI_MS,
    CALIBRATION_N_TRIALS,
    CALIBRATION_NOGO_PROPORTION,
    determine_guidance_level,
)

__all__ = [
    "CALIBRATION_ISI_MS",
    "CALIBRATION_NOGO_PROPORTION",
    "CALIBRATION_N_TRIALS",
    "determine_guidance_level",
]
