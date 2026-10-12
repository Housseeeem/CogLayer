"""CogLayer profile package — Bayesian Beta profile model and service."""

from coglayer.profile.model import DEFAULT_FORGETTING_FACTOR, BetaProfileModel
from coglayer.profile.service import DIMENSION_MAPPING, ProfileService

__all__ = [
    "DEFAULT_FORGETTING_FACTOR",
    "DIMENSION_MAPPING",
    "BetaProfileModel",
    "ProfileService",
]
