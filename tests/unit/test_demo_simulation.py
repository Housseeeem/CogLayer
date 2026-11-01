"""Focused checks for deterministic demo coverage."""

from __future__ import annotations

from collections import Counter

from scripts.demo_simulation import (
    IOI_DEFINITIONS,
    NOGO_CORRECT_BY_SESSION,
    SESSION_TASKS,
)


def test_demo_has_six_comparable_sessions_per_dimension() -> None:
    assert len(SESSION_TASKS) == 6
    counts = Counter(task_id for tasks in SESSION_TASKS for task_id in tasks)
    assert counts == {
        "go_no_go": 6,
        "sequence_span": 6,
        "digit_span": 6,
        "stroop": 6,
    }


def test_demo_defines_three_ioi_opportunities_per_component() -> None:
    assert len(IOI_DEFINITIONS) == 5
    assert len({component for component, _ in IOI_DEFINITIONS}) == 5


def test_demo_contains_a_clear_brain_twin_dip() -> None:
    assert NOGO_CORRECT_BY_SESSION[5] == 1
    assert NOGO_CORRECT_BY_SESSION[5] < NOGO_CORRECT_BY_SESSION[4]
    assert NOGO_CORRECT_BY_SESSION[5] < NOGO_CORRECT_BY_SESSION[6]
