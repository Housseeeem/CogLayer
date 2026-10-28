"""Unit tests for LetterNumberSequencingScorer."""

from __future__ import annotations

import pytest

from coglayer.core.tasks import LETTER_NUMBER_DESCRIPTOR
from coglayer.signals.letter_number import (
    LetterNumberSequencingScorer,
    sort_letter_number_tokens,
)


@pytest.fixture
def scorer() -> LetterNumberSequencingScorer:
    return LetterNumberSequencingScorer(LETTER_NUMBER_DESCRIPTOR)


def test_sort_letter_number_rule() -> None:
    tokens = ["C", "2", "B", "1", "9", "A"]
    sorted_tokens = sort_letter_number_tokens(tokens)
    assert sorted_tokens == ["1", "2", "9", "A", "B", "C"]


def test_letter_number_scoring(scorer: LetterNumberSequencingScorer) -> None:
    raw: dict[str, object] = {
        "session_id": "sess-lns-1",
        "user_id": "user-lns",
        "trials": [
            {
                "stimulus": "B 1",
                "response": "1 B",
                "length": 2,
                "rt_ms": 2000.0,
            },
            {
                "stimulus": "C 3 A",
                "response": "3 A C",
                "length": 3,
                "rt_ms": 3000.0,
            },
            {
                "stimulus": "Z 5 M 2",
                "response": "2 5 M Z",
                "length": 4,
                "rt_ms": 4000.0,
            },
            {
                "stimulus": "F 8 B 1 9",
                "response": "1 8 9 B X",  # error
                "length": 5,
                "rt_ms": 4500.0,
            },
        ],
    }

    result = scorer.score(raw)
    assert result.task_id == "letter_number_sequencing"
    assert result.metrics["lns_span_max"] == 4.0
    assert result.metrics["accuracy"] == 0.75
    assert result.metrics["valid_trials_count"] == 4.0


def test_letter_number_timeout(scorer: LetterNumberSequencingScorer) -> None:
    raw: dict[str, object] = {
        "session_id": "sess-lns-2",
        "user_id": "user-lns",
        "trials": [
            {
                "stimulus": "B 1",
                "response": "1 B",
                "rt_ms": 35000.0,  # exceeds 30000ms
            },
            {
                "stimulus": "A 2",
                "response": "2 A",
                "rt_ms": 2000.0,
            },
        ],
    }

    result = scorer.score(raw)
    assert result.trials[0].valid is False
    assert result.trials[0].invalid_reason == "timeout"
    assert result.trials[1].valid is True
    assert result.metrics["valid_trials_count"] == 1.0
