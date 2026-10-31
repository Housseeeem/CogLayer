# Privacy and Data Handling

This document describes what CogLayer actually stores, how consent works, and
how data can be deleted.  Where the specification (`docs/SPEC.md`) describes an
intent that has not yet been implemented in code, this is stated explicitly.

---

## Consent

Consent is required before any session can be created.  The `ConsentService`
(in `src/coglayer/privacy/consent.py`) provides three operations:

- **`record_consent(user_id, guardian_consent, guardian_id)`** — creates or
  replaces the consent record for a user.  `consented_at` is set to the current
  UTC timestamp.  `guardian_consent` (boolean) and `guardian_id` (optional
  string) support parental consent for minors.
- **`revoke_consent(user_id)`** — sets `revoked_at` on the existing record.
  If no record exists this is a no-op (idempotent).
- **`has_consented(user_id)`** — returns `True` only if a record exists and
  `revoked_at` is `None`.

The `POST /v1/assessment/sessions` endpoint calls `has_consented` before
creating a session and returns HTTP 403 if consent is absent.  Several other
endpoints perform the same check before returning data.

The consent record is stored in the `consent` table of the SQLite database
(file path from `Settings.database_path`).  Fields: `user_id`, `consented_at`
(ISO-8601 UTC), `revoked_at` (NULL while active), `guardian_consent` (0/1),
`guardian_id`.

---

## What is stored

CogLayer persists the following categories of data.  **Raw message text from
the user's conversation with the LLM is not persisted by default.**

### Assessment data

Stored in the `sessions`, `trials`, `task_metrics`, and `data_quality` tables.

| Category | Content |
|---|---|
| Sessions | Session ID, user ID, start/end timestamps, status, session type, list of completed task IDs. |
| Trials | Per-trial stimulus, expected response, actual response, reaction time, validity flag, invalidity reason.  This is structured task data (e.g., which button was pressed), not free-text conversation. |
| Task metrics | Aggregate computed metrics per (session, task): accuracy, span lengths, reaction times, etc. |
| Data quality | Valid trial counts, total trial counts, completeness ratio, anomaly flags. |

### Cognitive profile

Stored in the `profiles` table as a JSON blob (`CognitiveProfile` serialised
via Pydantic).  Contains per-dimension:

- Posterior mean and 90 % credible interval (lower, upper).
- Number of evidence updates (`n_evidence`).
- Timestamp of last update.
- Internal Beta distribution parameters (α, β) for resuming the model.
- Uncertainty estimate (upper − mean).

The profile contains **derived indicators only** — not the raw user messages that
produced those indicators.

### Collaboration events (IOI)

Stored in the `collaboration_events` table.  Each record captures a structured
observation: which IOI component, which opportunity, whether the behavior was
observed, a validity flag, and a timestamp.  No message text is stored.

### Experience profile

Stored in the `experience_profiles` table.  Contains onboarding answers: age
group, goals, tech comfort level, information style, layout preference, theme
preference, and guidance level.  Created at onboarding; updated if the user
revisits onboarding.

### Coach conversations

Stored in the `coach_conversations` and `coach_messages` tables.  `coach_messages`
stores the `content` (text) of each turn in a coaching conversation, along with
role (`user` or `assistant`) and timestamp.

**This is an exception to the "derived indicators only" rule described in
`docs/SPEC.md` section 9.**  The SPEC states: "Raw message text stays in memory
for the current session and is not persisted by default."  The current code does
persist coaching conversation text.  The columns are:

```sql
coach_messages.content TEXT NOT NULL
```

This should be reviewed against the data minimization requirement before
production deployment.

### Daily plans

Stored in the `daily_plans` table as a JSON blob.  Contains the generated
task sequence for a given date, not user messages.

---

## Provider boundary

Providers (Gemini, Groq, Ollama) receive the conversation and a neutral
coaching instruction.  The `CognitiveProfile` is **never sent to a provider**.
This is enforced at the architecture level: the `api` and `ui` modules wire
implementations to interfaces; the profile is consumed only inside `coglayer`
itself.

---

## Deletion

### API endpoint

`DELETE /v1/assessment/users/{user_id}` (defined in
`src/coglayer/api/routers/admin.py`, registered under the prefix
`/v1/assessment`).

This endpoint calls, in order:

1. `assessment_repo.delete_user(user_id)` — removes all rows in `sessions`,
   and (via `ON DELETE CASCADE`) all rows in `trials`, `task_metrics`,
   `data_quality`, and `collaboration_events` for that user.
2. `profile_repo.delete_user(user_id)` — removes the row in `profiles`.
3. `consent_repo.delete_consent(user_id)` — removes the row in `consent`.
4. `conversation_repo.delete_user(user_id)` — removes rows in
   `coach_conversations`, and (via cascade) `coach_messages`.
5. `experience_profile_repo.delete_user(user_id)` — removes the row in
   `experience_profiles`.

On success the endpoint returns HTTP 204 No Content.  The deletion is covered
by tests in `tests/unit/test_storage.py` and `tests/unit/test_storage_property.py`.

### Local mode

When using the Ollama provider, no data leaves the machine.  The SQLite database
is a local file at the path configured in `Settings.database_path`.

---

## Retention policy

`docs/SPEC.md` section 9 states: "default 30 days [ASSUMPTION], configurable;
expired data is deleted automatically."

**This is not implemented in the current code.**  There is no scheduled job,
background task, cron entry, or database trigger that purges expired records.
The `RetentionPolicy` and `Eraser` interfaces mentioned in the SPEC are not
present in the codebase.

Data persists until explicitly deleted via the `DELETE /v1/assessment/users/{id}`
endpoint or manual database administration.

---

## Summary of gaps relative to SPEC.md

| SPEC requirement | Status in code |
|---|---|
| Persist derived indicators only; raw message text not stored by default (§9) | Partially implemented: coaching conversation text is persisted in `coach_messages.content`. |
| 30-day default retention with automatic expiry (§9) | Not implemented. No purge mechanism exists. |
| `RetentionPolicy` and `Eraser` interfaces (§5) | Not implemented. |
