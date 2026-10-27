"""Stroop task scoring adapter for CogLayer.

Measures selective attention, interference control, and cognitive flexibility
by comparing response latency and accuracy under congruent vs incongruent
semantic conditions.

Non-clinical statement: This task measures reaction times and interference
resolution under standardized visual color-naming conditions. It is not
a clinical assessment.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from coglayer.core.models import (
    DataQuality,
    RawTaskResult,
    Signal,
    TaskDescriptor,
    TaskResult,
    Trial,
)
from coglayer.core.tasks import STROOP_DESCRIPTOR

__all__ = [
    "STROOP_ANTICIPATION_MS",
    "STROOP_TIMEOUT_MS",
    "StroopScorer",
]

STROOP_ANTICIPATION_MS: Final[float] = 150.0
STROOP_TIMEOUT_MS: Final[float] = 3000.0


class StroopScorer:
    """Scoring adapter for the Stroop cognitive interference task."""

    def __init__(self, descriptor: TaskDescriptor = STROOP_DESCRIPTOR) -> None:
        self.descriptor = descriptor

    def score(self, raw: RawTaskResult) -> TaskResult:
        """Score raw Stroop trials and return a validated TaskResult."""
        raw_trials = raw.get("trials", [])
        if not isinstance(raw_trials, list):
            raw_trials = []

        session_id = str(raw.get("session_id", ""))
        user_id = str(raw.get("user_id", ""))
        task_version = str(raw.get("task_version", self.descriptor.version))

        trials: list[Trial] = []
        trial_conditions: list[str] = []

        for item in raw_trials:
            if not isinstance(item, dict):
                continue
            stimulus = str(item.get("stimulus", "")).strip().upper()
            expected = str(item.get("expected", item.get("ink_color", ""))).strip().upper()

            resp_raw = item.get("response")
            response = str(resp_raw).strip().upper() if resp_raw is not None else None

            # Determine condition if not explicitly provided
            condition = str(item.get("condition", "")).lower()
            if not condition:
                condition = "congruent" if stimulus == expected else "incongruent"

            try:
                rt_ms = float(item.get("rt_ms", 0.0))
            except (ValueError, TypeError):
                rt_ms = 0.0

            ts_raw = item.get("timestamp")
            if ts_raw:
                try:
                    timestamp = datetime.fromisoformat(str(ts_raw))
                except ValueError:
                    timestamp = datetime.now(UTC)
            else:
                timestamp = datetime.now(UTC)

            valid = bool(item.get("valid", True))
            invalid_reason: str | None = (
                str(item["invalid_reason"]) if item.get("invalid_reason") is not None else None
            )

            # Apply standard exclusion rules
            if response is None or len(response) == 0:
                valid = False
                invalid_reason = "omission"
            elif rt_ms < STROOP_ANTICIPATION_MS:
                valid = False
                invalid_reason = "anticipation"
            elif rt_ms > STROOP_TIMEOUT_MS:
                valid = False
                invalid_reason = "timeout"

            trials.append(
                Trial(
                    stimulus=stimulus,
                    expected=expected,
                    response=response,
                    rt_ms=rt_ms,
                    timestamp=timestamp,
                    valid=valid,
                    invalid_reason=invalid_reason,
                )
            )
            trial_conditions.append(condition)

        total_trials = len(trials)
        valid_trials = [t for t in trials if t.valid]
        valid_count = len(valid_trials)

        congruent_trials = [
            (t, cond)
            for t, cond in zip(trials, trial_conditions, strict=True)
            if t.valid and cond == "congruent"
        ]
        incongruent_trials = [
            (t, cond)
            for t, cond in zip(trials, trial_conditions, strict=True)
            if t.valid and cond == "incongruent"
        ]

        congruent_correct = [t for t, _ in congruent_trials if t.response == t.expected]
        incongruent_correct = [t for t, _ in incongruent_trials if t.response == t.expected]

        n_cong = len(congruent_trials)
        n_incong = len(incongruent_trials)

        congruent_acc = (len(congruent_correct) / n_cong) if n_cong > 0 else 0.0
        incongruent_acc = (len(incongruent_correct) / n_incong) if n_incong > 0 else 0.0
        overall_correct = len(congruent_correct) + len(incongruent_correct)
        overall_acc = (overall_correct / valid_count) if valid_count > 0 else 0.0

        congruent_rt = (
            sum(t.rt_ms for t in congruent_correct) / len(congruent_correct)
            if congruent_correct
            else 0.0
        )
        incongruent_rt = (
            sum(t.rt_ms for t in incongruent_correct) / len(incongruent_correct)
            if incongruent_correct
            else 0.0
        )

        stroop_effect = (
            max(0.0, incongruent_rt - congruent_rt)
            if (congruent_correct and incongruent_correct)
            else 0.0
        )
        mean_rt = sum(t.rt_ms for t in valid_trials) / valid_count if valid_count > 0 else 0.0

        metrics: dict[str, float] = {
            "incongruent_accuracy": round(incongruent_acc, 4),
            "congruent_accuracy": round(congruent_acc, 4),
            "overall_accuracy": round(overall_acc, 4),
            "stroop_effect_ms": round(stroop_effect, 2),
            "mean_rt_congruent_ms": round(congruent_rt, 2),
            "mean_rt_incongruent_ms": round(incongruent_rt, 2),
            "mean_rt_ms": round(mean_rt, 2),
            "valid_trials_count": float(valid_count),
        }

        signals = [
            Signal(name="incongruent_accuracy", value=incongruent_acc),
            Signal(name="stroop_effect_ms", value=stroop_effect),
        ]

        anomalies: list[str] = []
        if total_trials > 0 and valid_count < 4:
            anomalies.append("low_valid_trial_count")

        completeness = (valid_count / total_trials) if total_trials > 0 else 0.0
        data_quality = DataQuality(
            valid_trials=valid_count,
            total_trials=total_trials,
            completeness=completeness,
            anomalies=anomalies,
        )

        return TaskResult(
            task_id=self.descriptor.task_id,
            task_version=task_version,
            session_id=session_id,
            user_id=user_id,
            trials=trials,
            metrics=metrics,
            signals=signals,
            target_dimensions=list(self.descriptor.target_dimensions),
            data_quality=data_quality,
            uncertainty=None,
        )
