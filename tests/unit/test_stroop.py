"""Unit tests for StroopScorer."""

from __future__ import annotations

import pytest

from coglayer.core.tasks import STROOP_DESCRIPTOR
from coglayer.signals.stroop import StroopScorer


@pytest.fixture
def scorer() -> StroopScorer:
    return StroopScorer(STROOP_DESCRIPTOR)


def test_stroop_congruent_and_incongruent_scoring(scorer: StroopScorer) -> None:
    raw: dict[str, object] = {
        "session_id": "sess-stroop-1",
        "user_id": "user-stroop",
        "trials": [
            # Congruent trials: ink matches word
            {
                "stimulus": "RED",
                "expected": "RED",
                "response": "RED",
                "condition": "congruent",
                "rt_ms": 400.0,
            },
            {
                "stimulus": "GREEN",
                "expected": "GREEN",
                "response": "GREEN",
                "condition": "congruent",
                "rt_ms": 420.0,
            },
            # Incongruent trials: ink differs from word
            {
                "stimulus": "RED",
                "expected": "BLUE",
                "response": "BLUE",
                "condition": "incongruent",
                "rt_ms": 650.0,
            },
            {
                "stimulus": "GREEN",
                "expected": "YELLOW",
                "response": "YELLOW",
                "condition": "incongruent",
                "rt_ms": 670.0,
            },
        ],
    }

    result = scorer.score(raw)
    assert result.task_id == "stroop"
    assert result.metrics["congruent_accuracy"] == 1.0
    assert result.metrics["incongruent_accuracy"] == 1.0
    assert result.metrics["overall_accuracy"] == 1.0
    # Mean congruent: 410, Mean incongruent: 660 -> effect: 250ms
    assert result.metrics["stroop_effect_ms"] == pytest.approx(250.0)
    assert result.metrics["valid_trials_count"] == 4.0
    assert result.data_quality.completeness == 1.0


def test_stroop_exclusions_anticipation_and_timeout(scorer: StroopScorer) -> None:
    raw: dict[str, object] = {
        "session_id": "sess-stroop-2",
        "user_id": "user-stroop",
        "trials": [
            # Anticipation (< 150 ms)
            {
                "stimulus": "RED",
                "expected": "RED",
                "response": "RED",
                "condition": "congruent",
                "rt_ms": 110.0,
            },
            # Timeout (> 3000 ms)
            {
                "stimulus": "BLUE",
                "expected": "RED",
                "response": "RED",
                "condition": "incongruent",
                "rt_ms": 3200.0,
            },
            # Valid congruent
            {
                "stimulus": "GREEN",
                "expected": "GREEN",
                "response": "GREEN",
                "condition": "congruent",
                "rt_ms": 500.0,
            },
            # Valid incongruent wrong response
            {
                "stimulus": "YELLOW",
                "expected": "BLUE",
                "response": "YELLOW",  # error
                "condition": "incongruent",
                "rt_ms": 700.0,
            },
        ],
    }

    result = scorer.score(raw)
    assert result.trials[0].valid is False
    assert result.trials[0].invalid_reason == "anticipation"
    assert result.trials[1].valid is False
    assert result.trials[1].invalid_reason == "timeout"
    assert result.trials[2].valid is True
    assert result.trials[3].valid is True
    assert result.metrics["valid_trials_count"] == 2.0
    assert result.metrics["congruent_accuracy"] == 1.0
    assert result.metrics["incongruent_accuracy"] == 0.0
