# AI Collaboration Score (IOI)

The AI Collaboration Score is an **experimental** measure of how effectively a
user collaborates with an AI assistant.  It is not a validated psychometric
instrument and should not be interpreted as a definitive assessment of any
individual.

The implementation lives in `src/coglayer/core/ioi.py`
(`IOIScoringService.score`) and the data models in `src/coglayer/core/models.py`
(`IOIComponent`, `IOIObservation`, `IOIComponentScore`, `IOIScore`).

---

## Components and weights

The score is composed of five components.  The table below shows the exact
weights as defined by the constant `IOI_WEIGHTS` in `ioi.py`.

| Component | `IOIComponent` enum value | Weight |
|---|---|---|
| Critical verification | `CRITICAL_VERIFICATION` | 0.25 |
| Clarification | `CLARIFICATION` | 0.20 |
| Iteration | `ITERATION` | 0.20 |
| Autonomy | `AUTONOMY` | 0.20 |
| Responsible use | `RESPONSIBLE_USAGE` | 0.15 |

The weights sum to exactly 1.0 (enforced at module load time; a `RuntimeError`
is raised if they do not).

> **Weights match the task brief.** The brief stated candidate weights of
> clarification 20, critical verification 25, iteration 20, autonomy 20,
> responsible use 15.  The code matches these values exactly.

---

## Scale

The aggregate score is expressed as a **proportion in [0, 1]**, not as a
0–100 integer.  If you need a percentage display, multiply by 100.

The `IOIScore.aggregate_score` field is either a `float` in [0, 1] or `None`
when the evidence is insufficient (see below).

---

## How each component is computed

### Observations

Each observation is an `IOIObservation` with these fields:

- `user_id` — the user the observation belongs to.
- `component` — which `IOIComponent` this observation records.
- `opportunity_id` — a unique identifier for the collaboration opportunity
  (e.g., a specific task or prompt instance).
- `behavior_observed` — `True` if the collaborative behavior was observed,
  `False` otherwise.
- `valid` — whether the observation is usable (observations marked invalid are
  excluded from scoring).

The scoring service deduplicates observations by `(component, opportunity_id)`:
only the **first** observation for each `(component, opportunity_id)` pair is
kept.

### Per-component score

For each component, the service:

1. Filters observations to those that are `valid=True` and match the component.
2. After deduplication, counts the qualifying observations as `evidence_count`.
3. Computes the component score as:

```
component_score = sum(behavior_observed for obs in valid_obs) / evidence_count
```

This is the proportion of valid deduplicated opportunities where the behavior
was observed.  Range [0, 1].  If `evidence_count = 0`, the score defaults to
0.0.

4. Records whether the component has sufficient evidence:

```
sufficient = evidence_count >= IOI_MINIMUM_OBSERVATIONS  (= 3)
```

### Aggregate score

The aggregate score is computed only when **all five components** have
sufficient evidence (`evidence_count >= 3`):

```
aggregate_score = sum(component.score * component.weight for each component)
```

This is a weighted sum with the weights from the table above.  Range [0, 1].

If any component has fewer than 3 observations, `aggregate_score` is `None`
and the `IOIScore.status` field is `"INSUFFICIENT_EVIDENCE"`.  When all
components are sufficient, `status` is `"AVAILABLE"`.

### Calculation version

`IOIScore.calculation_version` is the constant string `"1.0"`.  This field
allows future consumers to detect when the formula has changed and recompute
historical scores if needed.

---

## Limitations

- **Experimental.** The IOI score has not been validated against independent
  measures of human-AI collaboration quality or productivity.
- **Minimum observations.** Three observations per component is a low threshold.
  Scores based on exactly three observations have high variance.
- **Deduplication is first-wins.** Only the first observation per
  `(component, opportunity_id)` is used.  Revised observations submitted later
  are silently ignored.
- **Binary behavior.** Each observation records either "behavior observed" or
  not.  Graded or partial behaviors are not represented.
- **No longitudinal model.** Unlike the cognitive dimensions, the IOI score has
  no forgetting factor and no Bayesian posterior.  Each call to
  `IOIScoringService.score` computes the score from the full list of
  observations passed in; history management is the caller's responsibility.
- **Not a validated measure.** The weights, the component definitions, and the
  minimum-observations threshold are design choices, not empirically derived
  parameters.
