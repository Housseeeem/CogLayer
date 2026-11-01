# Cognitive Dimensions

This document describes the four cognitive dimensions that are active in CogLayer's
task battery and Bayesian profile.  All of them are non-clinical.  CogLayer does not
diagnose anything; it tracks performance on standardized tasks and builds an
uncertainty-aware profile of those performances.

The mapping from task to dimension is built at runtime by
`ProfileService` using the `InMemoryTaskRegistry` returned by
`build_default_registry()` (see `src/coglayer/signals/registry.py`).  For each
registered task, `TaskDescriptor._validate_interpretation_rules` (rule b) derives
`primary_metric` from the first `status="profile"` entry in the task's `readings`
list.  `ProfileService.update_from_result` then uses this to update the Beta
posterior for the corresponding dimension.

The table below was produced by running the live registry and ProfileService
against `build_default_registry()`:

| task_id | dimension | outcome_metric | weight | count_metric |
|---|---|---|---|---|
| `go_no_go` | `response_inhibition` | `nogo_accuracy` | 1.0 | `nogo_valid_count` |
| `sequence_span` | `sequential_visual_memory` | `correct_sequences_ratio` | 1.0 | `valid_sequence_count` |
| `corsi_blocks` | `sequential_visual_memory` | `accuracy` | 1.0 | `valid_sequences_count` |
| `digit_span` | `working_memory` | `accuracy` | 1.0 | `valid_trials_count` |
| `n_back` | `working_memory` | `n_back_accuracy` | 1.0 | `valid_trials_count` |
| `letter_number_sequencing` | `working_memory` | `accuracy` | 1.0 | `valid_trials_count` |
| `stroop` | `cognitive_flexibility` | `incongruent_accuracy` | 1.0 | `valid_trials_count` |
| `perception_lab` | `cognitive_flexibility` | `perceptual_stability` | 1.0 | `valid_trials_count` |

> **Non-biometric mode.** No camera or microphone input is used in the MVP.
> Every measurement comes from keyboard/mouse interaction only.

---

## 1. response_inhibition

### Definition

The capacity to withhold a prepotent response — to *not* act when an action
would otherwise be automatic.  In cognitive science this is measured by how
often a person correctly refrains from responding to a No-Go stimulus while
also responding quickly and accurately to Go stimuli.

### Tasks mapped

| Task | `task_id` |
|---|---|
| Go/No-Go | `go_no_go` |

The task presents 20 scored stimuli (configurable): 75 % Go (green circle,
press spacebar) and 25 % No-Go (red circle, withhold).  Five practice trials
are excluded from scoring.

### What is scored

| Metric | Field in `TaskResult.metrics` | Meaning |
|---|---|---|
| `nogo_accuracy` | `metrics["nogo_accuracy"]` | Proportion of valid No-Go trials correctly inhibited (response withheld).  Range [0, 1].  **Profile-facing outcome.** |
| `go_accuracy` | `metrics["go_accuracy"]` | Proportion of valid Go trials correctly responded to.  Used as a data-quality indicator. |
| `commission_errors` | `metrics["commission_errors"]` | Count of valid No-Go trials where a response was given. |
| `omission_errors` | `metrics["omission_errors"]` | Count of valid Go trials where no response was given. |
| `mean_rt_ms` | `metrics["mean_rt_ms"]` | Mean reaction time on correct valid Go trials (milliseconds). |
| `rt_std_ms` | `metrics["rt_std_ms"]` | Standard deviation of RT on correct valid Go trials. |

Trials are marked invalid for omission or timeout; invalid trials are excluded
from all accuracy calculations.

The **profile update** uses `nogo_accuracy` as the outcome and `nogo_valid_count`
(the count of valid No-Go trials) as the evidence weight.  If `nogo_valid_count`
is 0 the update is skipped and no Evidence record is appended.

### Uncertainty representation

A Beta(α, β) posterior is maintained per user for this dimension.
The outcome fed to the model is `nogo_accuracy` (in [0, 1]).  The count
parameter is `nogo_valid_count`.

The model reports:
- **posterior mean** = α / (α + β)
- **90 % credible interval** = [Beta.ppf(0.05, α, β), Beta.ppf(0.95, α, β)]

Interval width decreases as more valid No-Go trials accumulate.  A forgetting
factor λ = 0.98 shrinks the posterior back toward the uniform Beta(1, 1) prior
between sessions, so stale evidence loses influence over time.  A single session
contributes at most `min(nogo_valid_count, 20)` pseudo-observations
(`MAX_PSEUDO_COUNT = 20`).

