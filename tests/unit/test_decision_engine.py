"""Tests for AdaptiveDecisionEngine (new rules, results-only API).

Acceptance criteria covered:
  test_ac_engine_task_order            — go_no_go first, then sequence_span
  test_ac_engine_completion            — complete when both done and sufficient
  test_ac_interrupted_session_resume   — INTERRUPTED + go_no_go done -> sequence_span
  test_ac_interrupted_both_low_quality — INTERRUPTED + both done + 0.7 -> insufficient_data
  test_ac_interrupted_both_high_quality — INTERRUPTED + both done + 0.9 -> complete
  test_ac_completeness_exact_boundary  — completeness == 0.8 passes
  test_ac_missing_responses            — low completeness yields insufficient_data
  test_ac_incomplete_session           — no results -> next_task go_no_go
  test_ac_third_task_outside_protocol  — unknown task silently ignored

All expected values are hand-derived from the decision rules in decision.py.
Requirements: R-007.1, R-007.2, R-007.3
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coglayer.coach.decision import PROTOCOL_ORDER, AdaptiveDecisionEngine
from coglayer.core.models import (
    DataQuality,
    TaskResult,
)
from coglayer.core.settings import Settings

# ---------------------------------------------------------------------------
# Helpers — hand-crafted minimal objects
# ---------------------------------------------------------------------------

_TS = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
_ENGINE = AdaptiveDecisionEngine()


def _settings(threshold: float = 0.8) -> Settings:
    """Return a Settings object with a specific completeness threshold."""
    return Settings(completeness_threshold=threshold)


def _result(task_id: str, completeness: float = 1.0) -> TaskResult:
    """Build a minimal TaskResult with the given task_id and completeness.

    Hand-derived: total_trials=10, valid_trials computed from completeness.
    """
    valid = round(10 * completeness)  # e.g. 0.8 -> 8 valid out of 10
    dq = DataQuality(
        valid_trials=valid,
        total_trials=10,
        completeness=float(valid) / 10.0,
        anomalies=[],
    )
    return TaskResult(
        task_id=task_id,
        task_version="1.0",
        session_id="sess-test",
        user_id="user-test",
        trials=[],
        metrics={},
        signals=[],
        target_dimensions=[],
        data_quality=dq,
        uncertainty=None,
    )


# ---------------------------------------------------------------------------
# test_ac_engine_task_order
# Hand-derived: empty results -> go_no_go first; after go_no_go -> sequence_span
# ---------------------------------------------------------------------------


def test_ac_engine_task_order() -> None:
    """AC: tasks run in PROTOCOL_ORDER: go_no_go then sequence_span.

    Hand-derived:
      No results -> Rule 1 checks go_no_go (absent) -> next_task = "go_no_go"
      go_no_go done -> Rule 1 checks go_no_go (present), sequence_span (absent)
                    -> next_task = "sequence_span"
    """
    settings = _settings()

    # No tasks done yet
    decision = _ENGINE.decide(results=[], settings=settings)
    assert decision.status == "next_task"
    assert decision.next_task == "go_no_go"

    # go_no_go done with full completeness
    decision2 = _ENGINE.decide(
        results=[_result("go_no_go", completeness=1.0)],
        settings=settings,
    )
    assert decision2.status == "next_task"
    assert decision2.next_task == "sequence_span"


# ---------------------------------------------------------------------------
# test_ac_engine_completion
# Hand-derived: both tasks done, both completeness=1.0 -> complete
# ---------------------------------------------------------------------------


def test_ac_engine_completion() -> None:
    """AC: complete when both tasks done and completeness >= threshold.

    Hand-derived:
      go_no_go completeness=1.0 (>= 0.8), sequence_span completeness=1.0
      -> Rule 2 does not fire -> Rule 3: status = "complete"
    """
    settings = _settings()
    decision = _ENGINE.decide(
        results=[
            _result("go_no_go", completeness=1.0),
            _result("sequence_span", completeness=1.0),
        ],
        settings=settings,
    )
    assert decision.status == "complete"
    assert decision.next_task is None


# ---------------------------------------------------------------------------
# test_ac_interrupted_session: INTERRUPTED + go_no_go done -> sequence_span
# Hand-derived: results have go_no_go only. INTERRUPTED treated same as
# IN_PROGRESS. Rule 1: go_no_go present, sequence_span absent -> next_task.
# ---------------------------------------------------------------------------


def test_ac_interrupted_session() -> None:
    """AC: INTERRUPTED session with go_no_go done -> resume at sequence_span.

    Hand-derived:
      results = [go_no_go(1.0)], no sequence_span result
      INTERRUPTED behaves like IN_PROGRESS (no separate rule)
      Rule 1: go_no_go present, sequence_span absent -> next_task
    """
    settings = _settings()
    decision = _ENGINE.decide(
        results=[_result("go_no_go", completeness=1.0)],
        settings=settings,
    )
    assert decision.status == "next_task"
    assert decision.next_task == "sequence_span"


# ---------------------------------------------------------------------------
# INTERRUPTED + both tasks done + completeness 0.7 -> insufficient_data
# Hand-derived: both tasks present, go_no_go completeness=0.7 < 0.8
# -> Rule 2 fires on go_no_go.
# ---------------------------------------------------------------------------


def test_ac_interrupted_both_done_low_quality() -> None:
    """INTERRUPTED + both done + completeness 0.7 -> insufficient_data.

    Hand-derived:
      go_no_go: valid=7, total=10, completeness=0.7
      sequence_span: completeness=1.0
      threshold=0.8
      Rule 2: 0.7 < 0.8 -> insufficient_data with reason naming "go_no_go"
    """
    settings = _settings(threshold=0.8)
    gng = _result("go_no_go", completeness=0.7)
    # Verify hand-derived completeness
    assert gng.data_quality.completeness == pytest.approx(0.7)

    decision = _ENGINE.decide(
        results=[gng, _result("sequence_span", completeness=1.0)],
        settings=settings,
    )
    assert decision.status == "insufficient_data"
    assert decision.next_task is None
    assert decision.reason is not None
    assert "go_no_go" in decision.reason
    assert "session" in decision.reason.lower()


# ---------------------------------------------------------------------------
# INTERRUPTED + both done + completeness 0.9 -> complete
# Hand-derived: both tasks with completeness 0.9 >= 0.8 -> Rule 3: complete
# ---------------------------------------------------------------------------


def test_ac_interrupted_both_done_high_quality() -> None:
    """INTERRUPTED + both done + completeness 0.9 -> complete.

    Hand-derived:
      go_no_go: valid=9, total=10, completeness=0.9
      sequence_span: valid=9, total=10, completeness=0.9
      Both 0.9 >= 0.8 -> Rule 2 does not fire -> Rule 3: complete
    """
    settings = _settings(threshold=0.8)
    decision = _ENGINE.decide(
        results=[
            _result("go_no_go", completeness=0.9),
            _result("sequence_span", completeness=0.9),
        ],
        settings=settings,
    )
    assert decision.status == "complete"
    assert decision.next_task is None


# ---------------------------------------------------------------------------
# Completeness exactly 0.8 passes
# Hand-derived: completeness == threshold -> >= passes -> Rule 3: complete
# ---------------------------------------------------------------------------


def test_ac_completeness_exact_boundary() -> None:
    """Completeness exactly equal to threshold passes (boundary: >= not >).

    Hand-derived:
      go_no_go: valid=8, total=10, completeness=0.8
      sequence_span: completeness=1.0
      threshold=0.8
      Rule 2: 0.8 >= 0.8 -> does NOT fire -> Rule 3: complete
    """
    settings = _settings(threshold=0.8)
    gng = TaskResult(
        task_id="go_no_go",
        task_version="1.0",
        session_id="sess-test",
        user_id="user-test",
        trials=[],
        metrics={},
        signals=[],
        target_dimensions=[],
        data_quality=DataQuality(valid_trials=8, total_trials=10, completeness=0.8, anomalies=[]),
        uncertainty=None,
    )
    span = _result("sequence_span", completeness=1.0)

    decision = _ENGINE.decide(results=[gng, span], settings=settings)
    assert decision.status == "complete", (
        f"Expected complete at boundary 0.8==threshold, got {decision.status}: {decision.reason}"
    )


# ---------------------------------------------------------------------------
# test_ac_missing_responses
# Hand-derived: both tasks submitted, go_no_go completeness=0.5 < 0.8
# -> Rule 2 fires.
# ---------------------------------------------------------------------------


def test_ac_missing_responses() -> None:
    """AC: task with completeness below threshold -> insufficient_data.

    Hand-derived:
      go_no_go: valid=5, total=10, completeness=0.5
      sequence_span: completeness=1.0
      threshold=0.8
      Rule 2: 0.5 < 0.8 -> insufficient_data
    """
    settings = _settings(threshold=0.8)
    gng = _result("go_no_go", completeness=0.5)
    assert gng.data_quality.completeness == pytest.approx(0.5)

    decision = _ENGINE.decide(
        results=[gng, _result("sequence_span", completeness=1.0)],
        settings=settings,
    )
    assert decision.status == "insufficient_data"
    assert decision.next_task is None
    assert decision.reason is not None
    assert "go_no_go" in decision.reason
    assert "session" in decision.reason.lower()


# ---------------------------------------------------------------------------
# test_ac_incomplete_session
# Hand-derived: no results -> Rule 1 fires on go_no_go (first absent task)
# ---------------------------------------------------------------------------


def test_ac_incomplete_session() -> None:
    """AC: session with no results -> next_task go_no_go.

    Hand-derived: Rule 1 fires immediately (go_no_go not in results).
    """
    settings = _settings()
    decision = _ENGINE.decide(results=[], settings=settings)
    assert decision.status == "next_task"
    assert decision.next_task == "go_no_go"


# ---------------------------------------------------------------------------
# Third task outside PROTOCOL_ORDER is ignored
# Hand-derived: "dummy_task" not in PROTOCOL_ORDER; engine only looks at
# protocol tasks. go_no_go absent from results -> next_task = "go_no_go"
# ---------------------------------------------------------------------------


def test_ac_third_task_outside_protocol_ignored() -> None:
    """A TaskResult for a task outside PROTOCOL_ORDER is silently ignored.

    Hand-derived:
      results = [dummy_task(1.0)] — not in PROTOCOL_ORDER
      Engine filters to PROTOCOL_ORDER tasks only; go_no_go absent
      -> Rule 1: next_task = "go_no_go"
    """
    assert "dummy_task" not in PROTOCOL_ORDER
    settings = _settings()
    decision = _ENGINE.decide(
        results=[_result("dummy_task", completeness=1.0)],
        settings=settings,
    )
    assert decision.status == "next_task"
    assert decision.next_task == "go_no_go"


# ---------------------------------------------------------------------------
# PROTOCOL_ORDER is a tuple (immutable)
# ---------------------------------------------------------------------------


def test_protocol_order_is_tuple() -> None:
    """PROTOCOL_ORDER must be a tuple (immutable), not a list."""
    assert isinstance(PROTOCOL_ORDER, tuple)
    assert PROTOCOL_ORDER == ("go_no_go", "sequence_span")
