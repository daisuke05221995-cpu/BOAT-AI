-- Non-authoritative program roster shape/coverage snapshots only.
-- Never use this table for real pre-close predictions or as a licensed feed.
CREATE TABLE IF NOT EXISTS program_roster_candidate (
  race_id TEXT PRIMARY KEY REFERENCES race_schedule(race_id),
  checked_ms INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('SHAPE_ONLY_UNVERIFIED', 'UNAVAILABLE')),
  failure_code TEXT,
  candidate_json TEXT,
  source TEXT NOT NULL DEFAULT 'PROGRAM_FEED_UNVERIFIED',
  CHECK ((status = 'SHAPE_ONLY_UNVERIFIED' AND candidate_json IS NOT NULL AND failure_code IS NULL)
      OR (status = 'UNAVAILABLE' AND candidate_json IS NULL AND failure_code IS NOT NULL))
);