### Known biases / limits

- **Practice effects.** Repeated sessions improve inhibition scores independently
  of genuine changes in the underlying capacity.
- **Device variability.** `mean_rt_ms` is influenced by keyboard hardware and
  display refresh rate; RT comparisons across devices are unreliable.
- **Context dependence.** A 25 % No-Go proportion is moderate.  Higher proportions
  make inhibition harder; results are not directly comparable to tasks with
  different proportions.
- **Non-clinical.** `nogo_accuracy` is not equivalent to any clinical inhibition
  scale.  The `readings` entries for `go_accuracy`, `mean_rt_ms`, and `rt_std_ms`
  carry `status="observation"` or `"quality"` and are not fed to the profile model.

---

## 2. sequential_visual_memory

### Definition

The capacity to encode, hold, and reproduce a spatial sequence in forward or
reverse order.  Tasks in this dimension require maintaining a visuospatial
representation of an ordered series of locations or blocks.  This is used as a
proxy for working-memory span but does not purely measure working memory
(executive manipulation is minimal in the forward condition).

### Tasks mapped

| Task | `task_id` |
|---|---|
| Visual Sequence Span | `sequence_span` |
| Corsi Blocks | `corsi_blocks` |

**Sequence Span:** squares light up one at a time; the user reproduces the
sequence in the same order.  Sequences start at length 3 and increment by 1
up to length 9.

**Corsi Blocks:** spatial blocks light up in sequence; the user reproduces the
sequence in forward or backward order.  Minimum span 3, maximum span 8 (9
blocks on screen).

Both tasks update the same `sequential_visual_memory` dimension, each through
its own `primary_metric` and count metric.

### What is scored

#### sequence_span

| Metric | Field | Meaning |
|---|---|---|
| `correct_sequences_ratio` | `metrics["correct_sequences_ratio"]` | Proportion of sequences reproduced correctly, with timeouts counted in the denominator.  Range [0, 1].  **Profile-facing outcome.** |
| `max_span` | `metrics["max_span"]` | Longest sequence length with at least one correct reproduction. |
| `correct_sequences` | `metrics["correct_sequences"]` | Raw count of correctly reproduced valid sequences. |
| `order_errors` | `metrics["order_errors"]` | Valid sequences where the response items match the expected set but in wrong order. |
| `mean_rt_ms` | `metrics["mean_rt_ms"]` | Mean RT across valid sequences (ms). |

Sequences exceeding 30 000 ms (`SEQUENCE_TIMEOUT_MS`) are marked invalid.
`correct_sequences_ratio` denominator = valid_count + timeout_count, so
timeouts penalise the ratio.  The count metric for the Beta model is
`valid_sequence_count`.

#### corsi_blocks

| Metric | Field | Meaning |
|---|---|---|
| `accuracy` | `metrics["accuracy"]` | Proportion of valid sequences correctly reproduced across both forward and backward conditions.  Range [0, 1].  **Profile-facing outcome.** |
| `corsi_span_max` | `metrics["corsi_span_max"]` | Maximum span achieved in either condition. |
| `forward_span` | `metrics["forward_span"]` | Maximum span in forward condition. |
| `backward_span` | `metrics["backward_span"]` | Maximum span in backward condition. |
| `forward_accuracy` | `metrics["forward_accuracy"]` | Proportion correct in forward condition. |
| `backward_accuracy` | `metrics["backward_accuracy"]` | Proportion correct in backward condition. |
| `mean_rt_ms` | `metrics["mean_rt_ms"]` | Mean RT across valid sequences. |

Sequences exceeding 30 000 ms are marked invalid.  The count metric for the
Beta model is `valid_sequences_count`.

### Uncertainty representation

Same Beta posterior mechanism as described for `response_inhibition`.

- For `sequence_span`: outcome = `correct_sequences_ratio`, count = `valid_sequence_count`.
- For `corsi_blocks`: outcome = `accuracy`, count = `valid_sequences_count`.

Each task submission appends a separate Evidence record.  The posterior
integrates evidence across both tasks under the assumption that they measure
a common visuospatial span construct.

### Known biases / limits

- **Forward vs. backward conflation.** `corsi_blocks accuracy` pools both
  conditions.  Backward recall recruits more executive resources; a single
  pooled score may obscure differences.
