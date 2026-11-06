-- Additive operational audit. Existing race forecasts and purchases are untouched.
CREATE TABLE IF NOT EXISTS cron_heartbeat (
  race_date TEXT PRIMARY KEY,
  last_started_ms INTEGER NOT NULL,
  last_completed_ms INTEGER,
  started_count INTEGER NOT NULL DEFAULT 0,
  completed_count INTEGER NOT NULL DEFAULT 0,
  last_error_code TEXT
);

CREATE TABLE IF NOT EXISTS capture_attempt (
  race_id TEXT NOT NULL,
  stage INTEGER NOT NULL CHECK (stage IN (1, 2)),
  started_ms INTEGER NOT NULL,
  finished_ms INTEGER,
  completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
  failure_code TEXT,
  PRIMARY KEY (race_id, stage),
  FOREIGN KEY (race_id) REFERENCES race_schedule(race_id)
);

CREATE INDEX IF NOT EXISTS idx_capture_attempt_started ON capture_attempt(started_ms);
