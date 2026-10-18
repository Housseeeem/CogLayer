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
    TaskDescriptor,
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


# ---------------------------------------------------------------------------
# Step 1: Generalized decision engine tests
# ---------------------------------------------------------------------------


def _descriptor(task_id: str, dimension: str) -> TaskDescriptor:
    from coglayer.core.models import Reading, TaskDescriptor

    return TaskDescriptor(
        task_id=task_id,
        version="1.0",
        instructions=f"Instructions for {task_id}",
        target_dimensions=[dimension],
        readings=[
            Reading(metric=f"{task_id}_score", dimension=dimension, status="profile"),
        ],
        parameters={},
    )


def test_ac_least_certain_dimension_proposed() -> None:
    """AC (a): Dimension A has no evidence, dimension B has Beta(9,3) -> next task is A.
    Swap them -> next task is B.

    Hand-derived:
      Prior Beta(1,1): variance = 1/12 = 0.0833
      Posterior Beta(9,3): variance = 27/(144*13) = 0.0144
      Variance Beta(1,1) > variance Beta(9,3), so Beta(1,1) is more uncertain.

    Scipy credible intervals (TESTED):
      width Beta(1,1): beta.ppf(0.95, 1, 1) - beta.ppf(0.05, 1, 1) = 0.95 - 0.05 = 0.900000
      width Beta(9,3): beta.ppf(0.95, 9, 3) - beta.ppf(0.05, 9, 3) = 0.921180 - 0.529913 = 0.391267
      0.900000 > 0.391267 -> Dimension A without evidence is less certain than Dimension B.
    """
    import scipy.stats

    from coglayer.profile.model import BetaProfileModel
    from coglayer.signals.registry import InMemoryTaskRegistry

    # TESTED: verify scipy interval widths match hand-derived relationship
    w_prior = float(scipy.stats.beta.ppf(0.95, 1, 1) - scipy.stats.beta.ppf(0.05, 1, 1))
    w_b93 = float(scipy.stats.beta.ppf(0.95, 9, 3) - scipy.stats.beta.ppf(0.05, 9, 3))
    assert w_prior == pytest.approx(0.90, abs=1e-4)
    assert w_b93 == pytest.approx(0.391267, abs=1e-4)
    assert w_prior > w_b93

    registry = InMemoryTaskRegistry()
    registry.register(_descriptor("task_a", "dim_a"))
    registry.register(_descriptor("task_b", "dim_b"))

    settings = _settings()

    # Case 1: dim_a has no evidence, dim_b has Beta(9,3)
    model1 = BetaProfileModel()
    model1.seed_dimension("dim_b", alpha=9.0, beta=3.0, n_evidence=1, last_update=_TS)
    engine1 = AdaptiveDecisionEngine(registry=registry, interval_fn=model1.credible_interval)
    decision1 = engine1.decide(results=[], settings=settings)
    assert decision1.status == "next_task"
    assert decision1.next_task == "task_a"

    # Case 2: swap them -> dim_a has Beta(9,3), dim_b has no evidence
    model2 = BetaProfileModel()
    model2.seed_dimension("dim_a", alpha=9.0, beta=3.0, n_evidence=1, last_update=_TS)
    engine2 = AdaptiveDecisionEngine(registry=registry, interval_fn=model2.credible_interval)
    decision2 = engine2.decide(results=[], settings=settings)
    assert decision2.status == "next_task"
    assert decision2.next_task == "task_b"


def test_ac_tie_breaking_registry_order_deterministic() -> None:
    """AC (b): Tie (both without evidence) -> registry order, identical on two calls."""
    from coglayer.signals.registry import InMemoryTaskRegistry

    registry = InMemoryTaskRegistry()
    registry.register(_descriptor("task_alpha", "dim_alpha"))
    registry.register(_descriptor("task_beta", "dim_beta"))

    settings = _settings()
    engine = AdaptiveDecisionEngine(registry=registry)

    # Both dimensions at Beta(1,1) -> tied uncertainty
    decision1 = engine.decide(results=[], settings=settings)
    decision2 = engine.decide(results=[], settings=settings)

    assert decision1.status == "next_task"
    assert decision1.next_task == "task_alpha"
    assert decision2.status == "next_task"
    assert decision2.next_task == "task_alpha"


