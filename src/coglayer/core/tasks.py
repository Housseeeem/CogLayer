"""Built-in cognitive task descriptors (single source of truth).

Declares the static descriptors for the built-in tasks, including target dimensions
and primary metrics.
"""

from __future__ import annotations

from coglayer.core.models import TaskDescriptor

GO_NO_GO_DESCRIPTOR = TaskDescriptor(
    task_id="go_no_go",
    version="1.0",
    instructions=(
        "A series of stimuli will appear on screen. "
        "Press the spacebar as quickly as possible when you see the Go stimulus (green circle), "
        "but do NOT press anything when you see the No-Go stimulus (red circle). "
        "Try to respond accurately and quickly. "
        "This is a non-clinical measure of response speed and inhibition."
    ),
    target_dimensions=["response_inhibition"],
    primary_metric="nogo_accuracy",
    count_metric="nogo_valid_count",
    parameters={
        "n_practice_trials": 5,
        "n_scored_trials": 20,
        "nogo_proportion": 0.25,
        "isi_ms": 800,
        "count_metric": "nogo_valid_count",
        "weight": 1.0,
    },
)

SEQUENCE_SPAN_DESCRIPTOR = TaskDescriptor(
    task_id="sequence_span",
    version="1.0",
    instructions=(
        "A sequence of squares will light up one at a time. "
        "Watch the full sequence, then reproduce it by clicking the squares in the same order. "
        "The sequences will get longer as you go. "
        "This task measures sequential visual memory via spatial sequence reproduction. "
        "It is used as a proxy for working-memory capacity"
        " but does not purely measure working memory. "
        "This is a non-clinical measure."
    ),
    target_dimensions=["sequential_visual_memory"],
    primary_metric="correct_sequences_ratio",
    count_metric="valid_sequence_count",
    parameters={
        "n_demo_sequences": 1,
        "n_practice_sequences": 2,
        "starting_length": 3,
        "increment": 1,
        "max_length": 9,
        "max_rt_ms": 30000,
        "count_metric": "valid_sequence_count",
        "weight": 1.0,
    },
)

DEFAULT_TASK_DESCRIPTORS: tuple[TaskDescriptor, ...] = (
    GO_NO_GO_DESCRIPTOR,
    SEQUENCE_SPAN_DESCRIPTOR,
)
