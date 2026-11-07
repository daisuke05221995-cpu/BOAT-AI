-- Immutable, non-purchasing shadow forecasts. Never read this table as BUY/SKIP.
CREATE TABLE IF NOT EXISTS model_a_shadow_attempt (
  race_id TEXT NOT NULL REFERENCES race_schedule(race_id),
  capture_stage INTEGER NOT NULL CHECK (capture_stage IN (1, 2)),
  checked_ms INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('UNAVAILABLE', 'FORECAST_ONLY')),
  reason TEXT,
  history_sha256 TEXT,
  model_bundle_sha256 TEXT,
  source_provenance_json TEXT,
  probabilities_json TEXT,
  PRIMARY KEY (race_id, capture_stage),
  CHECK ((status = 'FORECAST_ONLY' AND reason IS NULL AND
    length(history_sha256) = 64 AND length(model_bundle_sha256) = 64 AND
    source_provenance_json IS NOT NULL AND probabilities_json IS NOT NULL) OR
    (status = 'UNAVAILABLE' AND reason IS NOT NULL AND probabilities_json IS NULL))
);
CREATE INDEX IF NOT EXISTS idx_model_a_shadow_status ON model_a_shadow_attempt(status, checked_ms);