def test_ac_completed_tasks_not_proposed_and_completion() -> None:
    """AC (c): Tasks already completed in current session are not proposed again;
    when every registered task is completed, protocol is complete."""
    from coglayer.signals.registry import InMemoryTaskRegistry

    registry = InMemoryTaskRegistry()
    registry.register(_descriptor("task_a", "dim_a"))
    registry.register(_descriptor("task_b", "dim_b"))

    settings = _settings()
    engine = AdaptiveDecisionEngine(registry=registry)

    # First task proposed
    d1 = engine.decide(results=[], settings=settings)
    assert d1.status == "next_task"
    assert d1.next_task == "task_a"

    # task_a completed in this session -> propose task_b
    d2 = engine.decide(
        results=[_result("task_a", completeness=1.0)],
        settings=settings,
    )
    assert d2.status == "next_task"
    assert d2.next_task == "task_b"

    # Both completed -> protocol complete
    d3 = engine.decide(
        results=[
            _result("task_a", completeness=1.0),
            _result("task_b", completeness=1.0),
        ],
        settings=settings,
    )
    assert d3.status == "complete"
    assert d3.next_task is None


def test_ac_fictitious_third_task_extensibility() -> None:
    """AC (d): A fictitious 3rd task registered in a test registry:
    protocol now requires it; user with data in first two dims and none in third
    is proposed 3rd task first; protocol is complete only after all 3 are done."""
    from coglayer.profile.model import BetaProfileModel
    from coglayer.signals.registry import InMemoryTaskRegistry

    registry = InMemoryTaskRegistry()
    registry.register(_descriptor("task_1", "dim_1"))
    registry.register(_descriptor("task_2", "dim_2"))
    registry.register(_descriptor("task_3", "dim_3"))

    settings = _settings()

    # User with data in dim_1 and dim_2, none in dim_3
    model = BetaProfileModel()
    model.seed_dimension("dim_1", alpha=8.0, beta=4.0, n_evidence=2, last_update=_TS)
    model.seed_dimension("dim_2", alpha=9.0, beta=3.0, n_evidence=2, last_update=_TS)

    engine = AdaptiveDecisionEngine(registry=registry, interval_fn=model.credible_interval)

    # Proposed first: task_3 (least certain estimate)
    d1 = engine.decide(results=[], settings=settings)
    assert d1.status == "next_task"
    assert d1.next_task == "task_3"

    # After task_3 is done, protocol still requires task_1 and task_2
    d2 = engine.decide(
        results=[_result("task_3", completeness=1.0)],
        settings=settings,
    )
    assert d2.status == "next_task"
    assert d2.next_task in ("task_1", "task_2")

    other_task = "task_2" if d2.next_task == "task_1" else "task_1"
    d3 = engine.decide(
        results=[
            _result("task_3", completeness=1.0),
            _result(d2.next_task, completeness=1.0),
        ],
        settings=settings,
    )
    assert d3.status == "next_task"
    assert d3.next_task == other_task

    # Only complete when all 3 are done
    d4 = engine.decide(
        results=[
            _result("task_1", completeness=1.0),
            _result("task_2", completeness=1.0),
            _result("task_3", completeness=1.0),
        ],
        settings=settings,
    )
    assert d4.status == "complete"
    assert d4.next_task is None


