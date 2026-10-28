"""Built-in cognitive task descriptors (single source of truth).

Declares the static descriptors for the built-in tasks, including target dimensions
and primary metrics.
"""

from __future__ import annotations

from coglayer.core.models import Reading, TaskDescriptor

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
    count_metric="nogo_valid_count",
    readings=[
        Reading(
            metric="nogo_accuracy",
            dimension="response_inhibition",
            status="profile",
        ),
        Reading(
            metric="go_accuracy",
            dimension="engagement",
            status="quality",
        ),
        Reading(
            metric="omission_errors",
            dimension="engagement",
            status="quality",
        ),
        Reading(
            metric="mean_rt_ms",
            dimension="speed",
            status="observation",
            caveat="design hypothesis; compare only within the same person and device",
        ),
        Reading(
            metric="rt_std_ms",
            dimension="attention_regularity",
            status="observation",
            caveat="design hypothesis",
        ),
    ],
    parameters={
        "n_practice_trials": 5,
        "n_scored_trials": 20,
        "nogo_proportion": 0.25,
        "isi_ms": 800,
        "count_metric": "nogo_valid_count",
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
    count_metric="valid_sequence_count",
    readings=[
        Reading(
            metric="correct_sequences_ratio",
            dimension="sequential_visual_memory",
            status="profile",
        ),
        Reading(
            metric="completeness",
            dimension="engagement",
            status="quality",
        ),
        Reading(
            metric="mean_rt_ms",
            dimension="speed",
            status="observation",
            caveat=(
                "design hypothesis; not comparable with the Go/No-Go mean_rt_ms "
                "(different definition)"
            ),
        ),
    ],
    parameters={
        "n_demo_sequences": 1,
        "n_practice_sequences": 2,
        "starting_length": 3,
        "increment": 1,
        "max_length": 9,
        "max_rt_ms": 30000,
        "count_metric": "valid_sequence_count",
    },
)

DIGIT_SPAN_DESCRIPTOR = TaskDescriptor(
    task_id="digit_span",
    version="1.0",
    instructions=(
        "Memorize the sequence of digits shown. "
        "Reproduce them in forward order or backward order as prompted. "
        "This is a non-clinical measure of short-term verbal working memory capacity."
    ),
    target_dimensions=["working_memory"],
    count_metric="valid_trials_count",
    primary_metric="accuracy",
    readings=[
        Reading(
            metric="accuracy",
            dimension="working_memory",
            status="profile",
        ),
        Reading(
            metric="digit_span_max",
            dimension="working_memory",
            status="observation",
        ),
        Reading(
            metric="forward_span",
            dimension="working_memory",
            status="observation",
        ),
        Reading(
            metric="backward_span",
            dimension="working_memory",
            status="observation",
        ),
        Reading(
            metric="completeness",
            dimension="engagement",
            status="quality",
        ),
    ],
    parameters={
        "min_span": 3,
        "max_span": 9,
        "trials_per_span": 2,
        "count_metric": "valid_trials_count",
    },
)

STROOP_DESCRIPTOR = TaskDescriptor(
    task_id="stroop",
    version="1.0",
    instructions=(
        "Identify the ink color of each word as quickly and accurately as possible, "
        "ignoring what the word says. "
        "This is a non-clinical measure of selective attention and interference resolution."
    ),
    target_dimensions=["cognitive_flexibility"],
    count_metric="valid_trials_count",
    primary_metric="incongruent_accuracy",
    readings=[
        Reading(
            metric="incongruent_accuracy",
            dimension="cognitive_flexibility",
            status="profile",
        ),
        Reading(
            metric="stroop_effect_ms",
            dimension="cognitive_flexibility",
            status="observation",
            caveat="Difference between incongruent and congruent reaction times",
        ),
        Reading(
            metric="congruent_accuracy",
            dimension="engagement",
            status="quality",
        ),
        Reading(
            metric="overall_accuracy",
            dimension="cognitive_flexibility",
            status="observation",
        ),
        Reading(
            metric="mean_rt_ms",
            dimension="speed",
            status="observation",
        ),
        Reading(
            metric="completeness",
            dimension="engagement",
            status="quality",
        ),
    ],
    parameters={
        "n_trials": 20,
        "count_metric": "valid_trials_count",
    },
)

