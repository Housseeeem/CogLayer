"""Tests for the GoNoGoScorer.

Tasks 5.3, 5.4, 5.5 + regression tests — property tests and exact-value unit tests.
Requirements: R-003.3, R-003.4, R-003.5, REQ-011
"""

from __future__ import annotations

import copy
import random
from statistics import stdev

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import composite

from coglayer.signals.go_no_go import GoNoGoScorer

TIMESTAMP = "2024-01-15T10:00:00+00:00"


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------


@composite
def trial_strategy(draw: st.DrawFn) -> dict[str, object]:
    """Generate a single trial dict for hypothesis tests."""
    stimulus: str = draw(st.sampled_from(["go", "nogo"]))
    expected: str = "press" if stimulus == "go" else "inhibit"
    response: str | None = draw(st.one_of(st.none(), st.just("press")))
    rt_ms: float = draw(
        st.floats(
            min_value=0.0,
            max_value=2000.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    return {
        "stimulus": stimulus,
        "expected": expected,
        "response": response,
        "rt_ms": rt_ms,
        "timestamp": TIMESTAMP,
        "valid": True,
        "invalid_reason": None,
    }


def _make_raw(trials: list[dict[str, object]]) -> dict[str, object]:
    return {"session_id": "s1", "user_id": "u1", "trials": trials}


# ---------------------------------------------------------------------------
# Task 5.3 — Property 5: GNG completeness in [0,1]
# Feature: vertical-slice, Property 5: GNG completeness in [0,1]
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(trials=st.lists(trial_strategy(), max_size=30))
def test_gng_completeness_in_range(trials: list[dict[str, object]]) -> None:
    """Property 5: completeness is always in [0, 1] and equals valid/total."""
    result = GoNoGoScorer().score(_make_raw(trials))
    dq = result.data_quality
    assert 0.0 <= dq.completeness <= 1.0
    if dq.total_trials > 0:
        assert dq.completeness == pytest.approx(dq.valid_trials / dq.total_trials)
    else:
        assert dq.completeness == 0.0


# ---------------------------------------------------------------------------
# Task 5.4 — Property 7: anticipation exclusion order-independence
# Feature: vertical-slice, Property 7: anticipation order-independence
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(trials=st.lists(trial_strategy(), min_size=1, max_size=20))
def test_anticipation_exclusion_order_independence(
    trials: list[dict[str, object]],
) -> None:
    """Property 7: exclusion pattern is identical regardless of trial order."""
    result_original = GoNoGoScorer().score(_make_raw(trials))

    shuffled = copy.copy(trials)
    rng = random.Random(42)  # noqa: S311 — seeded RNG for deterministic test shuffle only
    rng.shuffle(shuffled)
    result_shuffled = GoNoGoScorer().score(_make_raw(shuffled))

    # Same multiset of (stimulus, invalid_reason) tuples in both results.
    # Sort key maps None -> "" so tuples are always comparable.
    def _key(s: str, r: str | None) -> tuple[str, str]:
        return (s, r if r is not None else "")

    original_tags = sorted(_key(t.stimulus, t.invalid_reason) for t in result_original.trials)
    shuffled_tags = sorted(_key(t.stimulus, t.invalid_reason) for t in result_shuffled.trials)
    assert original_tags == shuffled_tags


# ---------------------------------------------------------------------------
# Regression property test: validity never depends on rt_ms when response=None
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    stimulus=st.sampled_from(["go", "nogo"]),
    rt_ms=st.floats(min_value=0.0, max_value=2000.0, allow_nan=False, allow_infinity=False),
)
def test_response_none_validity_independent_of_rt(stimulus: str, rt_ms: float) -> None:
    """Regression: when response=None, validity never depends on rt_ms."""
    raw: dict[str, object] = {
        "session_id": "s1",
        "user_id": "u1",
        "trials": [
            {
                "stimulus": stimulus,
                "expected": "press" if stimulus == "go" else "inhibit",
                "response": None,
                "rt_ms": rt_ms,
                "timestamp": TIMESTAMP,
                "valid": True,
                "invalid_reason": None,
            }
        ],
    }
    result = GoNoGoScorer().score(raw)
    assert result.trials[0].valid is True
    assert result.trials[0].invalid_reason is None


# ---------------------------------------------------------------------------
# Example test: Go omission with rt_ms=0
# ---------------------------------------------------------------------------


def test_go_omission_with_rt_zero() -> None:
    """Example: Go trial with response=None and rt_ms=0 stays valid (omission error)."""
    raw: dict[str, object] = {
        "session_id": "s1",
        "user_id": "u1",
        "trials": [
            {
                "stimulus": "go",
                "expected": "press",
                "response": None,
                "rt_ms": 0.0,
                "timestamp": TIMESTAMP,
                "valid": True,
                "invalid_reason": None,
            }
        ],
    }
    result = GoNoGoScorer().score(raw)
    assert result.trials[0].valid is True
    assert result.trials[0].invalid_reason is None
    assert result.metrics["omission_errors"] == pytest.approx(1.0)
    assert result.metrics["valid_trial_count"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Protocol conformance tests
# ---------------------------------------------------------------------------


def test_gng_scorer_satisfies_protocol() -> None:
    """GoNoGoScorer satisfies the ScoringAdapter protocol structurally."""
    from coglayer.core.protocols import ScoringAdapter

    scorer = GoNoGoScorer()
    assert isinstance(scorer, ScoringAdapter)


def test_gng_runner_satisfies_protocol() -> None:
    """GoNoGoRunner satisfies the TaskRunner protocol structurally."""
    from coglayer.core.protocols import TaskRunner
    from coglayer.signals.go_no_go import GoNoGoRunner

    runner = GoNoGoRunner()
    assert isinstance(runner, TaskRunner)


def test_gng_runner_raises_not_implemented() -> None:
    """GoNoGoRunner.run() raises NotImplementedError (UI-driven task)."""
    from coglayer.signals.go_no_go import GoNoGoRunner

    runner = GoNoGoRunner()
    with pytest.raises(NotImplementedError, match="UI-driven"):
        runner.run("session_1", "user_1", {})


# ---------------------------------------------------------------------------
# Task 5.5 — Exact-value test: test_ac_gng_metrics_exact
# REQ-011: test_ac_gng_metrics_exact
# ---------------------------------------------------------------------------


def test_ac_gng_metrics_exact() -> None:
    """REQ-011: exact metric values for a hand-crafted 10-trial set.

    Trial breakdown (derived by hand from R-003.3/R-003.4 rules):

    #  stimulus  response  rt_ms  -> outcome
    1  nogo      None      0.0    -> VALID, correct (inhibited; response=None, no exclusion)
    2  nogo      press     320.0  -> VALID, commission error
    3  nogo      press     350.0  -> VALID, commission error
    4  go        None      500.0  -> VALID, omission error (no response => no exclusion)
    5  go        press     80.0   -> INVALID anticipation (response!=None, rt<100)
    6  go        press     120.0  -> INVALID implausibly_fast (response!=None, 100<=rt<150)
    7  go        press     200.0  -> VALID, correct Go
    8  go        press     250.0  -> VALID, correct Go
    9  go        press     300.0  -> VALID, correct Go
    10 go        press     350.0  -> VALID, correct Go

    Hand-computed metrics:
      total_trials         = 10
      valid_trials         = 8  (trials 1-4, 7-10)
      completeness         = 8/10 = 0.8
      commission_errors    = 2  (trials 2, 3)
      omission_errors      = 1  (trial 4)
      correct valid trials = trial 1 + trials 7-10 = 5
      accuracy             = 5/8 = 0.625
      correct Go rts       = [200, 250, 300, 350]
      mean_rt_ms           = 1100/4 = 275.0
      rt_std_ms            = stdev([200, 250, 300, 350]) = 64.549...
    """
    raw_trials = [
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": None,
            "rt_ms": 0.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": "press",
            "rt_ms": 320.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": "press",
            "rt_ms": 350.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "stimulus": "go",
            "expected": "press",
            "response": None,
            "rt_ms": 500.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 80.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 120.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 200.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 250.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 300.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "stimulus": "go",
            "expected": "press",
            "response": "press",
            "rt_ms": 350.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
    ]

    result = GoNoGoScorer().score(
        {"session_id": "test_session", "user_id": "test_user", "trials": raw_trials}
    )

    assert result.data_quality.total_trials == 10
    assert result.data_quality.valid_trials == 8
    assert result.data_quality.completeness == pytest.approx(0.8)

    t = result.trials
    assert t[0].valid is True
    assert t[0].invalid_reason is None
    assert t[4].valid is False
    assert t[4].invalid_reason == "anticipation"
    assert t[5].valid is False
    assert t[5].invalid_reason == "implausibly_fast"

    m = result.metrics
    assert m["commission_errors"] == pytest.approx(2.0)
    assert m["omission_errors"] == pytest.approx(1.0)
    assert m["accuracy"] == pytest.approx(5 / 8)
    # No-Go accuracy: 1 correct out of 3 valid No-Go trials (trial 1 correct, 2 and 3 errors)
    assert m["nogo_accuracy"] == pytest.approx(1 / 3)
    # Go accuracy: 4 correct out of 5 valid Go trials (trials 7-10 correct, trial 4 omission)
    assert m["go_accuracy"] == pytest.approx(4 / 5)
    # Count metrics
    assert m["nogo_valid_count"] == pytest.approx(3.0)  # trials 1, 2, 3
    assert m["go_valid_count"] == pytest.approx(5.0)  # trials 4, 7, 8, 9, 10
    assert m["mean_rt_ms"] == pytest.approx(275.0)
    assert m["rt_std_ms"] == pytest.approx(stdev([200.0, 250.0, 300.0, 350.0]), rel=1e-4)
    assert m["valid_trial_count"] == pytest.approx(8.0)

    assert result.task_id == "go_no_go"
    assert result.target_dimensions == ["response_inhibition"]


def test_nogo_fast_response_counts_as_commission_error_not_exclusion() -> None:
    """A response on a No-Go trial faster than 100 ms counts as commission error, not exclusion.

    Hand-derived arithmetic:
      5 No-Go trials:
        - 4 trials: response=None, rt_ms=0.0 (correctly inhibited).
        - 1 trial: response="press", rt_ms=80.0 (< 100 ms anticipation threshold).
      Expected values:
        - The fast No-Go response trial must have valid=True, invalid_reason=None.
        - Commission errors = 1.0 (the 80 ms press).
        - Valid No-Go trials = 5.0.
        - Correctly inhibited No-Go trials = 4.0.
        - nogo_accuracy = 4 / 5 = 0.8.
        (Previously, it was excluded as anticipation: valid=False, giving 4/4 = 1.0).
    """
    raw_trials: list[dict[str, object]] = [
        # 4 correctly inhibited No-Go trials
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": None,
            "rt_ms": 0.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": None,
            "rt_ms": 0.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": None,
            "rt_ms": 0.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": None,
            "rt_ms": 0.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        # 1 fast press on No-Go (80 ms < 100 ms)
        {
            "stimulus": "nogo",
            "expected": "inhibit",
            "response": "press",
            "rt_ms": 80.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
    ]

    result = GoNoGoScorer().score(
        {"session_id": "test_session", "user_id": "test_user", "trials": raw_trials}
    )

    fast_trial = result.trials[4]
    assert fast_trial.valid is True
    assert fast_trial.invalid_reason is None

    assert result.metrics["commission_errors"] == pytest.approx(1.0)
    assert result.metrics["nogo_valid_count"] == pytest.approx(5.0)
    assert result.metrics["nogo_accuracy"] == pytest.approx(4 / 5)  # 0.8
