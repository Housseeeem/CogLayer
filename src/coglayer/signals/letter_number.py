"""Letter-Number Sequencing task scoring adapter for CogLayer.

Measures active mental manipulation and working memory capacity by presenting
mixed letters and numbers that must be reordered (numbers ascending, letters
alphabetically).

Non-clinical statement: This task measures performance on mental manipulation
under standardized rules. It is not a clinical assessment.
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
from coglayer.core.tasks import LETTER_NUMBER_DESCRIPTOR

__all__ = ["LETTER_NUMBER_TIMEOUT_MS", "LetterNumberSequencingScorer"]

LETTER_NUMBER_TIMEOUT_MS: Final[float] = 30000.0


def _parse_tokens(s: object) -> list[str]:
    """Extract alphanumeric characters as individual tokens."""
    if s is None:
        return []
    text = str(s).upper().replace(",", " ").strip()
    return [ch for token in text.split() for ch in token if ch.isalnum()]


def sort_letter_number_tokens(tokens: list[str]) -> list[str]:
    """Sort tokens: numbers ascending first, then letters alphabetically."""
    nums: list[int] = []
    letters: list[str] = []
    for tok in tokens:
        if tok.isdigit():
            nums.append(int(tok))
        elif tok.isalpha():
            letters.append(tok.upper())
    nums.sort()
    letters.sort()
    return [str(n) for n in nums] + letters


class LetterNumberSequencingScorer:
    """Scoring adapter for Letter-Number Sequencing."""

    def __init__(self, descriptor: TaskDescriptor = LETTER_NUMBER_DESCRIPTOR) -> None:
        self.descriptor = descriptor

    def score(self, raw: RawTaskResult) -> TaskResult:
        """Score raw Letter-Number trials and return a validated TaskResult."""
        raw_trials = raw.get("trials", raw.get("sequences", []))
        if not isinstance(raw_trials, list):
            raw_trials = []

        session_id = str(raw.get("session_id", ""))
        user_id = str(raw.get("user_id", ""))
        task_version = str(raw.get("task_version", self.descriptor.version))

        trials: list[Trial] = []
        trial_lengths: list[int] = []

        for item in raw_trials:
            if not isinstance(item, dict):
                continue
            stim_tokens = _parse_tokens(item.get("stimulus"))
            expected_raw = item.get("expected")
            if expected_raw is not None:
                exp_tokens = _parse_tokens(expected_raw)
            else:
                exp_tokens = sort_letter_number_tokens(stim_tokens)

            resp_raw = item.get("response")
            resp_tokens = _parse_tokens(resp_raw) if resp_raw is not None else []

            norm_stim = " ".join(stim_tokens)
            norm_exp = " ".join(exp_tokens)
            norm_resp = " ".join(resp_tokens) if resp_raw is not None else None

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

            if rt_ms > LETTER_NUMBER_TIMEOUT_MS:
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

            len_val = item.get("length")
            if isinstance(len_val, int) and len_val > 0:
                trial_lengths.append(len_val)
            else:
                trial_lengths.append(len(stim_tokens))

        total_trials = len(trials)
        valid_trials = [t for t in trials if t.valid]
        valid_count = len(valid_trials)

        correct_lengths: list[int] = []
        correct_count = 0

        for t, length in zip(trials, trial_lengths, strict=True):
            if not t.valid:
                continue
            if t.response is not None and t.response == t.expected:
                correct_count += 1
                correct_lengths.append(length)

        lns_span_max = max(correct_lengths) if correct_lengths else 0
        accuracy = (correct_count / valid_count) if valid_count > 0 else 0.0
        mean_rt = sum(t.rt_ms for t in valid_trials) / valid_count if valid_count > 0 else 0.0

        metrics: dict[str, float] = {
            "accuracy": round(accuracy, 4),
            "lns_span_max": float(lns_span_max),
            "mean_rt_ms": round(mean_rt, 2),
            "valid_trials_count": float(valid_count),
        }

        signals = [
            Signal(name="accuracy", value=accuracy),
            Signal(name="lns_span_max", value=float(lns_span_max)),
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
