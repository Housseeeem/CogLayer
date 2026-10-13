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
--
-- No triggers: timestamps are set explicitly in Python for determinism.
-- No utcnow(): Python always stores ISO-8601 strings with UTC offset.

-- -------------------------------------------------------------------------
-- Consent (R-001.1, R-001.4)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consent (
    user_id      TEXT    NOT NULL PRIMARY KEY,
    consented_at TEXT    NOT NULL,  -- ISO-8601 with timezone
    revoked_at   TEXT              -- NULL means currently consented
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
