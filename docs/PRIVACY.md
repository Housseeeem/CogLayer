# Privacy and Data Handling

This document describes what CogLayer actually stores, how consent works, and
how data can be deleted. Where the original specification described features
not yet in code, this document describes the actual implemented behavior and
notes planned improvements.

---

## Consent

Consent is required before any session can be created. The `ConsentService`
(in `src/coglayer/privacy/consent.py`) provides operations to record, check, and
revoke consent:

- **`record_consent(user_id, guardian_consent, guardian_id)`** — creates or
  replaces the consent record for a user. `consented_at` is set to the current
  UTC timestamp. Minors require guardian consent: `guardian_consent` (boolean)
  and `guardian_id` (optional string) are stored.
- **`revoke_consent(user_id)`** — revokes consent by setting `revoked_at` to
  the current timestamp. If no record exists this is a no-op (idempotent).
- **`has_consented(user_id)`** — returns `True` only if an active record exists
  and `revoked_at` is `None`.

The `POST /v1/assessment/sessions` endpoint verifies consent before
creating a session and returns HTTP 403 if consent is missing or revoked.

---

## What is stored

CogLayer stores data locally in a SQLite database (file path configured via
`COGLAYER_DATABASE_PATH`, default `coglayer.db`). Assessment and profile data are
stored as derived indicators and task metrics. Coach conversation text is
held in memory and is persisted to SQLite **ONLY** when explicitly enabled via
`COGLAYER_STORE_CONVERSATIONS=true` (default: `false`).

The exact database tables and their contents are:

| Table | Content stored |
|---|---|
| `consent` | User consent record: `user_id`, `consented_at`, `revoked_at`, `guardian_consent` (0/1), `guardian_id`. |
| `sessions` | Assessment sessions: `session_id`, `user_id`, `created_at`, `started_at`, `completed_at`, `status`, `session_type`, `completed_tasks`. |
| `trials` | Structured task trials: `trial_id`, `session_id`, `task_id`, `trial_index`, `stimulus`, `expected_response`, `actual_response`, `reaction_time_ms`, `is_valid`, `invalidity_reason`. No conversation text. |
| `task_metrics` | Computed metrics per (session, task): `metric_id`, `session_id`, `task_id`, `accuracy`, `mean_reaction_time_ms`, `span_length`, `metrics_json`. |
| `data_quality` | Task data validation records: `quality_id`, `session_id`, `task_id`, `valid_trials`, `total_trials`, `completeness_ratio`, `anomaly_flags`. |
| `profiles` | Serialized Bayesian cognitive profile (`CognitiveProfile` JSON): `user_id`, `updated_at`, `profile_data` containing dimension posteriors (α, β, mean, 90% credible interval) and evidence history. Derived indicators only. |
| `experience_profiles` | User onboarding preferences: `user_id`, `updated_at`, `profile_data` (age group, goals, tech comfort, information style, layout, theme, guidance level). |
| `collaboration_events` | AI Collaboration Score observations: `event_id`, `user_id`, `session_id`, `component`, `opportunity_id`, `behavior_observed`, `is_valid`, `timestamp`. |
| `daily_plans` | Adaptive daily task recommendations: `plan_id`, `user_id`, `plan_date`, `target_dimensions`, `tasks`, `total_estimated_duration_min`, `rationale`. |
| `coach_conversations` | Coaching conversation metadata: `conversation_id`, `user_id`, `session_id`, `created_at`. |
| `coach_messages` | Individual conversation turns: `message_id`, `conversation_id`, `role`, `content`, `timestamp`. **Populated only when `COGLAYER_STORE_CONVERSATIONS=true`.** When `false` (default), messages exist only in process memory during the run. |

---

## Provider boundary

CogLayer supports the `fake` provider (deterministic local testing) and `groq`
(cloud LLM provider). Other providers such as Gemini and Ollama are planned but
not implemented.

The LLM provider receives only the conversation text and a neutral coaching
instruction. The `CognitiveProfile` and raw task trials are **never sent to
an external LLM provider**.

---

## Retention and Deletion

### Local data retention

Data is kept locally in the SQLite database until the user requests its deletion.
There is currently no automatic retention purge mechanism.

### Deletion endpoint

The user can delete all their data at any time via:
`DELETE /v1/assessment/users/{user_id}`

This endpoint completely deletes all associated rows across all 11 tables:
1. `sessions` (and cascades to `trials`, `task_metrics`, `data_quality`, `collaboration_events`)
2. `profiles`
3. `consent`
4. `coach_conversations` (and cascades to `coach_messages`)
5. `experience_profiles`
6. `daily_plans`

On success the endpoint returns HTTP 204 No Content.

### Planned improvements

- **Automatic retention purge:** A scheduled background retention cleaner to
  automatically purge data older than a configurable retention window (e.g.,
  30 days).
- **Local offline LLM provider:** An Ollama provider adapter to enable coaching
  without external network calls.
