"""Sequence Span task scorer for CogLayer.

This task measures sequential visual memory via spatial sequence reproduction.
It is used as a proxy for working-memory capacity but does not purely measure
working memory.

Requirements: R-004.1 to R-004.4
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from coglayer.core.models import (
    DataQuality,
    RawTaskResult,
    TaskResult,
    Trial,
)
from coglayer.core.settings import Settings, get_settings

__all__ = [
    "SEQUENCE_TIMEOUT_MS",
    "SequenceSpanRunner",
    "SequenceSpanScorer",
]

# Maximum allowed response time per sequence. Sequences exceeding this
# threshold are marked invalid with invalid_reason="timeout" (R-004.4).
SEQUENCE_TIMEOUT_MS: Final[float] = 30_000.0


class SequenceSpanScorer:
    """ScoringAdapter for the Visual Sequence Span task.

    Transforms a raw dict produced by the UI (or submitted via the API) into a
    fully validated ``TaskResult``.  Exclusion rules and metric definitions
    follow R-004.3 and R-004.4.

    This task measures sequential visual memory via spatial sequence
    reproduction. It is used as a proxy for working-memory capacity but does
    not purely measure working memory.

    Requirements: R-004.2, R-004.3, R-004.4
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    def score(self, raw: RawTaskResult) -> TaskResult:
        """Score a raw Sequence Span result.

        Args:
            raw: A dict with the following keys:

                - ``"sequences"`` (list[dict]): Each dict is one trial with:

                    - ``"stimulus"`` (str): The shown sequence (e.g. ``"1,2,3"``).
                    - ``"expected"`` (str): The correct reproduction (same as stimulus).
                    - ``"response"`` (str | None): The user's reproduction.
                    - ``"rt_ms"`` (float): Response time for the entire sequence.
                    - ``"timestamp"`` (str): ISO-format timestamp string.
                    - ``"valid"`` (bool, default ``True``): Pre-existing validity flag.
                    - ``"invalid_reason"`` (str | None, default ``None``).
                    - ``"length"`` (int): Sequence length.

                - ``"session_id"`` (str)
                - ``"user_id"`` (str)
                - ``"task_version"`` (str, default ``"1.0"``)

        Returns:
            A fully populated ``TaskResult``.

        Requirements: R-004.3, R-004.4
        """
        raw_sequences = raw.get("sequences", [])
        assert isinstance(raw_sequences, list)
        sequences: list[dict[str, object]] = raw_sequences
        session_id: str = str(raw.get("session_id", ""))
        user_id: str = str(raw.get("user_id", ""))
        task_version: str = str(raw.get("task_version", "1.0"))

        trials: list[Trial] = []

        for seq in sequences:
            stimulus: str = str(seq.get("stimulus", ""))
            expected: str = str(seq.get("expected", ""))
            response_raw = seq.get("response")
            response: str | None = str(response_raw) if response_raw is not None else None
            rt_ms: float = float(seq.get("rt_ms", 0.0))  # type: ignore[arg-type]
            timestamp_raw = seq.get("timestamp", "")
            timestamp: datetime = datetime.fromisoformat(str(timestamp_raw))
            valid: bool = bool(seq.get("valid", True))
            invalid_reason: str | None = (
                str(seq["invalid_reason"]) if seq.get("invalid_reason") is not None else None
            )

            # R-004.4: Mark as invalid when response time exceeds the timeout threshold.
            if rt_ms > SEQUENCE_TIMEOUT_MS:
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

        # --- Compute metrics from valid sequences only (R-004.3) ---

        total: int = len(trials)
        valid_trials_list = [t for t in trials if t.valid]
        valid_count: int = len(valid_trials_list)

        # correct_sequences: valid sequences where response == expected
        correct_sequences: int = sum(
            1 for t in valid_trials_list if t.response is not None and t.response == t.expected
        )

        # order_errors: valid sequences where response has the same items as
        # expected but in a different order.
        #
        # Split on comma to compare item sets faithfully regardless of spacing.
        def _items(s: str) -> list[str]:
            return [x.strip() for x in s.split(",")]

        order_errors: int = sum(
            1
            for t in valid_trials_list
            if (
                t.response is not None
                and set(_items(t.response)) == set(_items(t.expected))
                and t.response != t.expected
            )
        )

        # max_span: longest sequence length with at least one correct valid reproduction.
        # We infer the length from the expected field (number of comma-separated items)
        # because the raw 'length' field is consumed into the trial stimulus but Trial
        # does not carry it.  Both approaches give the same answer.
        max_span: int = 0
        for seq, trial in zip(sequences, trials, strict=True):
            if trial.valid and trial.response is not None and trial.response == trial.expected:
                raw_len = seq.get("length", len(_items(trial.expected)))
                length_from_raw = (
                    int(raw_len)
                    if isinstance(raw_len, int | str | float)
                    else len(_items(trial.expected))
                )
                if length_from_raw > max_span:
                    max_span = length_from_raw

        # mean_rt_ms: mean RT across all valid sequences (0.0 if none)
        mean_rt_ms: float = (
            sum(t.rt_ms for t in valid_trials_list) / valid_count if valid_count > 0 else 0.0
        )

        # correct_sequences_ratio: proportion of correct sequences where timeouts count
        # as failed trials in the denominator (valid_count + timeout_count).
        # (used by the profile service's DIMENSION_MAPPING)
        timeout_count: int = sum(1 for t in trials if t.invalid_reason == "timeout")
        total_sequences_denominator: int = valid_count + timeout_count
        correct_sequences_ratio: float = (
            correct_sequences / total_sequences_denominator
            if total_sequences_denominator > 0
            else 0.0
        )

        metrics: dict[str, float] = {
            "max_span": float(max_span),
            "correct_sequences": float(correct_sequences),
            "order_errors": float(order_errors),
            "mean_rt_ms": mean_rt_ms,
            "valid_sequence_count": float(valid_count),
            "correct_sequences_ratio": correct_sequences_ratio,
        }

        settings = self._settings or get_settings()
        completeness: float = valid_count / total if total > 0 else 0.0

        anomalies: list[str] = []
        if completeness < settings.completeness_threshold:
            anomalies.append("low_completeness")

        data_quality = DataQuality(
            valid_trials=valid_count,
            total_trials=total,
            completeness=completeness,
            anomalies=anomalies,
        )

        return TaskResult(
            task_id="sequence_span",
            task_version=task_version,
            session_id=session_id,
            user_id=user_id,
            trials=trials,
            metrics=metrics,
            signals=[],
            target_dimensions=["sequential_visual_memory"],
            data_quality=data_quality,
            uncertainty=None,
        )


class SequenceSpanRunner:
    """TaskRunner stub for the Visual Sequence Span task.

    The task is UI-driven: stimulus presentation and response capture happen
    in the browser via Streamlit.  Invoke the scorer directly with the raw
    data collected by the UI.

    Requirements: R-002.2
    """

    def run(
        self,
        session_id: str,
        user_id: str,
        parameters: dict[str, object],
    ) -> RawTaskResult:
        """Not implemented — the task is driven by the UI layer.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("UI-driven; call scorer directly")