- **Span ceiling.** Maximum span is capped at 8 (Corsi) or 9 (Sequence Span).
  Users near the ceiling will show compressed variance.
- **Practice effects.** Sequence memory improves with task familiarity.
- **Non-clinical.** Corsi span and sequence span accuracy are not equivalent to
  any standardised clinical visuospatial memory scale.

---

## 3. working_memory

### Definition

The capacity to hold and actively manipulate information in mind over a short
time horizon.  Measured through verbal (digit), alphanumeric (letter-number),
and continuous-updating (N-back) paradigms.

### Tasks mapped

| Task | `task_id` |
|---|---|
| Digit Span | `digit_span` |
| N-Back (2-Back) | `n_back` |
| Letter-Number Sequencing | `letter_number_sequencing` |

All three contribute to the same `working_memory` dimension in the profile.

### What is scored

#### digit_span

| Metric | Field | Meaning |
|---|---|---|
| `accuracy` | `metrics["accuracy"]` | Proportion of valid trials with a correct response across forward and backward conditions.  Range [0, 1].  **Profile-facing outcome.** |
| `digit_span_max` | `metrics["digit_span_max"]` | Maximum span achieved in either condition. |
| `forward_span` | `metrics["forward_span"]` | Maximum span in forward recall. |
| `backward_span` | `metrics["backward_span"]` | Maximum span in backward recall. |
| `forward_accuracy` | `metrics["forward_accuracy"]` | Proportion correct in forward condition. |
| `backward_accuracy` | `metrics["backward_accuracy"]` | Proportion correct in backward condition. |
| `mean_rt_ms` | `metrics["mean_rt_ms"]` | Mean RT across valid trials. |

Trials exceeding 30 000 ms (`DIGIT_SPAN_TIMEOUT_MS`) are marked invalid.  The
count metric is `valid_trials_count`.

#### n_back

| Metric | Field | Meaning |
|---|---|---|
| `n_back_accuracy` | `metrics["n_back_accuracy"]` | Proportion of valid trials correctly classified (hits + correct rejections) / valid_count.  Range [0, 1].  **Profile-facing outcome.** |
| `target_accuracy` | `metrics["target_accuracy"]` | Proportion of valid target trials correctly identified (hit rate). |
| `false_alarm_rate` | `metrics["false_alarm_rate"]` | Proportion of valid non-target trials incorrectly flagged as targets. |
| `d_prime` | `metrics["d_prime"]` | Signal detection index d′ (Macmillan & Kaplan 1985 edge corrections, clamped to [0, 5]). |
| `mean_rt_ms` | `metrics["mean_rt_ms"]` | Mean RT across valid trials. |

Trials below 100 ms (`N_BACK_ANTICIPATION_MS`) or above 3 000 ms
(`N_BACK_TIMEOUT_MS`) are marked invalid.  Default N = 2 (configurable).
The count metric is `valid_trials_count`.  `false_alarm_rate` is listed in the
task descriptor's `readings` as a secondary observation for `response_inhibition`
but does not update the profile directly; the profile-facing outcome is
`n_back_accuracy` for `working_memory`.

#### letter_number_sequencing

| Metric | Field | Meaning |
|---|---|---|
| `accuracy` | `metrics["accuracy"]` | Proportion of valid trials with a correct response.  Range [0, 1].  **Profile-facing outcome.** |
| `lns_span_max` | `metrics["lns_span_max"]` | Maximum sequence length with at least one correct response. |
| `mean_rt_ms` | `metrics["mean_rt_ms"]` | Mean RT across valid trials. |

Trials exceeding 30 000 ms are marked invalid.  The count metric is
`valid_trials_count`.

### Uncertainty representation

The same Beta posterior model applies.  All three tasks update the same
`working_memory` dimension sequentially (each session appends a new Evidence
record).  The posterior integrates evidence across paradigms, which means the
implicit assumption is that all three tasks measure a common underlying
construct.  No separate sub-dimension tracks are maintained.

### Known biases / limits

- **Paradigm heterogeneity.** Digit span (passive recall), N-back (continuous
  updating), and letter-number sequencing (active manipulation) tap related but
  distinguishable processes.  Collapsing them into one dimension increases noise.
- **N-back controversy.** Transfer from N-back training to general working memory
  is debated in the literature; d′ is a more informative signal than raw accuracy
  but is still task-specific.
