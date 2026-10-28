-- CogLayer cognitive assessment database schema
-- SQLite 3.x; foreign keys must be enabled per-connection: PRAGMA foreign_keys = ON
--
-- Tables:
--   consent       -- user consent records (R-001.1, R-001.4)
--   sessions      -- assessment session metadata (R-005.1, R-005.2)
--   trials        -- raw per-trial data, FK to sessions (R-005.1, R-001.3)
--   task_metrics  -- per-task aggregate metrics, composite PK (R-005.1)
--   data_quality  -- per-task data quality summary, composite PK (R-005.1)
--   profiles      -- cognitive profile JSON blob per user (R-006.2)
--   collaboration_events -- structured IOI observations only
--
-- No triggers: timestamps are set explicitly in Python for determinism.
-- No utcnow(): Python always stores ISO-8601 strings with UTC offset.

-- -------------------------------------------------------------------------
-- Consent (R-001.1, R-001.4)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consent (
    user_id          TEXT    NOT NULL PRIMARY KEY,
    consented_at     TEXT    NOT NULL,  -- ISO-8601 with timezone
    revoked_at       TEXT,              -- NULL means currently consented
    guardian_consent INTEGER NOT NULL DEFAULT 0,  -- 0 or 1
    guardian_id      TEXT                -- Optional guardian identifier
);

-- -------------------------------------------------------------------------
-- Sessions (R-005.1, R-005.2)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT    NOT NULL PRIMARY KEY,
    user_id         TEXT    NOT NULL,
    start_time      TEXT    NOT NULL,  -- ISO-8601 with timezone
    end_time        TEXT,              -- NULL while session is open
    status          TEXT    NOT NULL
        CHECK(status IN ('pending','in_progress','completed','interrupted')),
    completed_tasks TEXT    NOT NULL DEFAULT '[]'  -- JSON array of task_id strings
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- -------------------------------------------------------------------------
-- Trials — raw trial data per task result (R-005.1, R-001.3)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trials (
    id              INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    task_id         TEXT    NOT NULL,
    task_version    TEXT    NOT NULL,
    user_id         TEXT    NOT NULL,
    stimulus        TEXT    NOT NULL,
    expected        TEXT    NOT NULL,
    response        TEXT,              -- NULL = no response (omission)
    rt_ms           REAL    NOT NULL,
    timestamp_iso   TEXT    NOT NULL,
    valid           INTEGER NOT NULL,  -- 0 or 1
    invalid_reason  TEXT               -- 'anticipation'|'implausibly_fast'|'timeout'|NULL
);

CREATE INDEX IF NOT EXISTS idx_trials_session ON trials(session_id, task_id);

-- -------------------------------------------------------------------------
-- Task metrics — per (session_id, task_id) (R-005.1)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_metrics (
    session_id   TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    task_id      TEXT NOT NULL,
    metric_name  TEXT NOT NULL,
    metric_value REAL NOT NULL,
    PRIMARY KEY (session_id, task_id, metric_name)
);

-- -------------------------------------------------------------------------
-- Data quality — per (session_id, task_id) (R-005.1)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_quality (
    session_id         TEXT    NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    task_id            TEXT    NOT NULL,
    task_version       TEXT    NOT NULL,
    user_id            TEXT    NOT NULL,
    valid_trials       INTEGER NOT NULL,
    total_trials       INTEGER NOT NULL,
    completeness       REAL    NOT NULL,
    anomalies          TEXT    NOT NULL DEFAULT '[]',  -- JSON array of strings
    target_dimensions  TEXT    NOT NULL DEFAULT '[]',  -- JSON array of strings
    signals            TEXT    NOT NULL DEFAULT '[]',  -- JSON array of Signal objects
    uncertainty        REAL,  -- NULL allowed
    PRIMARY KEY (session_id, task_id)
);

-- -------------------------------------------------------------------------
-- Profiles — cognitive profile per user (R-006.2)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profiles (
    user_id      TEXT NOT NULL PRIMARY KEY,
    profile_json TEXT NOT NULL  -- CognitiveProfile serialised as JSON
);

-- -------------------------------------------------------------------------
-- Experience profiles — personalized onboarding data
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS experience_profiles (
    user_id         TEXT    NOT NULL PRIMARY KEY,
    age_group       TEXT    NOT NULL CHECK(age_group IN ('child_7_12','teen_13_17','young_adult_18_30','adult_31_60','senior_60_plus')),
    goals           TEXT    NOT NULL,  -- JSON array of strings
    tech_comfort    TEXT    NOT NULL CHECK(tech_comfort IN ('new','some_experience','comfortable','very_comfortable')),
    info_style      TEXT    NOT NULL CHECK(info_style IN ('visual','step_by_step','short_simple','detailed','conversational')),
    layout          TEXT    NOT NULL CHECK(layout IN ('guided_journey','dashboard','conversation_first','minimal')),
    theme           TEXT    NOT NULL CHECK(theme IN ('larger_text','standard','high_contrast','softer_colors','brighter_colors')),
    guidance_level  TEXT,              -- NULL allowed; CHECK(guidance_level IN ('more','some','minimal')) when present
    created_at      TEXT    NOT NULL,  -- ISO-8601 with timezone
    updated_at      TEXT    NOT NULL   -- ISO-8601 with timezone
);

-- -------------------------------------------------------------------------
-- IOI collaboration events
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS collaboration_events (
    event_id          TEXT NOT NULL PRIMARY KEY,
    user_id           TEXT NOT NULL,
    session_id        TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    component         TEXT NOT NULL,
    event_type        TEXT NOT NULL,
    opportunity_id    TEXT NOT NULL,
    behavior_observed INTEGER NOT NULL CHECK(behavior_observed IN (0, 1)),
    valid             INTEGER NOT NULL CHECK(valid IN (0, 1)),
    timestamp_iso     TEXT NOT NULL,
    schema_version    TEXT NOT NULL,
    metadata          TEXT NOT NULL DEFAULT '{}',
    UNIQUE(user_id, component, opportunity_id)
);

CREATE INDEX IF NOT EXISTS idx_collaboration_events_user
    ON collaboration_events(user_id, timestamp_iso);
CREATE INDEX IF NOT EXISTS idx_collaboration_events_session
    ON collaboration_events(session_id, timestamp_iso);

-- -------------------------------------------------------------------------
-- Daily plans — adaptive daily cognitive game selector
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_plans (
    user_id           TEXT    NOT NULL,
    plan_date         TEXT    NOT NULL,  -- YYYY-MM-DD
    session_id        TEXT,
    plan_json         TEXT    NOT NULL,  -- JSON serialized AdaptiveDailyPlan
    status            TEXT    NOT NULL CHECK(status IN ('generated', 'started', 'completed')),
    created_at        TEXT    NOT NULL,
    PRIMARY KEY (user_id, plan_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_plans_user ON daily_plans(user_id, plan_date);
CREATE INDEX IF NOT EXISTS idx_daily_plans_session ON daily_plans(session_id);

-- -------------------------------------------------------------------------
-- Coach conversations — multi-turn coaching interactions
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS coach_conversations (
    conversation_id TEXT NOT NULL PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES consent(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_coach_conversations_user ON coach_conversations(user_id, created_at);

CREATE TABLE IF NOT EXISTS coach_messages (
    message_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    timestamp_iso TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES coach_conversations(conversation_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_coach_messages_conversation ON coach_messages(conversation_id, timestamp_iso);
