-- Additive result reconciliation state; preserves all existing settled results.
-- Legacy rows at result_stage=2 without a result remain eligible for retry.
ALTER TABLE race_schedule ADD COLUMN result_last_attempt_ms INTEGER;
ALTER TABLE race_schedule ADD COLUMN result_failure_code TEXT;
CREATE INDEX IF NOT EXISTS idx_result_reconciliation_date
  ON race_schedule (race_date, result_last_attempt_ms);
