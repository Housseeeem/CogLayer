"""Core data models for CogLayer.

All Pydantic v2 models representing the shared data contracts used across
modules. These models define the validated interface between task execution,
storage, profiling, and the decision engine.

No clinical terminology is used. This tool is not a clinical assessment.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

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

    def is_sufficient_for_completion(self) -> bool:
        """Return True if data quality meets minimum criteria for task completion.

        Criteria:
        - At least one valid trial (valid_trials > 0)
        - Completeness >= 0.50
        - No 'low_completeness' anomaly
        - No 'unknown_task_version' anomaly
        """
        if self.valid_trials <= 0:
            return False
        if self.completeness < 0.50:
            return False
        if "low_completeness" in self.anomalies:
            return False
        if "unknown_task_version" in self.anomalies:
            return False
        return True


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


ReadingStatus = Literal["profile", "observation", "quality"]


class Reading(BaseModel):
    """A metric reading produced by a task with its dimensional status and caveats."""

    metric: str
    dimension: str
    status: Literal["profile", "observation", "quality"]
    caveat: str | None = None


class TaskDescriptor(BaseModel):
    """Static descriptor for a registered task (stored in the TaskRegistry)."""

    task_id: str
    version: str
    instructions: str
    target_dimensions: list[str]
    parameters: dict[str, object]
    primary_metric: str | None = None
    count_metric: str | None = None
    readings: list[Reading] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_interpretation_rules(self) -> Self:
        # Rule (c): NO numeric weights anywhere
        if "weight" in self.parameters or "weights" in self.parameters:
            raise ValueError("Numeric weights are forbidden anywhere in TaskDescriptor parameters.")

        # Synthesize profile reading if readings is empty but primary_metric is given
        if not self.readings and self.primary_metric and self.target_dimensions:
            self.readings = [
                Reading(metric=self.primary_metric, dimension=dim, status="profile")
                for dim in self.target_dimensions
            ]

        # Rule (a): exactly one status="profile" reading per target dimension
        if self.readings:
            profile_readings = [r for r in self.readings if r.status == "profile"]
            for dim in self.target_dimensions:
                matching = [r for r in profile_readings if r.dimension == dim]
                if len(matching) != 1:
                    raise ValueError(
                        f"Target dimension '{dim}' must have exactly one status='profile' reading, "
                        f"found {len(matching)}."
                    )
            # Rule (b): the profile reading is the single source of the primary metric
            if profile_readings:
                object.__setattr__(self, "primary_metric", profile_readings[0].metric)
            else:
                object.__setattr__(self, "primary_metric", None)
        return self


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


class SessionType(StrEnum):
    """Type of session (assessment vs calibration)."""

    ASSESSMENT = "assessment"
    CALIBRATION = "calibration"


class Session(BaseModel):
    """A single assessment session for a user."""

    session_id: str
    user_id: str
    start_time: datetime
    end_time: datetime | None
    status: SessionStatus
    session_type: SessionType = SessionType.ASSESSMENT
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
    task_version: str | None = None


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
# Indice Opérationnel d'Interaction (IOI)
# ---------------------------------------------------------------------------


class IOIComponent(StrEnum):
    """Operational interaction components scored by the IOI."""

    CRITICAL_VERIFICATION = "critical_verification"
    CLARIFICATION = "clarification"
    ITERATION = "iteration"
    AUTONOMY = "autonomy"
    RESPONSIBLE_USAGE = "responsible_usage"


class IOIEventType(StrEnum):
    """Explicit, extensible event types that create IOI opportunities."""

    VERIFICATION_OPPORTUNITY = "verification_opportunity"
    CLARIFICATION_OPPORTUNITY = "clarification_opportunity"
    ITERATION_OPPORTUNITY = "iteration_opportunity"
    AUTONOMY_OPPORTUNITY = "autonomy_opportunity"
    RESPONSIBLE_USAGE_OPPORTUNITY = "responsible_usage_opportunity"


IOI_COMPONENT_EVENT_TYPES: dict[IOIComponent, IOIEventType] = {
    IOIComponent.CRITICAL_VERIFICATION: IOIEventType.VERIFICATION_OPPORTUNITY,
    IOIComponent.CLARIFICATION: IOIEventType.CLARIFICATION_OPPORTUNITY,
    IOIComponent.ITERATION: IOIEventType.ITERATION_OPPORTUNITY,
    IOIComponent.AUTONOMY: IOIEventType.AUTONOMY_OPPORTUNITY,
    IOIComponent.RESPONSIBLE_USAGE: IOIEventType.RESPONSIBLE_USAGE_OPPORTUNITY,
}


class IOIObservation(BaseModel):
    """One explicitly recorded, binary IOI opportunity and its outcome."""

    event_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    component: IOIComponent
    event_type: IOIEventType
    opportunity_id: str = Field(min_length=1, max_length=128)
    behavior_observed: bool
    valid: bool = True
    timestamp: datetime
    schema_version: str = Field(min_length=1, max_length=32)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_event_definition(self) -> Self:
        expected_type = IOI_COMPONENT_EVENT_TYPES.get(self.component)
        if self.event_type is not expected_type:
            raise ValueError(
                f"event type {self.event_type.value!r} is not allowed for "
                f"component {self.component.value!r}"
            )
        if len(self.metadata) > 8:
            raise ValueError("metadata must contain at most 8 fields")
        for key, value in self.metadata.items():
            if not key or len(key) > 32 or not key.replace("_", "").isalnum():
                raise ValueError("metadata keys must be short machine-readable names")
            if isinstance(value, str) and len(value) > 64:
                raise ValueError("metadata string values must be at most 64 characters")
            if key.lower() in {"prompt", "response", "message", "text", "conversation"}:
                raise ValueError("metadata cannot contain raw conversation fields")
        return self


class IOIComponentScore(BaseModel):
    """Score and evidence status for one IOI component."""

    score: float = Field(ge=0.0, le=1.0)
    evidence_count: int = Field(ge=0)
    weight: float = Field(ge=0.0, le=1.0)
    sufficient: bool


class IOIScore(BaseModel):
    """Pure IOI result with an unavailable aggregate when evidence is incomplete."""

    user_id: str
    components: dict[IOIComponent, IOIComponentScore]
    aggregate_score: float | None = Field(default=None, ge=0.0, le=1.0)
    status: Literal["AVAILABLE", "INSUFFICIENT_EVIDENCE"]
    calculation_version: str


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
    guardian_consent: bool = False
    guardian_id: str | None = None


# ---------------------------------------------------------------------------
# Adaptive Daily Selection Contracts (Preparation)
# ---------------------------------------------------------------------------


class GuidanceLevel(StrEnum):
    """Level of guidance and scaffolding."""

    MORE = "more"
    SOME = "some"
    MINIMAL = "minimal"


class AdaptiveRecommendationCriteria(BaseModel):
    """Explicit parameters used to generate a deterministic daily activity plan."""

    user_id: str
    session_id: str | None = None
    historical_completeness: float = Field(default=1.0, ge=0.0, le=1.0)
    target_dimensions: list[str] = Field(default_factory=list)
    target_game_count: int = Field(default=3, ge=1, le=5)
    excluded_task_ids: list[str] = Field(default_factory=list)
    plan_date: str | None = None
    subjective_feedback: str | None = None
    guidance_level: GuidanceLevel | None = None

    @field_validator("plan_date")
    @classmethod
    def _validate_plan_date(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError as e:
                raise ValueError(f"plan_date must be in YYYY-MM-DD format, got {v!r}") from e
        return v


class AdaptiveGameRecommendation(BaseModel):
    """One recommended cognitive activity with explainable non-clinical rationale."""

    task_id: str
    rationale: str
    target_dimension: str
    difficulty_level: str = "standard"
    task_version: str = "1.0"


class AdaptiveDailyPlan(BaseModel):
    """Structured daily plan providing targeted, diverse cognitive activities."""

    user_id: str
    plan_date: str
    recommendations: list[AdaptiveGameRecommendation]
    deterministic_seed: int
    session_id: str | None = None
    status: Literal["generated", "started", "completed"] = "generated"
    factors_used: list[str] = Field(default_factory=list)
    fallback_strategy: str | None = None
    is_personalized: bool = False

    @field_validator("plan_date")
    @classmethod
    def _validate_plan_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"plan_date must be in YYYY-MM-DD format, got {v!r}") from e
        return v


# ---------------------------------------------------------------------------
# Conversational Coach models
# ---------------------------------------------------------------------------


class CoachMessageRole(StrEnum):
    """Role of a message in a coaching conversation."""

    USER = "user"
    ASSISTANT = "assistant"


class CoachMessage(BaseModel):
    """A single message in a coaching conversation."""

    message_id: int | None = None  # Set by repository on save
    conversation_id: str
    role: CoachMessageRole
    content: str = Field(min_length=1, max_length=8192)
    timestamp: datetime


class CoachConversation(BaseModel):
    """A coaching conversation with message history."""

    conversation_id: str
    user_id: str
    session_id: str | None = None
    created_at: datetime
    messages: list[CoachMessage] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Experience Profile for Personalized Onboarding
# ---------------------------------------------------------------------------


class AgeGroup(StrEnum):
    """Age group categories for personalized experience."""

    CHILD_7_12 = "child_7_12"
    TEEN_13_17 = "teen_13_17"
    YOUNG_ADULT_18_30 = "young_adult_18_30"
    ADULT_31_60 = "adult_31_60"
    SENIOR_60_PLUS = "senior_60_plus"


class TechComfort(StrEnum):
    """Self-reported comfort level with technology."""

    NEW = "new"
    SOME_EXPERIENCE = "some_experience"
    COMFORTABLE = "comfortable"
    VERY_COMFORTABLE = "very_comfortable"


class InfoStyle(StrEnum):
    """Preferred information presentation style."""

    VISUAL = "visual"
    STEP_BY_STEP = "step_by_step"
    SHORT_SIMPLE = "short_simple"
    DETAILED = "detailed"
    CONVERSATIONAL = "conversational"


class LayoutType(StrEnum):
    """Preferred UI layout pattern."""

    GUIDED_JOURNEY = "guided_journey"
    DASHBOARD = "dashboard"
    CONVERSATION_FIRST = "conversation_first"
    MINIMAL = "minimal"


class ThemeType(StrEnum):
    """Visual theme preference."""

    LARGER_TEXT = "larger_text"
    STANDARD = "standard"
    HIGH_CONTRAST = "high_contrast"
    SOFTER_COLORS = "softer_colors"
    BRIGHTER_COLORS = "brighter_colors"


class ExperienceProfile(BaseModel):
    """User's personalized experience profile for adaptive behavior.

    Captures age group, goals, technology comfort, information style,
    layout/theme preferences, and guidance level to drive adaptive behavior
    across coach, task selector, navigation, and presentation.
    """

    user_id: str
    age_group: AgeGroup
    goals: list[str] = Field(min_length=1)
    tech_comfort: TechComfort
    info_style: InfoStyle
    layout: LayoutType
    theme: ThemeType
    guidance_level: GuidanceLevel | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
