-- Dormant immutable Model A text assets. Never activates BUY/SKIP or changes
-- personal purchases, existing history generations, or the frozen models.
CREATE TABLE IF NOT EXISTS model_a_frozen_bundle (
  bundle_sha256 TEXT PRIMARY KEY CHECK (length(bundle_sha256) = 64),
  stage_manifest_json TEXT NOT NULL,
  staged_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS model_a_frozen_chunk (
  bundle_sha256 TEXT NOT NULL REFERENCES model_a_frozen_bundle(bundle_sha256),
  stage_index INTEGER NOT NULL CHECK (stage_index BETWEEN 0 AND 2),
  chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
  chunk_sha256 TEXT NOT NULL CHECK (length(chunk_sha256) = 64),
  base64_data TEXT NOT NULL,
  PRIMARY KEY (bundle_sha256, stage_index, chunk_index)
);