def test_ac_decision_reason_non_clinical() -> None:
    """AC (e): Decision carries a short human-readable reason naming the dimension
    and why ("least certain estimate"), containing no clinical words."""
    import re

    from coglayer.signals.registry import InMemoryTaskRegistry

    registry = InMemoryTaskRegistry()
    registry.register(_descriptor("task_inhibit", "response_inhibition"))

    settings = _settings()
    engine = AdaptiveDecisionEngine(registry=registry)

    decision = engine.decide(results=[], settings=settings)
    assert decision.status == "next_task"
    assert decision.next_task == "task_inhibit"
    assert decision.reason is not None
    assert "response_inhibition" in decision.reason
    assert "least certain" in decision.reason.lower()

    # Clinical words blacklist (whole words, case-insensitive)
    forbidden = ["diagnosis", "disorder", "deficit", "impairment", "iq", "patient"]
    for word in forbidden:
        pattern = rf"\b{re.escape(word)}\b"
        assert not re.search(pattern, decision.reason, re.IGNORECASE), (
            f"Forbidden word '{word}' found in reason: {decision.reason!r}"
        )


def test_decision_with_cognitive_profile_instance() -> None:
    """Decision engine reads dimension estimate bounds directly from CognitiveProfile."""
    from coglayer.core.models import CognitiveProfile, DimensionEstimate
    from coglayer.signals.registry import InMemoryTaskRegistry

    registry = InMemoryTaskRegistry()
    registry.register(_descriptor("task_x", "dim_x"))
    registry.register(_descriptor("task_y", "dim_y"))

    # dim_x has wide credible interval (upper - lower = 0.8), dim_y has narrow (upper - lower = 0.2)
    profile = CognitiveProfile(
        user_id="u_test",
        dimensions={
            "dim_x": DimensionEstimate(
                dimension="dim_x",
                mean=0.5,
                lower=0.1,
                upper=0.9,
                n_evidence=2,
                last_update=_TS,
            ),
            "dim_y": DimensionEstimate(
                dimension="dim_y",
                mean=0.5,
                lower=0.4,
                upper=0.6,
                n_evidence=20,
                last_update=_TS,
            ),
        },
        evidence_history=[],
        data_quality={},
        uncertainty={},
    )

    engine = AdaptiveDecisionEngine()
    decision = engine.decide(
        results=[],
        settings=_settings(),
        profile=profile,
        registry=registry,
    )
    assert decision.status == "next_task"
    assert decision.next_task == "task_x"


def test_decision_with_profile_model_instance() -> None:
    """Decision engine accepts an object with credible_interval as profile."""
    from coglayer.profile.model import BetaProfileModel
    from coglayer.signals.registry import InMemoryTaskRegistry

    registry = InMemoryTaskRegistry()
    registry.register(_descriptor("task_a", "dim_a"))
    registry.register(_descriptor("task_b", "dim_b"))

    model = BetaProfileModel()
    model.seed_dimension("dim_a", alpha=9.0, beta=3.0, n_evidence=1, last_update=_TS)
    # dim_b has no evidence (width 0.90) > dim_a (width 0.391)

    engine = AdaptiveDecisionEngine(registry=registry)
    decision = engine.decide(
        results=[],
        settings=_settings(),
        profile=model,
    )
    assert decision.status == "next_task"
    assert decision.next_task == "task_b"


def test_decision_descriptor_without_target_dimensions() -> None:
    """Descriptor without target_dimensions falls back to task_id as dimension."""
    from coglayer.core.models import Reading, TaskDescriptor
    from coglayer.signals.registry import InMemoryTaskRegistry

    desc = TaskDescriptor(
        task_id="standalone_task",
        version="1.0",
        instructions="Do standalone task.",
        target_dimensions=[],
        readings=[
            Reading(metric="standalone_score", dimension="speed", status="observation"),
        ],
        parameters={},
    )
    registry = InMemoryTaskRegistry()
    registry.register(desc)

    engine = AdaptiveDecisionEngine(registry=registry)
    decision = engine.decide(results=[], settings=_settings())
    assert decision.status == "next_task"
    assert decision.next_task == "standalone_task"
    assert "standalone_task" in str(decision.reason)
