# CogLayer: product and technical specification (v0.1)

Status: working draft. Items marked **[ASSUMPTION]** were not defined by the
challenge brief and are our own choices; revisit them if the organizers clarify.

## 1. Purpose

CogLayer is a provider-agnostic layer placed between a user and any LLM. It
observes the interaction, builds an uncertainty-aware cognitive profile,
coaches the user with explainable feedback, and generates adaptive exercises.
It is the mirror of RLHF: instead of humans improving the model, the model
interaction helps improve the human.

Non-goals: medical or clinical assessment, diagnosis, IQ testing, face or voice
analysis, training or fine-tuning any LLM.

## 2. Constraints from the challenge brief (CIS-TAC 1.0, AI4Brain)

- Loop: Assess (non-clinical profile across cognitive dimensions), Understand
  (uncertainty-aware percentage profile from performance and errors), Coach
  (explainable, personalized feedback and motivation), Improve (adaptive
  exercises and measurable learning paths).
- Layers A to C mandatory, layer D optional (bonus: voice coaching,
  emotion-aware AI, predictive cognitive growth).
- Ethics and data: consent, retention and deletion documented; no sensitive
  decision based on face or voice alone.
- Deliverables: public GitHub repository, 3 to 5 minute demo video, technical
  report (max 8 pages), presentation (max 15 slides). Everything in English.
- Dates: Phase 1 submission deadline 1 Nov 2026; Phase 2 pitch on 7 Nov 2026
  (8 minutes plus 5 minutes of questions, with a surprise element revealed the
  day before).
- Scoring: Phase 1 counts 60 percent (relevance 20, quality 20, innovation 20,
  UX 15, explainability 15, safety 10); Phase 2 counts 40 percent
  (generalisation 25, robustness 25, profile quality 20, plan relevance 15,
  defense 15).

## 3. Layers **[ASSUMPTION]**

The brief does not define layers A to C. We define them as:

- **Layer A, Assess:** signal collection (passive signals plus active probes).
- **Layer B, Understand:** probabilistic profile model.
- **Layer C, Coach and Improve:** intervention policy, feedback, exercises,
  learning path.
- **Layer D, optional:** growth prediction first; text-based affect estimation
  and voice interaction only if time remains.

## 4. Cognitive dimensions

The implemented battery covers four active dimensions across eight tasks:

| Id | Dimension | Meaning | Implemented tasks |
|---|---|---|---|
| `response_inhibition` | Response inhibition | Capacity to withhold a prepotent response | Go/No-Go (`go_no_go`) |
| `sequential_visual_memory` | Sequential visual memory | Visuospatial sequence retention and recall | Sequence Span (`sequence_span`), Corsi Blocks (`corsi_blocks`) |
| `working_memory` | Working memory | Holding and using several pieces of information at once | Digit Span (`digit_span`), N-Back (`n_back`), Letter-Number Sequencing (`letter_number_sequencing`) |
| `cognitive_flexibility` | Cognitive flexibility | Adapting when a rule or constraint changes | Stroop (`stroop`), Perception Lab (`perception_lab`) |

Dimensions are configuration, not code: adding one must not require changing
existing modules.

### Future work (planned dimensions)

| Id | Dimension | Meaning | Planned evidence |
|---|---|---|---|
| `logical_reasoning` | Logical reasoning | Drawing valid conclusions | Short logic problems; explanation quality |
| `critical_thinking` | Critical thinking | Questioning and verifying claims, including the LLM's own answers | Error-spotting probes; verification behavior |

## 5. Modules and interfaces

All interfaces are `typing.Protocol` classes in `core`.

| Module | Interface | Input | Output |
|---|---|---|---|
| `providers` | `LLMProvider.complete(request) -> response` | messages, model, options | text and usage metadata |
| `signals` | `SignalExtractor.extract(turn) -> list[Evidence]` | one interaction turn | evidence items |
| `signals` | `ProbeLibrary.next_probe(context) -> Probe` | profile state, context | a micro-challenge with a checkable answer |
| `profile` | `ProfileModel.update(evidence)` and `.estimate(dim)` | evidence | `DimensionEstimate` |
| `coach` | `CoachPolicy.choose(state) -> Intervention` and `.feedback(outcome)` | profile state | intervention; reward update |
| `exercises` | `ExerciseGenerator.generate(dim, level) -> Exercise` *(reserved for future work)* | dimension, level | validated exercise |
| `privacy` | `ConsentStore`, `Eraser` | user id | consent state; deletion |
| `sim` | `SimulatedUser.respond(item) -> Answer` *(reserved for future work)* | probe or exercise | answer following a hidden true profile |

Core data types (pydantic):

- `Evidence`: dimension id, outcome in [0, 1], source (`passive` or `active`),
  weight, timestamp, short machine-readable reason code.
- `DimensionEstimate`: mean, lower and upper bounds of a 90 percent credible
  interval, number of evidence items, last update.
- `Intervention`: one of `direct`, `hint_first`, `predict_then_reveal`,
  `explain_back`, `delayed_quiz`.
- `Exercise`: id, dimension, level, prompt, answer specification, verifier id.

## 6. Profile model (layer B)

Per user and dimension, keep a Beta(alpha, beta) distribution, prior
Beta(1, 1).

- Update with evidence of outcome `s` in [0, 1] and weight `w`:
  `alpha += w * s`, `beta += w * (1 - s)`.
