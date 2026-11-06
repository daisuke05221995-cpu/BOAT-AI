-- Existing captured records remain, but cannot become READY without these
-- independently verified, pre-close source timestamps and identities.
ALTER TABLE race_schedule ADD COLUMN preview_source TEXT;
ALTER TABLE race_schedule ADD COLUMN preview_observed_ms INTEGER;
ALTER TABLE race_schedule ADD COLUMN odds_observed_ms INTEGER;
