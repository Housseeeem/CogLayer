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
    flagged_dimensions: list[str] = Field(default_factory=list)


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


class DimensionBrainTwinResult(BaseModel):
    """EMA result and signal for a single dimension."""

    dimension: str
    ema: EMAResult
    signal: BrainTwinSignal


class PerDimensionBrainTwinResult(BaseModel):
    """Per-dimension Brain Twin results plus the legacy response_inhibition result."""

    # Legacy top-level fields for backward compatibility
    points: list[EMAPoint]
    status: str
    alpha: float = Field(gt=0.0, le=1.0)
    sigma_multiplier: float = Field(gt=0.0)

    # New: per-dimension map
    dimensions: dict[str, DimensionBrainTwinResult] = Field(default_factory=dict)
    flagged_dimensions: list[str] = Field(default_factory=list)


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


def comparable_evidence_for_dimension(
    evidence: Sequence[Evidence],
    dimension: str,
) -> list[Evidence]:
    """Return comparable evidence for a specific dimension, ordered by timestamp.

    Comparable means: same dimension and task_id. When a dimension has more
    than one task, use the task with the most observations so the returned
    series remains internally comparable.
    """
    dim_evidence = [item for item in evidence if item.dimension == dimension]
    if not dim_evidence:
        return []

    # Group by task_id, pick the one with most observations
    by_task: dict[str, list[Evidence]] = {}
    for item in dim_evidence:
        by_task.setdefault(item.task_id, []).append(item)

    best_task = min(
        by_task,
        key=lambda task_id: (-len(by_task[task_id]), task_id),
    )
    return sorted(by_task[best_task], key=lambda item: item.timestamp)


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


def _build_signal_from_ema(
    result: EMAResult,
    comparable: list[Evidence],
) -> BrainTwinSignal:
    """Derive a BrainTwinSignal from an EMAResult and its source evidence."""
    if result.status != "AVAILABLE":
        return BrainTwinSignal(
            state=BrainTwinState.INSUFFICIENT_DATA,
            comparable_observation_count=len(comparable),
        )

    flagged_indices = [index for index, point in enumerate(result.points) if point.flagged]
    if not flagged_indices:
        return BrainTwinSignal(
            state=BrainTwinState.NO_VARIATION,
            comparable_observation_count=len(comparable),
        )

    source = comparable[flagged_indices[-1]]
    return BrainTwinSignal(
        state=BrainTwinState.VARIATION_FLAGGED,
        comparable_observation_count=len(comparable),
        flagged_observation_id=evidence_observation_id(source),
        flagged_dimensions=[source.dimension],
    )


def build_brain_twin_analysis(
    evidence: Sequence[Evidence],
) -> tuple[EMAResult, BrainTwinSignal]:
    """Calculate the EMA result and its minimal Coach-facing interpretation.

    This is the backward-compatible API: operates on Go/No-Go response_inhibition
    evidence only.
    """
    comparable = comparable_brain_twin_evidence(evidence)
    result = calculate_ema_signal([item.outcome for item in comparable])
    signal = _build_signal_from_ema(result, comparable)
    return result, signal


def build_per_dimension_analysis(
    evidence: Sequence[Evidence],
) -> PerDimensionBrainTwinResult:
    """Calculate EMA results per dimension and the legacy Go/No-Go result.

    Returns a combined result with the legacy top-level fields (for backward
    compatibility with the existing Go/No-Go brain-twin endpoint) plus a
    per-dimension map.
    """
    # Legacy: Go/No-Go response_inhibition
    legacy_result, _ = build_brain_twin_analysis(evidence)

    # Discover all dimensions present in the evidence
    all_dims: set[str] = set()
    for item in evidence:
        if item.dimension:
            all_dims.add(item.dimension)

    dim_results: dict[str, DimensionBrainTwinResult] = {}
    flagged_dims: list[str] = []

    for dim in sorted(all_dims):
        comparable = comparable_evidence_for_dimension(evidence, dim)
        ema = calculate_ema_signal([item.outcome for item in comparable])
        signal = _build_signal_from_ema(ema, comparable)
        if signal.state is BrainTwinState.VARIATION_FLAGGED:
            signal = signal.model_copy(update={"flagged_dimensions": [dim]})
        dim_results[dim] = DimensionBrainTwinResult(
            dimension=dim,
            ema=ema,
            signal=signal,
        )
        if signal.state is BrainTwinState.VARIATION_FLAGGED:
            flagged_dims.append(dim)

    return PerDimensionBrainTwinResult(
        points=legacy_result.points,
        status=legacy_result.status,
        alpha=legacy_result.alpha,
        sigma_multiplier=legacy_result.sigma_multiplier,
        dimensions=dim_results,
        flagged_dimensions=flagged_dims,
    )


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
