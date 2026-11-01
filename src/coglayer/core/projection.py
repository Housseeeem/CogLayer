"""Possible-trajectory projections from historical dimension evidence."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite, sqrt

from pydantic import BaseModel, Field
from scipy.stats import t as student_t

from coglayer.core.models import Evidence

PROJECTION_CAVEAT = (
    "Possible trajectory based on past results only. It is not a prediction or a certainty."
)
_MINIMUM_OBSERVATIONS = 5


class ProjectionPoint(BaseModel):
    """One projected session with a mean and 90% prediction interval."""

    session_index: int = Field(ge=1)
    mean: float = Field(ge=0.0, le=1.0)
    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)


class DimensionProjection(BaseModel):
    """Possible trajectory and uncertainty for one cognitive dimension."""

    dimension: str
    slope: float
    intervals: list[ProjectionPoint]
    n_observations: int = Field(ge=0)
    status: str
    caveat: str = PROJECTION_CAVEAT


class ProjectionResponse(BaseModel):
    """Projection response containing one result for every observed dimension."""

    projections: dict[str, DimensionProjection]


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _insufficient(dimension: str, n_observations: int, slope: float = 0.0) -> DimensionProjection:
    return DimensionProjection(
        dimension=dimension,
        slope=slope,
        intervals=[],
        n_observations=n_observations,
        status="INSUFFICIENT_DATA",
    )


def project_dimension(
    dimension: str,
    observations: Sequence[float],
    *,
    horizon: int = 3,
) -> DimensionProjection:
    """Project the next sessions from normalized chronological outcomes.

    Returns a 90% prediction interval for each projected session. At least five
    finite observations are required; a constant series has no usable trend.
    """
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    values = [float(value) for value in observations]
    if any(not isfinite(value) for value in values):
        raise ValueError("observations must contain only finite numbers")
    n = len(values)
    if n < _MINIMUM_OBSERVATIONS:
        return _insufficient(dimension, n)

    x_mean = (n - 1) / 2.0
    sxx = sum((index - x_mean) ** 2 for index in range(n))
    y_mean = sum(values) / n
    slope = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / sxx
    intercept = y_mean - slope * x_mean
    residuals = [value - (intercept + slope * index) for index, value in enumerate(values)]
    sse = sum(residual * residual for residual in residuals)
    if sse <= 1e-14 and abs(slope) <= 1e-14:
        return _insufficient(dimension, n, slope)

    residual_standard_error = 0.0 if sse <= 1e-12 else sqrt(sse / (n - 2))
    critical_value = float(student_t.ppf(0.95, n - 2))
    intervals: list[ProjectionPoint] = []
    for offset in range(1, horizon + 1):
        session_index = n + offset
        x_value = session_index - 1
        mean = intercept + slope * x_value
        prediction_error = residual_standard_error * sqrt(
            1.0 + (1.0 / n) + ((x_value - x_mean) ** 2 / sxx)
        )
        margin = critical_value * prediction_error
        intervals.append(
            ProjectionPoint(
                session_index=session_index,
                mean=_clamp(mean),
                lower=_clamp(mean - margin),
                upper=_clamp(mean + margin),
            )
        )
    return DimensionProjection(
        dimension=dimension,
        slope=slope,
        intervals=intervals,
        n_observations=n,
        status="AVAILABLE",
    )


def project_evidence(
    evidence: Sequence[Evidence],
    *,
    horizon: int = 3,
) -> ProjectionResponse:
    """Project each dimension independently from timestamp-ordered evidence."""
    by_dimension: dict[str, list[Evidence]] = {}
    for item in evidence:
        by_dimension.setdefault(item.dimension, []).append(item)
    projections = {
        dimension: project_dimension(
            dimension,
            [item.outcome for item in sorted(items, key=lambda item: item.timestamp)],
            horizon=horizon,
        )
        for dimension, items in sorted(by_dimension.items())
    }
    return ProjectionResponse(projections=projections)
