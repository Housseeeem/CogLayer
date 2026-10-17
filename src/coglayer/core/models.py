"""Core data models for CogLayer.

All Pydantic v2 models representing the shared data contracts used across
modules. These models define the validated interface between task execution,
storage, profiling, and the decision engine.

No clinical terminology is used. This tool is not a clinical assessment.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Type alias for raw (unscored) task output
# ---------------------------------------------------------------------------

type RawTaskResult = dict[str, object]
"""The dict a TaskRunner returns before scoring -- unvalidated, untyped."""


# ---------------------------------------------------------------------------
# Trial-level models
# ---------------------------------------------------------------------------


class Trial(BaseModel):
    """A single stimulus-response trial within a task."""

    stimulus: str
    expected: str
    response: str | None  # None = no response (omission)
    rt_ms: float
    timestamp: datetime
    valid: bool
    invalid_reason: str | None  # "anticipation" | "implausibly_fast" | "timeout" | None


class Signal(BaseModel):
    """A named scalar signal produced alongside a trial (e.g. confidence)."""

    name: str  # e.g. "rt" | "confidence"
    value: float


class DataQuality(BaseModel):
    """Quality summary for a scored task result."""

    valid_trials: int
    total_trials: int
    completeness: float  # valid_trials / total_trials; 0.0 when total_trials == 0
    anomalies: list[str]

    @field_validator("completeness")
    @classmethod
    def _completeness_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"completeness must be in [0, 1], got {v}")
        return v


# ---------------------------------------------------------------------------
# Task result / descriptor
# ---------------------------------------------------------------------------


class TaskResult(BaseModel):
    """Fully validated result produced by a ScoringAdapter."""

    task_id: str
    task_version: str
    session_id: str
    user_id: str
    trials: list[Trial]
    metrics: dict[str, float]
    signals: list[Signal]
    target_dimensions: list[str]
    data_quality: DataQuality
    uncertainty: float | None


class TaskDescriptor(BaseModel):
    """Static descriptor for a registered task (stored in the TaskRegistry)."""

    task_id: str
    version: str
    instructions: str
    target_dimensions: list[str]
    parameters: dict[str, object]
    primary_metric: str | None = None
    count_metric: str | None = None


# ---------------------------------------------------------------------------
# Decision engine output
# ---------------------------------------------------------------------------


class EngineDecision(BaseModel):
    """Output produced by the AdaptiveDecisionEngine."""

    next_task: str | None = None
    status: Literal["next_task", "complete", "insufficient_data"] = "next_task"
    reason: str | None = None


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class SessionStatus(StrEnum):
    """Lifecycle states for a user session."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"


class Session(BaseModel):
    """A single assessment session for a user."""

    session_id: str
    user_id: str
    start_time: datetime
    end_time: datetime | None
    status: SessionStatus
    completed_tasks: list[str]  # task_ids completed in this session


# ---------------------------------------------------------------------------
# Profile models
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    """One piece of evidence used to update a cognitive dimension estimate."""

    dimension: str
    outcome: float  # normalised score in [0, 1]
    source: Literal["active", "passive"]
    weight: float
    timestamp: datetime
    reason_code: str
    task_id: str
    session_id: str


class DimensionEstimate(BaseModel):
    """Current Bayesian estimate for a single cognitive dimension."""

    dimension: str
    mean: float  # posterior mean; [0, 1]
    lower: float  # 90% credible interval lower bound
    upper: float  # 90% credible interval upper bound
    n_evidence: int
    last_update: datetime
    alpha: float = 1.0  # Beta distribution alpha parameter (persisted for lossless round-trip)
    beta_param: float = 1.0  # Beta distribution beta parameter (persisted for lossless round-trip)


class CognitiveProfile(BaseModel):
    """Aggregated cognitive profile for a user across all sessions."""

    user_id: str
    dimensions: dict[str, DimensionEstimate]
    evidence_history: list[Evidence]
    data_quality: dict[str, DataQuality]  # keyed by dimension
    uncertainty: dict[str, float | None]  # keyed by dimension


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


class ConsentRecord(BaseModel):
    """Record of a user's consent to data collection.

    Defined here (rather than in privacy.consent) so that core.protocols
    can reference it without creating a circular import.  The privacy.consent
    module re-uses this model directly.

    R-001.1, R-001.4: consent state is persisted and queryable.
    """

    user_id: str
    consented_at: datetime
    revoked_at: datetime | None = None
