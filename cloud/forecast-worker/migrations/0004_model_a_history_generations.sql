-- Immutable, checksum-addressed Model A history generations. This migration
-- does not replace the original Android asset or activate any prediction.
-- D1's row limit is 2 MB; each base64 chunk holds at most 512 KiB raw bytes.
CREATE TABLE IF NOT EXISTS model_a_history_generation (
  sha256 TEXT PRIMARY KEY CHECK (length(sha256) = 64),
  previous_sha256 TEXT,
  kind TEXT NOT NULL CHECK (kind IN ('FROZEN_BASE', 'RECONCILED_DAY')),
  through_day INTEGER NOT NULL CHECK (through_day > 0),
  update_races INTEGER NOT NULL CHECK (update_races >= 0),
  byte_length INTEGER NOT NULL CHECK (byte_length > 0),
  chunk_count INTEGER NOT NULL CHECK (chunk_count > 0),
  audit_json TEXT NOT NULL,
  audit_sha256 TEXT NOT NULL CHECK (length(audit_sha256) = 64),
  staged_ms INTEGER NOT NULL,
  FOREIGN KEY (previous_sha256) REFERENCES model_a_history_generation(sha256)
);

CREATE TABLE IF NOT EXISTS model_a_history_chunk (
  sha256 TEXT NOT NULL REFERENCES model_a_history_generation(sha256),
  chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
  chunk_sha256 TEXT NOT NULL CHECK (length(chunk_sha256) = 64),
  base64_data TEXT NOT NULL,
  PRIMARY KEY (sha256, chunk_index)
);

CREATE TABLE IF NOT EXISTS model_a_history_active (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  sha256 TEXT NOT NULL REFERENCES model_a_history_generation(sha256),
  through_day INTEGER NOT NULL CHECK (through_day > 0),
  activated_ms INTEGER NOT NULL
);