CORSI_BLOCKS_DESCRIPTOR = TaskDescriptor(
    task_id="corsi_blocks",
    version="1.0",
    instructions=(
        "Watch the spatial blocks light up in sequence. "
        "Reproduce the sequence by tapping the blocks in forward or reverse order. "
        "This is a non-clinical measure of visuospatial working memory span."
    ),
    target_dimensions=["sequential_visual_memory"],
    count_metric="valid_sequences_count",
    primary_metric="accuracy",
    readings=[
        Reading(
            metric="accuracy",
            dimension="sequential_visual_memory",
            status="profile",
        ),
        Reading(
            metric="corsi_span_max",
            dimension="sequential_visual_memory",
            status="observation",
        ),
        Reading(
            metric="forward_span",
            dimension="sequential_visual_memory",
            status="observation",
        ),
        Reading(
            metric="backward_span",
            dimension="sequential_visual_memory",
            status="observation",
        ),
        Reading(
            metric="completeness",
            dimension="engagement",
            status="quality",
        ),
    ],
    parameters={
        "n_blocks": 9,
        "min_span": 3,
        "max_span": 8,
        "count_metric": "valid_sequences_count",
    },
)

N_BACK_DESCRIPTOR = TaskDescriptor(
    task_id="n_back",
    version="1.0",
    instructions=(
        "Determine whether the current stimulus matches the one shown N steps earlier (2-Back). "
        "This is a non-clinical task measuring continuous working memory updating."
    ),
    target_dimensions=["working_memory"],
    count_metric="valid_trials_count",
    primary_metric="n_back_accuracy",
    readings=[
        Reading(
            metric="n_back_accuracy",
            dimension="working_memory",
            status="profile",
        ),
        Reading(
            metric="target_accuracy",
            dimension="working_memory",
            status="observation",
        ),
        Reading(
            metric="false_alarm_rate",
            dimension="response_inhibition",
            status="observation",
        ),
        Reading(
            metric="d_prime",
            dimension="working_memory",
            status="observation",
            caveat="Parametric sensitivity index d-prime from signal detection theory",
        ),
        Reading(
            metric="mean_rt_ms",
            dimension="speed",
            status="observation",
        ),
        Reading(
            metric="completeness",
            dimension="engagement",
            status="quality",
        ),
    ],
    parameters={
        "n": 2,
        "n_trials": 20,
        "count_metric": "valid_trials_count",
    },
)

LETTER_NUMBER_DESCRIPTOR = TaskDescriptor(
    task_id="letter_number_sequencing",
    version="1.0",
    instructions=(
        "View an unordered combination of numbers and letters. "
        "Reorganize them by reciting numbers first in ascending "
        "order, then letters alphabetically. "
        "This is a non-clinical measure of active mental manipulation in working memory."
    ),
    target_dimensions=["working_memory"],
    count_metric="valid_trials_count",
    primary_metric="accuracy",
    readings=[
        Reading(
            metric="accuracy",
            dimension="working_memory",
            status="profile",
        ),
        Reading(
            metric="lns_span_max",
            dimension="working_memory",
            status="observation",
        ),
        Reading(
            metric="completeness",
            dimension="engagement",
            status="quality",
        ),
    ],
    parameters={
        "min_length": 2,
        "max_length": 7,
        "count_metric": "valid_trials_count",
    },
)

PERCEPTION_DESCRIPTOR = TaskDescriptor(
    task_id="perception_lab",
    version="1.0",
    instructions=(
        "Explore perceptual bistability and visual change detection tasks "
        "(Necker cube, Rubin vase, ambiguous figures, change blindness). "
        "This is a non-clinical task exploring perceptual switching and visual attention."
    ),
    target_dimensions=["cognitive_flexibility"],
    count_metric="valid_trials_count",
    primary_metric="perceptual_stability",
    readings=[
        Reading(
            metric="perceptual_stability",
            dimension="cognitive_flexibility",
            status="profile",
        ),
        Reading(
            metric="switch_rate",
            dimension="cognitive_flexibility",
            status="observation",
        ),
        Reading(
            metric="detection_rate",
            dimension="cognitive_flexibility",
            status="observation",
        ),
        Reading(
            metric="completeness",
            dimension="engagement",
            status="quality",
        ),
    ],
    parameters={
        "subtasks": ["necker_cube", "ambiguous_figures", "change_blindness"],
        "count_metric": "valid_trials_count",
    },
)

DEFAULT_TASK_DESCRIPTORS: tuple[TaskDescriptor, ...] = (
    GO_NO_GO_DESCRIPTOR,
    SEQUENCE_SPAN_DESCRIPTOR,
)

COGNITIVE_LAB_DESCRIPTORS: tuple[TaskDescriptor, ...] = (
    DIGIT_SPAN_DESCRIPTOR,
    STROOP_DESCRIPTOR,
    CORSI_BLOCKS_DESCRIPTOR,
    N_BACK_DESCRIPTOR,
    LETTER_NUMBER_DESCRIPTOR,
    PERCEPTION_DESCRIPTOR,
)

ALL_TASK_DESCRIPTORS: tuple[TaskDescriptor, ...] = (
    DEFAULT_TASK_DESCRIPTORS + COGNITIVE_LAB_DESCRIPTORS
)
