"""N-Back task scoring adapter for CogLayer.

Measures continuous working memory updating and monitoring using the N-back
paradigm (default 2-Back), incorporating Signal Detection Theory metrics (d-prime).

Non-clinical statement: This task measures performance on continuous stimulus
comparison under standardized timing. It is not a clinical assessment.
"""

from __future__ import annotations

import math
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
from coglayer.core.tasks import N_BACK_DESCRIPTOR

__all__ = [
    "N_BACK_ANTICIPATION_MS",
    "N_BACK_TIMEOUT_MS",
    "NBackScorer",
]

N_BACK_ANTICIPATION_MS: Final[float] = 100.0
N_BACK_TIMEOUT_MS: Final[float] = 3000.0


def _probit(p: float) -> float:
    """Standard normal quantile function (inverse CDF) using rational approximation."""
    # Clamp probability to avoid inf
    p = max(1e-5, min(1.0 - 1e-5, p))
    # Approximation of inverse error function via Winitzki / Hastings
    # Phi^-1(p) = sqrt(2) * erfinv(2p - 1)
    y = 2.0 * p - 1.0
    a = 0.147
    sgn = 1.0 if y >= 0 else -1.0
    ln_term = math.log(max(1e-12, 1.0 - y * y))
    term1 = 2.0 / (math.pi * a) + ln_term / 2.0
    inner = term1 * term1 - ln_term / a
    erf_inv = sgn * math.sqrt(max(0.0, math.sqrt(max(0.0, inner)) - term1))
    return math.sqrt(2.0) * erf_inv


class NBackScorer:
    """Scoring adapter for the N-Back working memory updating task."""

    def __init__(self, descriptor: TaskDescriptor = N_BACK_DESCRIPTOR) -> None:
        self.descriptor = descriptor

    def score(self, raw: RawTaskResult) -> TaskResult:
        """Score raw N-Back trials and return a validated TaskResult."""
        raw_trials = raw.get("trials", [])
        if not isinstance(raw_trials, list):
            raw_trials = []

        session_id = str(raw.get("session_id", ""))
        user_id = str(raw.get("user_id", ""))
        task_version = str(raw.get("task_version", self.descriptor.version))

        trials: list[Trial] = []
        is_target_list: list[bool] = []

        for item in raw_trials:
            if not isinstance(item, dict):
                continue
            stimulus = str(item.get("stimulus", "")).strip().upper()
            is_target = bool(item.get("is_target", False))
            expected = "MATCH" if is_target else "NO_MATCH"

            resp_raw = item.get("response")
            if resp_raw is not None:
                resp_str = str(resp_raw).strip().upper()
                if resp_str in {"MATCH", "TRUE", "1", "YES"}:
                    response: str | None = "MATCH"
                elif resp_str in {"NO_MATCH", "FALSE", "0", "NO"}:
                    response = "NO_MATCH"
                else:
                    response = resp_str
            else:
                response = None

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
            elif rt_ms < N_BACK_ANTICIPATION_MS:
                valid = False
                invalid_reason = "anticipation"
            elif rt_ms > N_BACK_TIMEOUT_MS:
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
            is_target_list.append(is_target)

        total_trials = len(trials)
        valid_trials = [t for t in trials if t.valid]
        valid_count = len(valid_trials)

        hits = 0
        misses = 0
        false_alarms = 0
        correct_rejections = 0

        for t, is_target in zip(trials, is_target_list, strict=True):
            if not t.valid:
                continue
            answered_match = t.response == "MATCH"
            if is_target:
                if answered_match:
                    hits += 1
                else:
                    misses += 1
            else:
                if answered_match:
                    false_alarms += 1
                else:
                    correct_rejections += 1

        total_targets = hits + misses
        total_non_targets = false_alarms + correct_rejections

        # Signal detection edge corrections (Macmillan & Kaplan, 1985)
        if total_targets > 0:
            hit_rate_adj = (hits + 0.5) / (total_targets + 1.0)
            target_acc = hits / total_targets
        else:
            hit_rate_adj = 0.5
            target_acc = 0.0

        if total_non_targets > 0:
            fa_rate_adj = (false_alarms + 0.5) / (total_non_targets + 1.0)
            fa_rate = false_alarms / total_non_targets
        else:
            fa_rate_adj = 0.5
            fa_rate = 0.0

        d_prime = _probit(hit_rate_adj) - _probit(fa_rate_adj)
        # Ensure finite non-negative/reasonable d'
        d_prime = max(0.0, min(5.0, d_prime))

        total_correct = hits + correct_rejections
        overall_accuracy = (total_correct / valid_count) if valid_count > 0 else 0.0
        mean_rt = sum(t.rt_ms for t in valid_trials) / valid_count if valid_count > 0 else 0.0

        metrics: dict[str, float] = {
            "n_back_accuracy": round(overall_accuracy, 4),
            "target_accuracy": round(target_acc, 4),
            "false_alarm_rate": round(fa_rate, 4),
            "d_prime": round(d_prime, 3),
            "mean_rt_ms": round(mean_rt, 2),
            "hits": float(hits),
            "false_alarms": float(false_alarms),
            "valid_trials_count": float(valid_count),
        }

        signals = [
            Signal(name="n_back_accuracy", value=overall_accuracy),
            Signal(name="d_prime", value=d_prime),
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
