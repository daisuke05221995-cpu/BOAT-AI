-- Additive field-level provenance. Existing captures remain unverified until
-- a new, actually observed weather snapshot is saved; no timestamps backfilled.
ALTER TABLE race_schedule ADD COLUMN weather_source TEXT;
ALTER TABLE race_schedule ADD COLUMN weather_observed_ms INTEGER;