- Weights: active probes have a high weight, passive signals a low weight
  (initial values 1.0 and 0.2, to be tuned on the simulator).
- Forgetting: before each update, shrink toward the prior with factor
  `lambda` (initial 0.98 per update):
  `alpha = 1 + lambda * (alpha - 1)`, same for beta.
- Output: mean as a percentage and the 90 percent credible interval from Beta
  quantiles. The UI always shows the interval and the number of observations.
- Every displayed statement must trace back to stored evidence items.

## 7. Coach policy (layer C)

- Arms: the interventions listed above.
- Algorithm: Thompson sampling, one bandit per (user, dimension) in the MVP.
- Reward: success on a delayed retrieval check of the same concept (not
  immediate success), which measures learning instead of momentary performance.
- Safety rails: the user can switch to `direct` mode at any time; never
  interrupt more than once per N turns (configurable); no coaching on
  sensitive topics.
- Feedback must cite evidence: what was observed, what it suggests, what to
  try next, in encouraging non-clinical wording.

## 8. Exercises (improve)

- Generated by an LLM under a strict JSON schema, per dimension and level.
- Hard rule: every exercise has an answer verifiable by code (`verifier id`).
  Exercises that fail validation are rejected and regenerated.
- A learning path is a weekly sequence of exercises targeting the dimension
  with the lowest lower-bound, with a measurable before/after target.

## 9. Privacy and ethics requirements

- **Consent:** explicit consent screen before any data is processed; states
  what is stored, what goes to the chosen provider, and that the tool is
  non-clinical. Consent can be revoked; minors require guardian consent.
- **Minimization:** store derived indicators only (evidence items, estimates,
  intervention outcomes). Coach conversation text is persisted ONLY when
  `COGLAYER_STORE_CONVERSATIONS=true` (default: false); otherwise it remains in
  process memory only.
- **Storage:** data is kept locally in SQLite across 11 tables (`consent`,
  `sessions`, `trials`, `task_metrics`, `data_quality`, `profiles`,
  `experience_profiles`, `collaboration_events`, `daily_plans`,
  `coach_conversations`, `coach_messages`).
- **Provider boundary:** providers receive the conversation and a neutral
  instruction, never the profile. Only `fake` and `groq` are implemented;
  Gemini and Ollama are planned (not implemented).
- **Retention:** data is kept locally in SQLite until the user deletes it via
  `DELETE /v1/assessment/users/{user_id}`. Automatic retention purge is a
  planned improvement.
- **Deletion:** a "delete everything" action and API endpoint that removes all
  data for a user, covered by tests.
- **Local mode:** runs fully locally with the fake provider and local SQLite.
  Local LLM execution via Ollama is planned for future work.
- **Non-clinical wording:** disclaimer visible in the UI; vocabulary rules in
  `AGENTS.md`.
- **No face or voice** inputs in the MVP.
- Testing uses synthetic scenarios and simulated users only, never real
  personal conversations.

## 10. Simulator and evaluation

Simulated users have a hidden true profile and answer with a probabilistic
response model (probability of success rises with true skill, with noise).

Personas: honest, noisy, random answerer, cheater (copies the LLM), fast
learner, plateauing learner.

Metrics:

- **Profile recovery error:** mean absolute error between estimated and true
  profile.
- **Calibration:** a 90 percent interval should contain the true value about
  90 percent of the time.
- **Convergence speed:** number of interactions until the interval is narrower
  than a threshold.
- **Learning gain:** adaptive coach versus a direct-answer baseline on
  simulated learners.
- **Robustness:** degradation of the above under noise, random answers and
  provider failures.

State clearly in the report that simulator results concern simulated users;
complement them with a small pilot (5 to 10 volunteers) if time allows.

## 11. MVP scope

In scope: one real provider (Groq free tier) plus the fake provider (Gemini and
Ollama are planned, not implemented), four dimensions across eight tasks,
coaching feedback and multi-turn chat, profile dashboard with uncertainty,
consent and deletion, growth prediction as the bonus feature.
The `exercises` and `sim` modules are empty stubs reserved for future work.

Out of scope for the MVP: voice, emotion detection from face or voice, browser
extension, multi-tenant hosting, mobile apps.

## 12. Milestones (2 people, about 4 weeks)

| Week | Goal |
|---|---|
| 1 (1-7 Oct) | Repo, `make check` and CI, `core`, fake provider, provider adapters, profile model v0, simulator v0 |
| 2 (8-14 Oct) | Probes, exercises with verifiers, coach v1, chat UI. **End of week: complete loop working** |
| 3 (15-21 Oct) | Dashboard, evaluation metrics, consent and deletion, growth prediction, small pilot |
| 4 (22-28 Oct) | Fixes, video, slides, report, submission by about 28 Oct |
| 29 Oct - 1 Nov | Safety margin and form submission |
| 2-7 Nov | Pitch preparation, rehearsal for the surprise element |

If time runs short, cut in this order: voice and emotion, second live provider
in the demo, then extra coach interventions. Never cut: uncertainty-aware
profile, explanations, simulator metrics, ethics.

## 13. Open questions

- Do the organizers define layers A to C or the dimensions elsewhere?
- Is the report required at Phase 1 (brief section 3 suggests so, section 5
  lists only three items)?
- Can the team exceed four members if it includes an IEEE CIS or IEEE YP member?
- Which providers and API budgets are actually available to us?
