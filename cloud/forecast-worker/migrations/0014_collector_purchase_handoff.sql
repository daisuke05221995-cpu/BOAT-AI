-- A short-lived, non-executing transfer of proposed tickets between paired Android devices.
-- This table never stores login credentials or submits wagers.
CREATE TABLE IF NOT EXISTS collector_purchase_handoff (
  handoff_id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL,
  session_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PENDING', 'DELIVERED', 'EXPIRED')),
  requested_ms INTEGER NOT NULL,
  expires_ms INTEGER NOT NULL,
  delivered_ms INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS collector_purchase_handoff_pending_device
  ON collector_purchase_handoff(device_id) WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS collector_purchase_handoff_expiry
  ON collector_purchase_handoff(status, expires_ms);
