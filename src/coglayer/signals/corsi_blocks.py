"""Corsi Blocks task scoring adapter for CogLayer.

Measures visuospatial working memory span via spatial block sequence reproduction
in direct (forward) and reverse (backward) conditions.

Non-clinical statement: This task measures performance on spatial block sequence
reproduction. It is not a clinical assessment.
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
from coglayer.core.tasks import CORSI_BLOCKS_DESCRIPTOR

__all__ = ["CORSI_TIMEOUT_MS", "CorsiBlocksScorer"]

CORSI_TIMEOUT_MS: Final[float] = 30000.0


def _parse_sequence_tokens(val: object) -> list[str]:
    """Parse comma or space separated tokens into clean elements."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    s = str(val).replace(",", " ").strip()
    return [token for token in s.split() if token]


class CorsiBlocksScorer:
    """Scoring adapter for the Corsi Blocks visuospatial memory task."""

    def __init__(self, descriptor: TaskDescriptor = CORSI_BLOCKS_DESCRIPTOR) -> None:
        self.descriptor = descriptor

    def score(self, raw: RawTaskResult) -> TaskResult:
        """Score raw Corsi Blocks trials and return a validated TaskResult."""
        raw_sequences = raw.get("sequences", raw.get("trials", []))
        if not isinstance(raw_sequences, list):
            raw_sequences = []

        session_id = str(raw.get("session_id", ""))
        user_id = str(raw.get("user_id", ""))
        task_version = str(raw.get("task_version", self.descriptor.version))

        trials: list[Trial] = []
        trial_conditions: list[str] = []
        trial_lengths: list[int] = []

        for item in raw_sequences:
            if not isinstance(item, dict):
                continue
            stim_tokens = _parse_sequence_tokens(item.get("stimulus"))
            condition = str(item.get("condition", "forward")).lower()
            expected_raw = item.get("expected")

            if expected_raw is not None:
                exp_tokens = _parse_sequence_tokens(expected_raw)
            else:
                exp_tokens = list(reversed(stim_tokens)) if condition == "backward" else stim_tokens

            resp_raw = item.get("response")
            resp_tokens = _parse_sequence_tokens(resp_raw) if resp_raw is not None else []
            norm_stim = ",".join(stim_tokens)
            norm_exp = ",".join(exp_tokens)
            norm_resp = ",".join(resp_tokens) if resp_raw is not None else None

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

            if rt_ms > CORSI_TIMEOUT_MS:
                valid = False
                invalid_reason = "timeout"
            elif norm_resp is None or len(resp_tokens) == 0:
                if not invalid_reason:
                    invalid_reason = "omission"

            trials.append(
                Trial(
                    stimulus=norm_stim,
                    expected=norm_exp,
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
                length = len(stim_tokens)

            trial_conditions.append(condition)
            trial_lengths.append(length)

        total_trials = len(trials)
        valid_trials = [t for t in trials if t.valid]
        valid_count = len(valid_trials)

        forward_correct_lengths: list[int] = []
        backward_correct_lengths: list[int] = []
        forward_valid = 0
        backward_valid = 0
        forward_correct = 0
        backward_correct = 0

        for t, cond, length in zip(trials, trial_conditions, trial_lengths, strict=True):
            if not t.valid:
                continue
            is_correct = t.response is not None and t.response == t.expected
            if cond == "backward":
                backward_valid += 1
                if is_correct:
                    backward_correct += 1
                    backward_correct_lengths.append(length)
            else:
                forward_valid += 1
                if is_correct:
                    forward_correct += 1
                    forward_correct_lengths.append(length)

        forward_span = max(forward_correct_lengths) if forward_correct_lengths else 0
        backward_span = max(backward_correct_lengths) if backward_correct_lengths else 0
        corsi_span_max = max(forward_span, backward_span)

        total_correct = forward_correct + backward_correct
        accuracy = (total_correct / valid_count) if valid_count > 0 else 0.0
        forward_acc = (forward_correct / forward_valid) if forward_valid > 0 else 0.0
        backward_acc = (backward_correct / backward_valid) if backward_valid > 0 else 0.0
        mean_rt = sum(t.rt_ms for t in valid_trials) / valid_count if valid_count > 0 else 0.0

        metrics: dict[str, float] = {
            "accuracy": round(accuracy, 4),
            "forward_accuracy": round(forward_acc, 4),
            "backward_accuracy": round(backward_acc, 4),
            "corsi_span_max": float(corsi_span_max),
            "forward_span": float(forward_span),
            "backward_span": float(backward_span),
            "mean_rt_ms": round(mean_rt, 2),
            "valid_sequences_count": float(valid_count),
        }

        signals = [
            Signal(name="accuracy", value=accuracy),
            Signal(name="corsi_span_max", value=float(corsi_span_max)),
        ]

        anomalies: list[str] = []
        if total_trials > 0 and valid_count < 2:
            anomalies.append("low_valid_sequences_count")

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
