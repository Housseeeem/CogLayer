"""Tests for the SequenceSpanScorer.

Tasks 5.7, 5.8 -- property test and exact-value unit tests.
Requirements: R-004.3, R-004.4, R-004.5, REQ-011
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import composite

from coglayer.signals.sequence_span import SEQUENCE_TIMEOUT_MS, SequenceSpanScorer

TIMESTAMP = "2024-01-15T10:00:00+00:00"


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------


@composite
def sequence_strategy(draw: st.DrawFn) -> dict[str, object]:
    """Generate a single sequence dict for hypothesis tests."""
    length: int = draw(st.integers(min_value=2, max_value=9))
    items = [str(i) for i in range(1, length + 1)]
    stimulus: str = ",".join(items)
    expected: str = stimulus
    response: str | None = draw(st.one_of(st.none(), st.just(stimulus)))
    rt_ms: float = draw(
        st.floats(
            min_value=0.0,
            max_value=60000.0,  # some will exceed the 30000 timeout
            allow_nan=False,
            allow_infinity=False,
        )
    )
    return {
        "length": length,
        "stimulus": stimulus,
        "expected": expected,
        "response": response,
        "rt_ms": rt_ms,
        "timestamp": TIMESTAMP,
        "valid": True,
        "invalid_reason": None,
    }


def _make_raw(sequences: list[dict[str, object]]) -> dict[str, object]:
    return {"session_id": "s1", "user_id": "u1", "sequences": sequences}


# ---------------------------------------------------------------------------
# Task 5.7 -- Property 6: Sequence Span completeness in [0,1]
# Feature: vertical-slice, Property 6: span completeness in [0,1]
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(sequences=st.lists(sequence_strategy(), max_size=20))
def test_span_completeness_in_range(sequences: list[dict[str, object]]) -> None:
    """Property 6: completeness is always in [0, 1] and equals valid/total."""
    result = SequenceSpanScorer().score(_make_raw(sequences))
    dq = result.data_quality
    assert 0.0 <= dq.completeness <= 1.0
    if dq.total_trials > 0:
        assert dq.completeness == pytest.approx(dq.valid_trials / dq.total_trials)
    else:
        assert dq.completeness == 0.0


# ---------------------------------------------------------------------------
# Protocol conformance tests
# ---------------------------------------------------------------------------


def test_span_scorer_satisfies_protocol() -> None:
    """SequenceSpanScorer satisfies the ScoringAdapter protocol structurally."""
    from coglayer.core.protocols import ScoringAdapter

    scorer = SequenceSpanScorer()
    assert isinstance(scorer, ScoringAdapter)


def test_span_runner_satisfies_protocol() -> None:
    """SequenceSpanRunner satisfies the TaskRunner protocol structurally."""
    from coglayer.core.protocols import TaskRunner
    from coglayer.signals.sequence_span import SequenceSpanRunner

    runner = SequenceSpanRunner()
    assert isinstance(runner, TaskRunner)


def test_span_runner_raises_not_implemented() -> None:
    """SequenceSpanRunner.run() raises NotImplementedError (UI-driven task)."""
    from coglayer.signals.sequence_span import SequenceSpanRunner

    runner = SequenceSpanRunner()
    with pytest.raises(NotImplementedError, match="UI-driven"):
        runner.run("session_1", "user_1", {})


# ---------------------------------------------------------------------------
# Task 5.8 -- Exact-value test: test_ac_span_metrics_exact
# REQ-011: test_ac_span_metrics_exact
# ---------------------------------------------------------------------------


def test_ac_span_metrics_exact() -> None:
    """REQ-011: exact metric values for a hand-crafted 6-sequence set.

    Sequence breakdown (derived by hand from R-004.3/R-004.4 rules):

    #  length  response       rt_ms   -> outcome
    1  3       "1,2,3"        5000    -> VALID, correct
    2  4       "1,2,3,4"      8000    -> VALID, correct
    3  5       "1,2,3,4,5"    12000   -> VALID, correct (longest correct span)
    4  3       "2,1,3"        6000    -> VALID, order_error (same items, wrong order)
    5  4       "1,2,4,3"      9000    -> VALID, order_error
    6  5       None           35000   -> INVALID timeout (rt > 30000)

    Hand-computed metrics:
      total_trials            = 6
      valid_trials            = 5  (seqs 1-5; seq 6 is timeout)
      completeness            = 5/6

      correct_sequences       = 3  (seqs 1, 2, 3: response == expected)
      order_errors            = 2  (seqs 4, 5: same items, different order)
      max_span                = 5  (seq 3 is correct with length=5)
      valid_sequence_count    = 5
      mean_rt_ms              = (5000+8000+12000+6000+9000)/5 = 40000/5 = 8000.0
      correct_sequences_ratio = 3/5 = 0.6
    """
    raw_sequences = [
        # 1: correct, length=3
        {
            "length": 3,
            "stimulus": "1,2,3",
            "expected": "1,2,3",
            "response": "1,2,3",
            "rt_ms": 5000.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        # 2: correct, length=4
        {
            "length": 4,
            "stimulus": "1,2,3,4",
            "expected": "1,2,3,4",
            "response": "1,2,3,4",
            "rt_ms": 8000.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        # 3: correct, length=5 (longest correct)
        {
            "length": 5,
            "stimulus": "1,2,3,4,5",
            "expected": "1,2,3,4,5",
            "response": "1,2,3,4,5",
            "rt_ms": 12000.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        # 4: order error, length=3
        {
            "length": 3,
            "stimulus": "1,2,3",
            "expected": "1,2,3",
            "response": "2,1,3",
            "rt_ms": 6000.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        # 5: order error, length=4
        {
            "length": 4,
            "stimulus": "1,2,3,4",
            "expected": "1,2,3,4",
            "response": "1,2,4,3",
            "rt_ms": 9000.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
        # 6: timeout (rt > 30000) -> INVALID
        {
            "length": 5,
            "stimulus": "1,2,3,4,5",
            "expected": "1,2,3,4,5",
            "response": None,
            "rt_ms": 35000.0,
            "timestamp": TIMESTAMP,
            "valid": True,
            "invalid_reason": None,
        },
    ]

    result = SequenceSpanScorer().score(
        {"session_id": "test_session", "user_id": "test_user", "sequences": raw_sequences}
    )

    # --- Data quality --------------------------------------------------------
    assert result.data_quality.total_trials == 6
    assert result.data_quality.valid_trials == 5
    assert result.data_quality.completeness == pytest.approx(5 / 6)

    # --- Individual trial validity (seq 6 must be marked invalid) -----------
    assert result.trials[5].valid is False
    assert result.trials[5].invalid_reason == "timeout"
    assert result.trials[5].rt_ms == pytest.approx(35000.0)

    # Seqs 1-5 must remain valid
    for i in range(5):
        assert result.trials[i].valid is True

    # --- Metrics -------------------------------------------------------------
    m = result.metrics
    assert m["correct_sequences"] == pytest.approx(3.0)
    assert m["order_errors"] == pytest.approx(2.0)
    assert m["max_span"] == pytest.approx(5.0)
    assert m["valid_sequence_count"] == pytest.approx(5.0)
    assert m["mean_rt_ms"] == pytest.approx(8000.0)
    assert m["correct_sequences_ratio"] == pytest.approx(0.6)

    # --- Result metadata -----------------------------------------------------
    assert result.task_id == "sequence_span"
    assert result.target_dimensions == ["sequential_visual_memory"]

    # Confirm the SEQUENCE_TIMEOUT_MS constant is exactly 30000
    assert SEQUENCE_TIMEOUT_MS == 30_000.0
