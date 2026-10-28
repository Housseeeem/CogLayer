"""Perception and visual bistability task scoring adapter for CogLayer.

Measures perceptual switching rate on bistable figures (Necker Cube, Rubin Vase,
Ambiguous Figures) and visual search latency in Change Blindness flicker tasks.

Non-clinical statement: This task measures subjective perceptual report dynamics
and visual search times. It is not a clinical assessment.
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
from coglayer.core.tasks import PERCEPTION_DESCRIPTOR

__all__ = ["PERCEPTION_MAX_RT_MS", "PerceptionScorer"]

PERCEPTION_MAX_RT_MS: Final[float] = 60000.0


class PerceptionScorer:
    """Scoring adapter for perceptual illusions and change detection tasks."""

    def __init__(self, descriptor: TaskDescriptor = PERCEPTION_DESCRIPTOR) -> None:
        self.descriptor = descriptor

    def score(self, raw: RawTaskResult) -> TaskResult:
        """Score raw perception trials and return a validated TaskResult."""
        raw_trials = raw.get("trials", [])
        if not isinstance(raw_trials, list):
            raw_trials = []

        session_id = str(raw.get("session_id", ""))
        user_id = str(raw.get("user_id", ""))
        task_version = str(raw.get("task_version", self.descriptor.version))

        trials: list[Trial] = []
        switch_counts: list[float] = []
        detection_correct: list[bool] = []

        for item in raw_trials:
            if not isinstance(item, dict):
                continue
            stimulus = str(item.get("stimulus", "")).strip().lower()
            expected = str(item.get("expected", "REPORT")).strip().upper()

            resp_raw = item.get("response")
            response = str(resp_raw).strip() if resp_raw is not None else None

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

            if response is None or len(response) == 0:
                valid = False
                invalid_reason = "omission"
            elif rt_ms > PERCEPTION_MAX_RT_MS:
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

            if valid and response:
                if "necker" in stimulus or "switch" in stimulus:
                    try:
                        switch_counts.append(float(response))
                    except ValueError:
                        pass
                elif "change" in stimulus or "blindness" in stimulus:
                    detection_correct.append(response.upper() == expected)

        total_trials = len(trials)
        valid_trials = [t for t in trials if t.valid]
        valid_count = len(valid_trials)

        switch_rate = (sum(switch_counts) / len(switch_counts)) if switch_counts else 0.0
        det_rate = (
            (sum(1 for c in detection_correct if c) / len(detection_correct))
            if detection_correct
            else 1.0
        )

        # Perceptual stability proxy: inverse of excessive switching, normalized in [0, 1]
        stability = max(0.0, min(1.0, 1.0 - (switch_rate / 30.0)))
        mean_rt = sum(t.rt_ms for t in valid_trials) / valid_count if valid_count > 0 else 0.0

        metrics: dict[str, float] = {
            "perceptual_stability": round(stability, 4),
            "switch_rate": round(switch_rate, 2),
            "detection_rate": round(det_rate, 4),
            "mean_rt_ms": round(mean_rt, 2),
            "valid_trials_count": float(valid_count),
        }

        signals = [
            Signal(name="perceptual_stability", value=stability),
            Signal(name="switch_rate", value=switch_rate),
        ]

        anomalies: list[str] = []
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
