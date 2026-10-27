"""Unit tests for DigitSpanScorer."""

from __future__ import annotations

import pytest

from coglayer.core.tasks import DIGIT_SPAN_DESCRIPTOR
from coglayer.signals.digit_span import DigitSpanScorer


@pytest.fixture
def scorer() -> DigitSpanScorer:
    return DigitSpanScorer(DIGIT_SPAN_DESCRIPTOR)


def test_digit_span_forward_and_backward_scoring(scorer: DigitSpanScorer) -> None:
    raw: dict[str, object] = {
        "session_id": "sess-1",
        "user_id": "user-1",
        "trials": [
            # Forward trials
            {
                "stimulus": "1,2,3",
                "condition": "forward",
                "response": "123",
                "length": 3,
                "rt_ms": 1200.0,
            },
            {
                "stimulus": "4,5,6,7",
                "condition": "forward",
                "response": "4567",
                "length": 4,
                "rt_ms": 1500.0,
            },
            {
                "stimulus": "8,9,1,2,3",
                "condition": "forward",
                "response": "89120",  # wrong
                "length": 5,
                "rt_ms": 2000.0,
            },
            # Backward trials
            {
                "stimulus": "1,2,3",
                "condition": "backward",
                "response": "321",
                "length": 3,
                "rt_ms": 1800.0,
            },
            {
                "stimulus": "4,5,6,7",
                "condition": "backward",
                "response": "7654",
                "length": 4,
                "rt_ms": 2200.0,
            },
            {
                "stimulus": "1,3,5,7,9",
                "condition": "backward",
                "response": "97531",
                "length": 5,
                "rt_ms": 2500.0,
            },
        ],
    }

    result = scorer.score(raw)
    assert result.task_id == "digit_span"
    assert result.metrics["forward_span"] == 4.0
    assert result.metrics["backward_span"] == 5.0
    assert result.metrics["digit_span_max"] == 5.0
    assert result.metrics["valid_trials_count"] == 6.0
    assert result.metrics["accuracy"] == pytest.approx(5 / 6, abs=1e-3)
    assert result.data_quality.completeness == 1.0
    assert len(result.trials) == 6


def test_digit_span_omissions_and_timeouts(scorer: DigitSpanScorer) -> None:
    raw: dict[str, object] = {
        "session_id": "sess-2",
        "user_id": "user-2",
        "trials": [
            {
                "stimulus": "1,2,3",
                "condition": "forward",
                "response": None,  # omission
                "rt_ms": 5000.0,
            },
            {
                "stimulus": "4,5,6",
                "condition": "forward",
                "response": "456",
                "rt_ms": 35000.0,  # timeout > 30000
            },
            {
                "stimulus": "7,8,9",
                "condition": "forward",
                "response": "789",
                "rt_ms": 1200.0,
            },
        ],
    }

    result = scorer.score(raw)
    assert result.trials[0].invalid_reason == "omission"
    assert result.trials[1].valid is False
    assert result.trials[1].invalid_reason == "timeout"
    assert result.trials[2].valid is True
    assert result.metrics["forward_span"] == 3.0


def test_digit_span_empty_trials(scorer: DigitSpanScorer) -> None:
    raw: dict[str, object] = {"session_id": "sess-empty", "user_id": "user-empty", "trials": []}
    result = scorer.score(raw)
    assert result.metrics["valid_trials_count"] == 0.0
    assert result.metrics["digit_span_max"] == 0.0
    assert result.metrics["accuracy"] == 0.0
    assert result.data_quality.completeness == 0.0
