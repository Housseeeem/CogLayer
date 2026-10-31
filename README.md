# CogLayer

[![CI](https://github.com/Housseeeem/CogLayer/actions/workflows/ci.yml/badge.svg)](https://github.com/Housseeeem/CogLayer/actions/workflows/ci.yml)

## What CogLayer is

CogLayer is a provider-agnostic cognitive coaching layer built for the IEEE CIS
TAC CISTAC 1.0 AI4Brain challenge. It sits between a user and any large language
model and runs the loop Assess → Understand → Coach → Improve. It tracks
performance on standardized interactive tasks, builds an uncertainty-aware
profile, and generates supportive coaching feedback. CogLayer is non-clinical:
it does not perform any medical or clinical evaluation, and none of its outputs
are a diagnosis.

## What it does

### Layer A — Assess and understand

CogLayer measures four cognitive dimensions through eight keyboard/mouse tasks,
with no camera or microphone input (non-biometric mode):

| Dimension | Tasks |
|---|---|
| response_inhibition | Go/No-Go |
| sequential_visual_memory | Visual Sequence Span, Corsi Blocks |
| working_memory | Digit Span, N-Back (2-back), Letter-Number Sequencing |
| cognitive_flexibility | Stroop, Perception Lab |

For each dimension the profile model maintains a Beta(α, β) posterior. After
every completed task it reports a posterior mean (in [0, 1]) and a 90 %
credible interval. A forgetting factor (λ = 0.98) shrinks the posterior toward
a uniform prior between sessions so that stale evidence loses influence over
time. The Brain Twin module tracks an exponential moving-average baseline per
user and reports variation signals once sufficient comparable observations are
available.

### Layer B — Coach

The coaching module has two distinct surfaces:

**Coaching feedback summary** (`POST /v1/assessment/coach/{user_id}`): builds a local text
summary from the user's profile dimensions (percentage estimate, credible
interval, session count). When `coach_use_llm` is enabled and a provider is
configured, the local summary is sent to the provider with a neutral coaching
instruction so it can be rewritten in a friendly tone; the CognitiveProfile
object is never sent to the provider. When `coach_use_llm` is false or no
provider is configured, the local text is returned directly — there is no
fallback error message in this path.

**Conversation chat** (`POST /v1/assessment/coach/{user_id}/conversations/{conversation_id}/messages`): a
multi-turn chat interface. When `coach_use_llm` is false or no provider is
configured, every reply is the fixed fallback message "The conversation service
is temporarily unavailable. Please try again later." without calling any
external service.

### Layer C — Visualise and plan

The Cognitive Profile & Dashboard (screen 4) displays:

- A Brain Twin Fast-Track section showing the current variation flag for comparable
  Go/No-Go outcomes.
- A radar chart of the four dimension means with 90 % credible interval bounds.
- Progress curves showing how each dimension has evolved across sessions.
- A performance heatmap: rows are the four cognitive dimensions and columns are
  sessions numbered 1, 2, … N in chronological order; each cell shows the mean
  outcome across all tasks completed in that dimension during that session.
- An Assessment History table listing every evidence record in reverse chronological
  order.

The Cognitive Lab (screen 3) displays a daily recommended session: 2 or 3 tasks
selected by the `AdaptiveGameSelector` using a deterministic daily seed, history
performance, recency prevention, Brain Twin variation signal, user preference, guidance
level, and optional fatigue feedback.

### AI Collaboration Score (experimental)

The AI Collaboration Score is an experimental measure of how a user
collaborates with an AI assistant. It is composed of five components
(critical verification 0.25, clarification 0.20, iteration 0.20, autonomy 0.20,
responsible use 0.15). The internal aggregate is a weighted proportion in [0, 1];
the UI displays it as `x / 100` (for example `72.3 / 100`) by multiplying the
internal value by 100. The score is only available once **each component
individually** has at least three valid observations (`INSUFFICIENT_EVIDENCE` is
returned until every component meets that threshold). It is not a validated
psychometric instrument.

## Quick start

### Installation

```
make install
```

This runs `uv sync --all-extras` and installs the pre-commit hooks.

### Run the API

```
uv run uvicorn coglayer.api.app:app --port 8000
```

### Run the UI

```
uv run streamlit run src/coglayer/ui/app.py
```

Open `http://localhost:8501` in a browser. The UI expects the API to be running
at `http://localhost:8000` (override with the `COGLAYER_API_URL` environment
variable).

### Run the demo data script

The script requires a running API. It creates 6 assessment sessions for the
synthetic user `demo_user_001` (4 tasks per session, all 8 tasks covered) and
prints `SIMULATED DEMO DATA` with a profile summary to the console.

```
uv run python scripts/demo_simulation.py --api-url http://localhost:8000
```

### Run the tests

```
uv run pytest --no-cov -q
```

Drop `--no-cov` to also produce a coverage report (85 % threshold overall,
95 % for `profile` and `coach`).

## The six screens

1. **Informed Consent** — displays stored data details and the local-mode guarantee; consent is required before any session is created.
2. **Onboarding** — collects age group, goals, tech comfort, information style, layout and theme preferences; stored in the experience profile.
3. **Cognitive Lab** — entry point for assessment sessions; lists resumable and completed sessions, allows creating a new one, and shows the daily recommended session (2 or 3 tasks selected by the adaptive selector for the current date).
4. **Cognitive Profile & Dashboard** — Brain Twin variation flag, radar chart, progress curves, performance heatmap, and assessment history table.
5. **Cognitive Coach** — multi-turn chat interface. When `coach_use_llm` is true and a provider is active, the chat is powered by the provider. Without a provider (or when `coach_use_llm` is false) every reply is the fixed fallback message "The conversation service is temporarily unavailable. Please try again later."
6. **AI Collaboration Score** — records explicit IOI component observations and shows the current score or `INSUFFICIENT_EVIDENCE` status.

## Documentation

- [docs/DIMENSIONS.md](docs/DIMENSIONS.md) — the four active dimensions, their eight tasks, scoring formulas, and known biases.
- [docs/AI_COLLABORATION_SCORE.md](docs/AI_COLLABORATION_SCORE.md) — AI Collaboration Score components, weights, and limitations.
- [docs/PRIVACY.md](docs/PRIVACY.md) — what is stored, consent flow, the deletion endpoint, and gaps relative to the spec.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — module map, dependency contracts, data flow, and storage schema.
- [docs/SPEC.md](docs/SPEC.md) — original product specification and requirements.

## Privacy and ethics

Consent is recorded before any session can be created; the API returns HTTP 403
without it. All task measurements come from keyboard and mouse only — no camera
or microphone. A `DELETE /v1/assessment/users/{user_id}` endpoint removes all
stored data for a user across every table. Two gaps relative to the
specification are worth noting: coaching conversation text (the content of each
turn) is persisted in the `coach_messages` table, contrary to the spec's
"derived indicators only" policy; and automatic 30-day data retention is not
implemented — no purge mechanism exists, so data persists until explicitly
deleted via the endpoint above.

## Known limitations

- Goal tracking is not surfaced in the UI dashboard.
- The `logical_reasoning` and `critical_thinking` dimensions appear in
  `docs/SPEC.md` but have no task, scorer, or registry entry in the current
  code.
- User identity is declared (a string entered in the sidebar) and is not
  authenticated; there is no authentication layer in the current codebase.
- The coaching conversation feature has two surfaces: the one-shot feedback
  summary always returns a locally-generated text (no fallback message); the
  multi-turn chat requires `coach_use_llm = true` plus a valid provider and API
  key in environment variables. Without those, every chat reply is the fixed
  fallback message "The conversation service is temporarily unavailable. Please
  try again later." without calling any external service; the rest of the
  application works normally.

## Tests and quality

Run the tests:

```
uv run pytest --no-cov -q
```

Run the full quality gate (required before every commit):

```
make check
```

`make check` runs in order: `ruff format --check`, `ruff check`, `mypy`,
`lint-imports` (architecture contracts), `pytest` with the coverage threshold,
`gitleaks` (secret scanning), and `pip-audit` (dependency audit). The same
sequence runs in CI on every push and pull request.

For a faster inner loop during development:

```
make quick
```

`make quick` runs format check, lint, typecheck, and architecture contracts
only (no tests, no audit).