- **Verbal vs. visuospatial.** Digit span is verbal; Corsi blocks (in
  `sequential_visual_memory`) is visuospatial.  The two are not interchangeable.
- **Practice effects.** All three tasks show strong practice-related improvement.
- **Scale differences.** The three tasks have different ceilings and floor
  effects; accuracy values near 0 or 1 carry less information.
- **Non-clinical.** None of these metrics is equivalent to a standardised
  clinical working memory battery.

---

## 4. cognitive_flexibility

### Definition

The capacity to shift between rules, perspectives, or response sets.  Measured
through interference resolution (Stroop) and perceptual bistability (Perception Lab).

### Tasks mapped

| Task | `task_id` |
|---|---|
| Stroop | `stroop` |
| Perception Lab | `perception_lab` |

### What is scored

#### stroop

| Metric | Field | Meaning |
|---|---|---|
| `incongruent_accuracy` | `metrics["incongruent_accuracy"]` | Proportion of valid incongruent trials with a correct ink-color response.  Range [0, 1].  **Profile-facing outcome.** |
| `congruent_accuracy` | `metrics["congruent_accuracy"]` | Proportion of valid congruent trials correct.  Used as a quality signal. |
| `overall_accuracy` | `metrics["overall_accuracy"]` | Overall proportion correct across all valid trials. |
| `stroop_effect_ms` | `metrics["stroop_effect_ms"]` | Mean incongruent RT minus mean congruent RT on correct trials (ms, clamped ≥ 0). |
| `mean_rt_congruent_ms` | `metrics["mean_rt_congruent_ms"]` | Mean RT on correct congruent trials. |
| `mean_rt_incongruent_ms` | `metrics["mean_rt_incongruent_ms"]` | Mean RT on correct incongruent trials. |
| `mean_rt_ms` | `metrics["mean_rt_ms"]` | Mean RT across all valid trials. |

Trials below 150 ms (`STROOP_ANTICIPATION_MS`) or above 3 000 ms
(`STROOP_TIMEOUT_MS`) are marked invalid.  Omissions are also invalid.  The
count metric is `valid_trials_count`.

#### perception_lab

| Metric | Field | Meaning |
|---|---|---|
| `perceptual_stability` | `metrics["perceptual_stability"]` | Proxy score in [0, 1]: `max(0, 1 − switch_rate / 30)`.  Higher = more stable.  **Profile-facing outcome.** |
| `switch_rate` | `metrics["switch_rate"]` | Mean number of perceptual alternations per observation period (from bistable figure trials). |
| `detection_rate` | `metrics["detection_rate"]` | Proportion of change-blindness trials where a change was correctly detected. |
| `mean_rt_ms` | `metrics["mean_rt_ms"]` | Mean RT across valid trials. |

Trials above 60 000 ms (`PERCEPTION_MAX_RT_MS`) are marked invalid.
Subtasks: `necker_cube`, `ambiguous_figures`, `change_blindness`.  The count
metric is `valid_trials_count`.

### Uncertainty representation

Same Beta posterior model.  Both tasks update the same `cognitive_flexibility`
dimension.  `perceptual_stability` is a derived proxy; its range is determined by
the normalization constant 30 (switch\_rate / 30), which is a design choice and
has not been empirically validated against population norms.

### Known biases / limits

- **Stroop interference ≠ flexibility.** The Stroop effect measures selective
  attention and conflict monitoring; calling it "cognitive flexibility" is an
  approximation.  The SPEC notes this is a configurable design choice.
- **perceptual_stability proxy.** The formula `1 − switch_rate / 30` is a
  design hypothesis.  Switch rate above 30 saturates at 0.  The constant 30
  is not derived from normative data.
- **Heterogeneous subtasks.** Bistable-figure switching and change-blindness
  detection are distinct phenomena.  Their combination into one `perceptual_stability`
  score discards information.
- **Practice effects.** Both tasks are sensitive to familiarity with the stimuli.
- **Non-clinical.** Neither score is equivalent to a clinical flexibility or
  attention measure.

---

## Future work

The following dimensions are reserved for future work and have no task, scorer,
or registry entry in the current code:

| Dimension | SPEC id | Description |
|---|---|---|
| Logical reasoning | `logical_reasoning` | Drawing valid conclusions; short logic problems; explanation quality. |
| Critical thinking | `critical_thinking` | Questioning and verifying claims, including the LLM's own answers; error-spotting probes; verification behavior. |
