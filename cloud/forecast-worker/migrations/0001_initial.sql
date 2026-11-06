CREATE TABLE IF NOT EXISTS race_schedule (
  race_id TEXT PRIMARY KEY,
  race_date TEXT NOT NULL,
  stadium_number INTEGER NOT NULL,
  race_number INTEGER NOT NULL,
  deadline_ms INTEGER NOT NULL,
  capture_stage INTEGER NOT NULL DEFAULT 0 CHECK (capture_stage BETWEEN 0 AND 2),
  capture_started_ms INTEGER,
  captured_ms INTEGER,
  preview_json TEXT,
  odds_json TEXT,
  odds_source TEXT,
  forecast_json TEXT,
  model_version TEXT,
  decision TEXT CHECK (decision IS NULL OR decision IN ('BUY','SKIP')),
  failure_code TEXT,
  result_json TEXT,
  result_recorded_ms INTEGER,
  result_stage INTEGER NOT NULL DEFAULT 0 CHECK (result_stage BETWEEN 0 AND 2),
  updated_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_race_schedule_date ON race_schedule(race_date);
CREATE INDEX IF NOT EXISTS idx_race_schedule_deadline ON race_schedule(deadline_ms, capture_stage);

CREATE TABLE IF NOT EXISTS daily_import (
  race_date TEXT PRIMARY KEY,
  last_attempt_ms INTEGER NOT NULL,
  last_success_ms INTEGER,
  race_count INTEGER NOT NULL DEFAULT 0,
  failure_code TEXT
);
