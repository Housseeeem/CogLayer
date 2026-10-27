"""Unit tests for NBackScorer."""

from __future__ import annotations

import pytest

from coglayer.core.tasks import N_BACK_DESCRIPTOR
from coglayer.signals.n_back import NBackScorer


@pytest.fixture
def scorer() -> NBackScorer:
    return NBackScorer(N_BACK_DESCRIPTOR)


def test_n_back_hits_false_alarms_and_d_prime(scorer: NBackScorer) -> None:
    raw: dict[str, object] = {
        "session_id": "sess-nback-1",
        "user_id": "user-nback",
        "trials": [
            # Target trial 1 -> Hit
            {
                "stimulus": "A",
                "is_target": True,
                "response": "MATCH",
                "rt_ms": 450.0,
            },
            # Target trial 2 -> Hit
            {
                "stimulus": "B",
                "is_target": True,
                "response": "MATCH",
                "rt_ms": 500.0,
            },
            # Target trial 3 -> Miss
            {
                "stimulus": "C",
                "is_target": True,
                "response": "NO_MATCH",
                "rt_ms": 600.0,
            },
            # Non-target trial 1 -> Correct Rejection
            {
                "stimulus": "D",
                "is_target": False,
                "response": "NO_MATCH",
                "rt_ms": 400.0,
            },
            # Non-target trial 2 -> False Alarm
            {
                "stimulus": "E",
                "is_target": False,
                "response": "MATCH",
                "rt_ms": 420.0,
            },
            # Non-target trial 3 -> Correct Rejection
            {
                "stimulus": "F",
                "is_target": False,
                "response": "NO_MATCH",
                "rt_ms": 380.0,
            },
        ],
    }

    result = scorer.score(raw)
    assert result.task_id == "n_back"
    assert result.metrics["hits"] == 2.0
    assert result.metrics["false_alarms"] == 1.0
    assert result.metrics["target_accuracy"] == pytest.approx(2 / 3, abs=1e-3)
    assert result.metrics["false_alarm_rate"] == pytest.approx(1 / 3, abs=1e-3)
    assert result.metrics["n_back_accuracy"] == pytest.approx(4 / 6, abs=1e-3)
    assert result.metrics["d_prime"] > 0.0
    assert result.metrics["valid_trials_count"] == 6.0


def test_n_back_exclusions(scorer: NBackScorer) -> None:
    raw: dict[str, object] = {
        "session_id": "sess-nback-2",
        "user_id": "user-nback",
        "trials": [
            # Anticipation (< 100 ms)
            {
                "stimulus": "A",
                "is_target": True,
                "response": "MATCH",
                "rt_ms": 50.0,
            },
            # Timeout (> 3000 ms)
            {
                "stimulus": "B",
                "is_target": False,
                "response": "NO_MATCH",
                "rt_ms": 3500.0,
            },
            # Valid
            {
                "stimulus": "C",
                "is_target": False,
                "response": "NO_MATCH",
                "rt_ms": 400.0,
            },
        ],
    }

    result = scorer.score(raw)
    assert result.trials[0].valid is False
    assert result.trials[0].invalid_reason == "anticipation"
    assert result.trials[1].valid is False
    assert result.trials[1].invalid_reason == "timeout"
    assert result.trials[2].valid is True
    assert result.metrics["valid_trials_count"] == 1.0
