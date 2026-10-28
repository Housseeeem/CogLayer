"""Digit Span task scoring adapter for CogLayer.

Measures verbal working memory through direct (forward) and reverse (backward)
digit recall.

Non-clinical statement: This task measures performance on sequential digit recall
under standardized conditions. It is not a clinical assessment.
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
from coglayer.core.tasks import DIGIT_SPAN_DESCRIPTOR

__all__ = ["DIGIT_SPAN_TIMEOUT_MS", "DigitSpanScorer"]

DIGIT_SPAN_TIMEOUT_MS: Final[float] = 30000.0


def _normalize_digits(val: object) -> str:
    """Normalize comma, space or plain digit strings to a comparable string."""
    if val is None:
        return ""
    s = str(val).strip()
    # Strip spaces, commas, hyphens
    return "".join(ch for ch in s if ch.isdigit())


class DigitSpanScorer:
    """Scoring adapter for the Digit Span cognitive task."""

    def __init__(self, descriptor: TaskDescriptor = DIGIT_SPAN_DESCRIPTOR) -> None:
        self.descriptor = descriptor

    def score(self, raw: RawTaskResult) -> TaskResult:
        """Score raw Digit Span trials and return a validated TaskResult."""
        raw_trials = raw.get("trials", raw.get("sequences", []))
        if not isinstance(raw_trials, list):
            raw_trials = []

        session_id = str(raw.get("session_id", ""))
        user_id = str(raw.get("user_id", ""))
        task_version = str(raw.get("task_version", self.descriptor.version))

        trials: list[Trial] = []
        trial_conditions: list[str] = []
        trial_lengths: list[int] = []

        for item in raw_trials:
            if not isinstance(item, dict):
                continue
            stimulus_raw = item.get("stimulus", "")
            condition = str(item.get("condition", "forward")).lower()
            expected_raw = item.get("expected")

            norm_stim = _normalize_digits(stimulus_raw)
            if expected_raw is not None:
                norm_expected = _normalize_digits(expected_raw)
            else:
                norm_expected = norm_stim[::-1] if condition == "backward" else norm_stim

            resp_raw = item.get("response")
            norm_resp = _normalize_digits(resp_raw) if resp_raw is not None else None

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

            if rt_ms > DIGIT_SPAN_TIMEOUT_MS:
                valid = False
                invalid_reason = "timeout"
            elif norm_resp is None or len(norm_resp) == 0:
                # Omission
                if not invalid_reason:
                    invalid_reason = "omission"

            trials.append(
                Trial(
                    stimulus=norm_stim,
                    expected=norm_expected,
                    response=norm_resp,
                    rt_ms=rt_ms,
                    timestamp=timestamp,
                    valid=valid,
                    invalid_reason=invalid_reason,
                )
            )

            length_val = item.get("length")
            if isinstance(length_val, int) and length_val > 0:
                length = length_val
            else:
                length = len(norm_stim)

            trial_conditions.append(condition)
            trial_lengths.append(length)

        total_trials = len(trials)
        valid_trials = [t for t in trials if t.valid]
        valid_count = len(valid_trials)

        forward_correct_lengths: list[int] = []
        backward_correct_lengths: list[int] = []
        forward_valid_count = 0
        backward_valid_count = 0
        forward_correct_count = 0
        backward_correct_count = 0

        for t, cond, length in zip(trials, trial_conditions, trial_lengths, strict=True):
            if not t.valid:
                continue
            is_correct = t.response is not None and t.response == t.expected
            if cond == "backward":
                backward_valid_count += 1
                if is_correct:
                    backward_correct_count += 1
                    backward_correct_lengths.append(length)
            else:
                forward_valid_count += 1
                if is_correct:
                    forward_correct_count += 1
                    forward_correct_lengths.append(length)

        forward_span = max(forward_correct_lengths) if forward_correct_lengths else 0
        backward_span = max(backward_correct_lengths) if backward_correct_lengths else 0
        digit_span_max = max(forward_span, backward_span)

        total_correct = forward_correct_count + backward_correct_count
        overall_accuracy = (total_correct / valid_count) if valid_count > 0 else 0.0
        forward_acc = (
            (forward_correct_count / forward_valid_count) if forward_valid_count > 0 else 0.0
        )
        backward_acc = (
            (backward_correct_count / backward_valid_count) if backward_valid_count > 0 else 0.0
        )
        mean_rt = sum(t.rt_ms for t in valid_trials) / valid_count if valid_count > 0 else 0.0

        metrics: dict[str, float] = {
            "accuracy": round(overall_accuracy, 4),
            "forward_accuracy": round(forward_acc, 4),
            "backward_accuracy": round(backward_acc, 4),
            "digit_span_max": float(digit_span_max),
            "forward_span": float(forward_span),
            "backward_span": float(backward_span),
            "mean_rt_ms": round(mean_rt, 2),
            "valid_trials_count": float(valid_count),
        }

        signals = [
            Signal(name="accuracy", value=overall_accuracy),
            Signal(name="forward_span", value=float(forward_span)),
            Signal(name="backward_span", value=float(backward_span)),
        ]

        anomalies: list[str] = []
        if total_trials > 0 and valid_count < 2:
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
