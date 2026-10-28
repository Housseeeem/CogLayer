"""Small, transparent baseline signal based on exponential moving averages."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from math import isfinite

from pydantic import BaseModel, Field

from coglayer.core.models import Evidence


class BrainTwinState(StrEnum):
    """Coach-facing state derived from comparable EMA observations."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NO_VARIATION = "NO_VARIATION"
    VARIATION_FLAGGED = "VARIATION_FLAGGED"


class BrainTwinSignal(BaseModel):
    """Minimal typed context that the Coach may use."""

    state: BrainTwinState
    comparable_observation_count: int = Field(ge=0)
    flagged_observation_id: str | None = None


class EMAPoint(BaseModel):
    """One EMA prediction and residual for a comparable measurement."""

    observation: float
    prediction: float
    residual: float = Field(ge=0.0)
    threshold: float | None = Field(default=None, ge=0.0)
    flagged: bool = False


class EMAResult(BaseModel):
    """EMA output with an explicit data-sufficiency status."""

    points: list[EMAPoint]
    status: str
    alpha: float = Field(gt=0.0, le=1.0)
    sigma_multiplier: float = Field(gt=0.0)


def comparable_brain_twin_evidence(evidence: Sequence[Evidence]) -> list[Evidence]:
    """Return comparable Go/No-Go evidence in calculation order."""
    return sorted(
        (
            item
            for item in evidence
            if item.task_id == "go_no_go" and item.dimension == "response_inhibition"
        ),
        key=lambda item: item.timestamp,
    )


def evidence_observation_id(evidence: Evidence) -> str:
    """Build a stable identity from the source evidence metadata."""
    task_version = evidence.task_version or ""
    return "|".join(
        (
            evidence.session_id,
            evidence.task_id,
            evidence.dimension,
            evidence.timestamp.isoformat(),
            evidence.reason_code,
            task_version,
        )
    )


def build_brain_twin_analysis(evidence: Sequence[Evidence]) -> tuple[EMAResult, BrainTwinSignal]:
    """Calculate the EMA result and its minimal Coach-facing interpretation."""
    comparable = comparable_brain_twin_evidence(evidence)
    result = calculate_ema_signal([item.outcome for item in comparable])
    if result.status != "AVAILABLE":
        signal = BrainTwinSignal(
            state=BrainTwinState.INSUFFICIENT_DATA,
            comparable_observation_count=len(comparable),
        )
    else:
        flagged_indices = [index for index, point in enumerate(result.points) if point.flagged]
        if not flagged_indices:
            signal = BrainTwinSignal(
                state=BrainTwinState.NO_VARIATION,
                comparable_observation_count=len(comparable),
            )
        else:
            source = comparable[flagged_indices[-1]]
            signal = BrainTwinSignal(
                state=BrainTwinState.VARIATION_FLAGGED,
                comparable_observation_count=len(comparable),
                flagged_observation_id=evidence_observation_id(source),
            )
    return result, signal


def build_brain_twin_signal(evidence: Sequence[Evidence]) -> BrainTwinSignal:
    """Derive Coach context from profile evidence without changing EMA behavior."""
    _, signal = build_brain_twin_analysis(evidence)
    return signal


def calculate_ema_signal(
    observations: Sequence[float],
    *,
    alpha: float = 0.3,
    sigma_multiplier: float = 1.5,
    minimum_observations: int = 4,
) -> EMAResult:
    """Calculate a transparent EMA baseline and optional variation flags.

    Values must be comparable and use the same unit and direction. A flag is
    withheld until enough prior residuals exist to estimate their spread.
    """
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in (0, 1]")
    if sigma_multiplier <= 0.0:
        raise ValueError("sigma_multiplier must be positive")
    if minimum_observations < 2:
        raise ValueError("minimum_observations must be at least 2")
    if any(
        not isinstance(value, (int, float)) or not isfinite(float(value)) for value in observations
    ):
        raise ValueError("observations must contain only numeric values")

    values = [float(value) for value in observations]
    if not values:
        return EMAResult(
            points=[],
            status="INSUFFICIENT_DATA",
            alpha=alpha,
            sigma_multiplier=sigma_multiplier,
        )

    points: list[EMAPoint] = []
    prediction = values[0]
    residuals: list[float] = []
    for observation in values:
        residual = abs(observation - prediction)
        threshold: float | None = None
        flagged = False
        if len(residuals) >= 2:
            mean = sum(residuals) / len(residuals)
            variance = sum((item - mean) ** 2 for item in residuals) / len(residuals)
            threshold = mean + sigma_multiplier * variance**0.5
            flagged = residual > threshold
        points.append(
            EMAPoint(
                observation=observation,
                prediction=prediction,
                residual=residual,
                threshold=threshold,
                flagged=flagged,
            )
        )
        residuals.append(residual)
        prediction = alpha * observation + (1.0 - alpha) * prediction

    status = "AVAILABLE" if len(values) >= minimum_observations else "INSUFFICIENT_DATA"
    if status == "INSUFFICIENT_DATA":
        points = [point.model_copy(update={"flagged": False}) for point in points]
    return EMAResult(
        points=points,
        status=status,
        alpha=alpha,
        sigma_multiplier=sigma_multiplier,
    )
