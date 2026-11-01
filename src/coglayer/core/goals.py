"""Goal tracking and dimension mapping.

Maps user onboarding goals to cognitive dimensions and tracks progress
from baseline (earliest evidence) to target (+10 percentage points, capped at 100%),
with 90% credible intervals and non-clinical status messaging.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

__all__ = [
    "GoalProgress",
    "GoalTrackingResponse",
    "compute_goal_progress",
    "map_goal_to_dimensions",
]

# Canonical age-appropriate goals mapped to cognitive dimensions
GOAL_TO_DIMENSIONS_MAP: dict[str, list[str]] = {
    # Child (7-12)
    "Improve focus during homework": ["response_inhibition"],
    "Learn to pay attention longer": ["response_inhibition", "cognitive_flexibility"],
    "Get better at following instructions": ["working_memory", "sequential_visual_memory"],
    "Practice quick thinking": ["cognitive_flexibility", "response_inhibition"],
    # Teen (13-17)
    "Improve study focus": ["response_inhibition"],
    "Manage distractions better": ["response_inhibition"],
    "Build faster thinking skills": ["cognitive_flexibility"],
    "Practice self-control": ["response_inhibition"],
    # Young Adult (18-30)
    "Boost productivity at work": ["working_memory", "cognitive_flexibility"],
    "Improve focus during learning": ["response_inhibition", "working_memory"],
    "Practice quick decision-making": ["cognitive_flexibility", "response_inhibition"],
    "Build attention skills": ["response_inhibition"],
    # Adult (31-60)
    "Maintain mental sharpness": ["working_memory", "cognitive_flexibility"],
    "Improve work focus": ["response_inhibition"],
    "Reduce distractions": ["response_inhibition"],
    # Senior (60+)
    "Keep the mind active": ["cognitive_flexibility", "working_memory"],
    "Practice quick responses": ["response_inhibition"],
    "Maintain attention skills": ["response_inhibition"],
    "Stay mentally sharp": ["working_memory", "cognitive_flexibility"],
}

# Heuristic keywords for custom / arbitrary goal strings
KEYWORD_MAPPINGS: list[tuple[list[str], str]] = [
    (
        ["focus", "distract", "attention", "control", "inhibit", "response", "homework", "study"],
        "response_inhibition",
    ),
    (
        ["memory", "instruction", "span", "remember", "recall", "follow", "learn"],
        "working_memory",
    ),
    (
        ["visual", "sequence", "spatial", "pattern", "block"],
        "sequential_visual_memory",
    ),
    (
        ["flexib", "switch", "think", "sharp", "decision", "speed", "active", "productivity"],
        "cognitive_flexibility",
    ),
]


class GoalProgress(BaseModel):
    """Progress for a single user goal."""

    goal: str
    target_dimensions: list[str]
    status: Literal["insufficient_data", "active", "completed"]
    status_text: str
    n_sessions: int
    baseline: float | None = None
    current: float | None = None
    target: float | None = None
    lower: float | None = None
    upper: float | None = None
    progress_ratio: float | None = None


class GoalTrackingResponse(BaseModel):
    """API response model for user goal tracking."""

    user_id: str
    goals: list[GoalProgress]
    disclaimer: str = Field(
        default="Based on the tasks completed so far — not a clinical assessment."
    )


def map_goal_to_dimensions(goal: str) -> list[str]:
    """Map a goal string to one or more cognitive dimensions.

    Uses exact canonical lookup first, then keyword matching,
    and defaults to ['working_memory', 'response_inhibition'] if unrecognised.
    """
    clean_goal = goal.strip()
    if clean_goal in GOAL_TO_DIMENSIONS_MAP:
        return list(GOAL_TO_DIMENSIONS_MAP[clean_goal])

    lower = clean_goal.lower()
    matched_dims: list[str] = []
    for keywords, dim in KEYWORD_MAPPINGS:
        if any(kw in lower for kw in keywords) and dim not in matched_dims:
            matched_dims.append(dim)

    if matched_dims:
        return matched_dims

    return ["working_memory", "response_inhibition"]


def compute_goal_progress(
    goal: str,
    profile_data: dict[str, Any],
    *,
    baseline_n: int = 1,
    target_delta: float = 0.10,
    min_sessions: int = 3,
) -> GoalProgress:
    """Compute progress for a single goal from profile data.

    Args:
        goal: Goal description string.
        profile_data: Serialized or deserialized CognitiveProfile dict/object.
        baseline_n: Number of earliest evidence items to compute baseline (default 1).
        target_delta: Delta added to baseline to set target (default 0.10, clamped <= 1.0).
        min_sessions: Minimum observations required before showing active progress (default 3).

    Returns:
        GoalProgress populated with baseline, current, target, credible intervals, and status.
    """
    dims = map_goal_to_dimensions(goal)

    # Extract raw evidence history
    evidence_history: list[dict[str, Any]] = []
    raw_history = (
        profile_data.evidence_history
        if hasattr(profile_data, "evidence_history")
        else profile_data.get("evidence_history", [])
    )
    for ev in raw_history:
        if hasattr(ev, "model_dump"):
            evidence_history.append(ev.model_dump())
        elif isinstance(ev, dict):
            evidence_history.append(ev)

    # Extract dimensions estimates
    raw_dims = (
        profile_data.dimensions
        if hasattr(profile_data, "dimensions")
        else profile_data.get("dimensions", {})
    )
    dim_estimates: dict[str, dict[str, Any]] = {}
    for k, v in raw_dims.items():
        if hasattr(v, "model_dump"):
            dim_estimates[k] = v.model_dump()
        elif isinstance(v, dict):
            dim_estimates[k] = v

    baselines: list[float] = []
    currents: list[float] = []
    lowers: list[float] = []
    uppers: list[float] = []
    session_counts: list[int] = []

    for dim in dims:
        # Filter and sort evidence chronologically
        dim_ev = [
            e
            for e in evidence_history
            if str(e.get("dimension", "")).strip() == dim and "outcome" in e
        ]
        dim_ev.sort(key=lambda e: str(e.get("timestamp", "")))

        # Determine session count for this dimension
        n_obs = len(dim_ev)
        if dim in dim_estimates:
            est_n = int(dim_estimates[dim].get("n_evidence", 0))
            n_obs = max(n_obs, est_n)
        session_counts.append(n_obs)

        if not dim_ev:
            continue

        # Baseline: posterior mean after first N observations with Beta(1,1) prior
        earliest_ev = dim_ev[:baseline_n]
        alpha = 1.0
        beta_p = 1.0
        for e in earliest_ev:
            w = float(e.get("weight", 1.0))
            n_eff = min(w, 20.0) if w > 0 else 1.0
            out = float(e.get("outcome", 0.0))
            alpha += n_eff * out
            beta_p += n_eff * (1.0 - out)
        dim_baseline = alpha / (alpha + beta_p)
        baselines.append(dim_baseline)

        # Current estimate and 90% credible interval
        if dim in dim_estimates:
            est = dim_estimates[dim]
            c_mean = float(est.get("mean", dim_baseline))
            c_lower = float(est.get("lower", c_mean))
            c_upper = float(est.get("upper", c_mean))
            currents.append(c_mean)
            lowers.append(c_lower)
            uppers.append(c_upper)
        else:
            currents.append(dim_baseline)
            lowers.append(dim_baseline)
            uppers.append(dim_baseline)

    total_sessions = min(session_counts) if session_counts else 0

    if not baselines or total_sessions < min_sessions:
        # Insufficient data
        b_val = (sum(baselines) / len(baselines)) if baselines else None
        c_val = (sum(currents) / len(currents)) if currents else None
        t_val = min(1.0, b_val + target_delta) if b_val is not None else None
        l_val = (sum(lowers) / len(lowers)) if lowers else None
        u_val = (sum(uppers) / len(uppers)) if uppers else None
        return GoalProgress(
            goal=goal,
            target_dimensions=dims,
            status="insufficient_data",
            status_text="Not enough data yet",
            n_sessions=total_sessions,
            baseline=round(b_val, 4) if b_val is not None else None,
            current=round(c_val, 4) if c_val is not None else None,
            target=round(t_val, 4) if t_val is not None else None,
            lower=round(l_val, 4) if l_val is not None else None,
            upper=round(u_val, 4) if u_val is not None else None,
            progress_ratio=None,
        )

    # Compute composite averages across mapped dimensions
    avg_baseline = sum(baselines) / len(baselines)
    avg_current = sum(currents) / len(currents)
    avg_target = min(1.0, avg_baseline + target_delta)
    avg_lower = sum(lowers) / len(lowers)
    avg_upper = sum(uppers) / len(uppers)

    if avg_target > avg_baseline:
        ratio = max(0.0, min(1.0, (avg_current - avg_baseline) / (avg_target - avg_baseline)))
    else:
        ratio = 1.0 if avg_current >= avg_target else 0.0

    is_completed = avg_current >= avg_target
    status_lit: Literal["insufficient_data", "active", "completed"] = (
        "completed" if is_completed else "active"
    )
    status_str = "Target reached" if is_completed else "In progress"

    return GoalProgress(
        goal=goal,
        target_dimensions=dims,
        status=status_lit,
        status_text=status_str,
        n_sessions=total_sessions,
        baseline=round(avg_baseline, 4),
        current=round(avg_current, 4),
        target=round(avg_target, 4),
        lower=round(avg_lower, 4),
        upper=round(avg_upper, 4),
        progress_ratio=round(ratio, 4),
    )
