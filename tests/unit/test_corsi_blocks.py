"""Unit tests for CorsiBlocksScorer."""

from __future__ import annotations

import pytest

from coglayer.core.tasks import CORSI_BLOCKS_DESCRIPTOR
from coglayer.signals.corsi_blocks import CorsiBlocksScorer


@pytest.fixture
def scorer() -> CorsiBlocksScorer:
    return CorsiBlocksScorer(CORSI_BLOCKS_DESCRIPTOR)


def test_corsi_forward_and_backward_scoring(scorer: CorsiBlocksScorer) -> None:
    raw: dict[str, object] = {
        "session_id": "sess-corsi-1",
        "user_id": "user-corsi",
        "sequences": [
            # Forward: reproduce in same order
            {
                "stimulus": "1,4,7",
                "condition": "forward",
                "response": "1,4,7",
                "length": 3,
                "rt_ms": 2500.0,
            },
            {
                "stimulus": "2,5,8,3",
                "condition": "forward",
                "response": "2,5,8,3",
                "length": 4,
                "rt_ms": 3200.0,
            },
            {
                "stimulus": "6,1,9,4,2",
                "condition": "forward",
                "response": "6,1,9,4,8",  # incorrect
                "length": 5,
                "rt_ms": 4000.0,
            },
            # Backward: reproduce in reverse order
            {
                "stimulus": "1,4,7",
                "condition": "backward",
                "response": "7,4,1",
                "length": 3,
                "rt_ms": 2800.0,
            },
            {
                "stimulus": "2,5,8,3",
                "condition": "backward",
                "response": "3,8,5,2",
                "length": 4,
                "rt_ms": 3500.0,
            },
        ],
    }

    result = scorer.score(raw)
    assert result.task_id == "corsi_blocks"
    assert result.metrics["forward_span"] == 4.0
    assert result.metrics["backward_span"] == 4.0
    assert result.metrics["corsi_span_max"] == 4.0
    assert result.metrics["valid_sequences_count"] == 5.0
    assert result.metrics["forward_accuracy"] == pytest.approx(2 / 3, abs=1e-3)
    assert result.metrics["backward_accuracy"] == 1.0


def test_corsi_timeout_exclusion(scorer: CorsiBlocksScorer) -> None:
    raw: dict[str, object] = {
        "session_id": "sess-corsi-timeout",
        "user_id": "user-corsi",
        "sequences": [
            {
                "stimulus": "1,2,3",
                "condition": "forward",
                "response": "1,2,3",
                "rt_ms": 35000.0,  # exceeds 30000ms
            },
            {
                "stimulus": "4,5,6",
                "condition": "forward",
                "response": "4,5,6",
                "rt_ms": 2000.0,
            },
        ],
    }

    result = scorer.score(raw)
    assert result.trials[0].valid is False
    assert result.trials[0].invalid_reason == "timeout"
    assert result.trials[1].valid is True
    assert result.metrics["valid_sequences_count"] == 1.0
