"""Unit tests for PerceptionScorer."""

from __future__ import annotations

import pytest

from coglayer.core.tasks import PERCEPTION_DESCRIPTOR
from coglayer.signals.perception import PerceptionScorer


@pytest.fixture
def scorer() -> PerceptionScorer:
    return PerceptionScorer(PERCEPTION_DESCRIPTOR)


def test_perception_scoring_necker_and_change_blindness(scorer: PerceptionScorer) -> None:
    raw: dict[str, object] = {
        "session_id": "sess-perc-1",
        "user_id": "user-perc",
        "trials": [
            {
                "stimulus": "necker_cube_switch",
                "response": "6",
                "rt_ms": 30000.0,
            },
            {
                "stimulus": "change_blindness_flicker",
                "expected": "LEFT_TREE",
                "response": "LEFT_TREE",
                "rt_ms": 8500.0,
            },
            {
                "stimulus": "my_wife_and_my_mother_in_law",
                "response": "young_woman",
                "rt_ms": 3000.0,
            },
        ],
    }

    result = scorer.score(raw)
    assert result.task_id == "perception_lab"
    assert result.metrics["switch_rate"] == 6.0
    assert result.metrics["detection_rate"] == 1.0
    assert 0.0 <= result.metrics["perceptual_stability"] <= 1.0
    assert result.metrics["valid_trials_count"] == 3.0


def test_perception_timeout(scorer: PerceptionScorer) -> None:
    raw: dict[str, object] = {
        "session_id": "sess-perc-timeout",
        "user_id": "user-perc",
        "trials": [
            {
                "stimulus": "necker_cube",
                "response": "5",
                "rt_ms": 65000.0,  # exceeds 60000ms
            },
            {
                "stimulus": "ambiguous_rubin_vase",
                "response": "vase",
                "rt_ms": 4000.0,
            },
        ],
    }

    result = scorer.score(raw)
    assert result.trials[0].valid is False
    assert result.trials[0].invalid_reason == "timeout"
    assert result.trials[1].valid is True
    assert result.metrics["valid_trials_count"] == 1.0
