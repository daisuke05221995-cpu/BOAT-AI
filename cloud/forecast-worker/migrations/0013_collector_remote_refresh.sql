-- Explicitly scoped remote refresh for a single active collection Android.
-- No screen access, input injection, account credentials or bet-related actions.
CREATE TABLE IF NOT EXISTS collector_remote_refresh (
  command_id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL,
  action TEXT NOT NULL CHECK(action = 'REFRESH_NOW'),
  status TEXT NOT NULL CHECK(status IN ('PENDING', 'ACCEPTED', 'EXPIRED')),
  requested_ms INTEGER NOT NULL,
  expires_ms INTEGER NOT NULL,
  accepted_ms INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_collector_remote_one_pending
  ON collector_remote_refresh(device_id) WHERE status='PENDING';
CREATE INDEX IF NOT EXISTS idx_collector_remote_device_history
  ON collector_remote_refresh(device_id, requested_ms DESC);
