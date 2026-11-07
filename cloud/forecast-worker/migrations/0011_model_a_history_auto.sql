-- One immutable daily promotion attempt at a time. Missing source or bad
-- national coverage never changes the active Model A history pointer.
CREATE TABLE IF NOT EXISTS model_a_history_day_attempt (
  race_date TEXT PRIMARY KEY,
  last_started_ms INTEGER NOT NULL,
  last_finished_ms INTEGER,
  status TEXT NOT NULL CHECK (status IN ('RUNNING', 'UNAVAILABLE', 'PROMOTED')),
  reason TEXT,
  promoted_sha256 TEXT,
  expected_races INTEGER,
  committed_races INTEGER,
  CHECK ((status = 'PROMOTED' AND length(promoted_sha256) = 64 AND
    expected_races BETWEEN 1 AND 288 AND committed_races BETWEEN 0 AND expected_races AND reason IS NULL)
    OR (status != 'PROMOTED' AND promoted_sha256 IS NULL))
);
