-- Diagnostic-only last heartbeat per paired Android device.
-- No odds values, exhibition payloads, account IDs or BUY/SKIP are stored.
CREATE TABLE IF NOT EXISTS collector_device_heartbeat (
  device_id TEXT PRIMARY KEY,
  race_date TEXT NOT NULL,
  device_sent_ms INTEGER NOT NULL,
  received_ms INTEGER NOT NULL,
  app_version TEXT NOT NULL,
  program_received_ms INTEGER,
  race_count INTEGER NOT NULL CHECK(race_count BETWEEN 0 AND 288),
  odds_attempted INTEGER NOT NULL CHECK(odds_attempted >= 0),
  odds_succeeded INTEGER NOT NULL CHECK(odds_succeeded >= 0),
  odds_failed INTEGER NOT NULL CHECK(odds_failed >= 0),
  odds_last_attempt_ms INTEGER,
  odds_last_success_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_collector_heartbeat_date
  ON collector_device_heartbeat(race_date, received_ms DESC);
