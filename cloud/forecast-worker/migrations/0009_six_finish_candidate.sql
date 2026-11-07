-- Results-side diagnostic only; no national coverage or Model A history certification.
CREATE TABLE IF NOT EXISTS six_finish_candidate (
  race_id TEXT PRIMARY KEY REFERENCES race_schedule(race_id),
  checked_ms INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('SHAPE_ONLY_UNVERIFIED', 'UNAVAILABLE', 'NON_SETTLED')),
  failure_code TEXT,
  candidate_json TEXT,
  source TEXT NOT NULL DEFAULT 'PROGRAM_RESULT_FEED_UNVERIFIED',
  CHECK ((status = 'SHAPE_ONLY_UNVERIFIED' AND candidate_json IS NOT NULL AND failure_code IS NULL)
      OR (status = 'UNAVAILABLE' AND candidate_json IS NULL AND failure_code IS NOT NULL)
      OR (status = 'NON_SETTLED' AND candidate_json IS NULL AND failure_code IS NULL))
);
