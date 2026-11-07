import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';

const migration = readFileSync(new URL('../migrations/0001_initial.sql', import.meta.url), 'utf8');
const auditMigration = readFileSync(new URL('../migrations/0002_operational_audit.sql', import.meta.url), 'utf8');
const provenanceMigration = readFileSync(new URL('../migrations/0003_preclose_provenance.sql', import.meta.url), 'utf8');
const historyMigration = readFileSync(new URL('../migrations/0004_model_a_history_generations.sql', import.meta.url), 'utf8');
const weatherMigration = readFileSync(new URL('../migrations/0005_weather_provenance.sql', import.meta.url), 'utf8');
const resultMigration = readFileSync(new URL('../migrations/0006_result_reconciliation.sql', import.meta.url), 'utf8');
const modelAssetMigration = readFileSync(new URL('../migrations/0007_model_a_frozen_assets.sql', import.meta.url), 'utf8');
const rosterMigration = readFileSync(new URL('../migrations/0008_program_roster_candidate.sql', import.meta.url), 'utf8');

test('D1 SQLite migration accepts actual race inserts, rejects duplicate loss', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(migration);
  const insert = db.prepare(`INSERT INTO race_schedule
    (race_id, race_date, stadium_number, race_number, deadline_ms, updated_ms)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(race_id) DO UPDATE SET deadline_ms=excluded.deadline_ms, updated_ms=excluded.updated_ms
    WHERE race_schedule.capture_stage = 0 AND race_schedule.capture_started_ms IS NULL`);
  insert.run('2026-11-06-01-1', '2026-11-06', 1, 1, 100_000, 1);
  db.prepare('UPDATE race_schedule SET capture_stage=1, capture_started_ms=2 WHERE race_id=?').run('2026-11-06-01-1');
  insert.run('2026-11-06-01-1', '2026-11-06', 1, 1, 120_000, 3);
  assert.equal(db.prepare('SELECT deadline_ms FROM race_schedule').get().deadline_ms, 100_000);
  assert.throws(() => db.prepare('UPDATE race_schedule SET decision=?').run('MISSING_ODDS'));
  db.close();
});

test('atomic capture claim avoids duplicate cron execution', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(migration);
  db.prepare(`INSERT INTO race_schedule
    (race_id, race_date, stadium_number, race_number, deadline_ms, updated_ms)
    VALUES ('2026-11-06-01-1', '2026-11-06', 1, 1, 100000, 0)`).run();
  const claim = db.prepare(`UPDATE race_schedule SET capture_stage=?, capture_started_ms=?, updated_ms=?
    WHERE race_id=? AND capture_stage=? AND deadline_ms > ?`);
  assert.equal(claim.run(1, 90_000, 90_000, '2026-11-06-01-1', 0, 90_000).changes, 1);
  assert.equal(claim.run(1, 90_000, 90_000, '2026-11-06-01-1', 0, 90_000).changes, 0);
  assert.equal(claim.run(2, 95_000, 95_000, '2026-11-06-01-1', 1, 95_000).changes, 1);
  assert.equal(claim.run(2, 95_000, 95_000, '2026-11-06-01-1', 1, 95_000).changes, 0);
  assert.equal(claim.run(2, 100_000, 100_000, '2026-11-06-01-1', 1, 100_000).changes, 0);
  db.close();
});

test('audit migration preserves existing races, tracks one attempt per stage, and counts cron runs', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(migration);
  db.prepare(`INSERT INTO race_schedule
    (race_id, race_date, stadium_number, race_number, deadline_ms, updated_ms)
    VALUES ('2026-11-06-01-1', '2026-11-06', 1, 1, 100000, 0)`).run();
  db.exec(auditMigration);
  db.exec(auditMigration);
  db.prepare(`INSERT INTO capture_attempt (race_id, stage, started_ms)
    VALUES ('2026-11-06-01-1', 1, 90000)`).run();
  assert.throws(() => db.prepare(`INSERT INTO capture_attempt (race_id, stage, started_ms)
    VALUES ('2026-11-06-01-1', 1, 90001)`).run());
  db.prepare(`INSERT INTO capture_attempt (race_id, stage, started_ms)
    VALUES ('2026-11-06-01-1', 2, 95000)`).run();
  db.prepare(`INSERT INTO cron_heartbeat (race_date, last_started_ms, started_count)
    VALUES ('2026-11-06', 90000, 1)`).run();
  assert.equal(db.prepare('SELECT COUNT(*) AS count FROM capture_attempt').get().count, 2);
  assert.equal(db.prepare('SELECT started_count FROM cron_heartbeat').get().started_count, 1);
  assert.equal(db.prepare('SELECT deadline_ms FROM race_schedule').get().deadline_ms, 100000);
  db.close();
});

test('strict pre-close provenance migration preserves existing capture and adds source timestamps', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(migration);
  db.prepare(`INSERT INTO race_schedule
    (race_id, race_date, stadium_number, race_number, deadline_ms, updated_ms)
    VALUES ('2026-11-06-01-1', '2026-11-06', 1, 1, 100000, 0)`).run();
  db.exec(auditMigration);
  db.exec(provenanceMigration);
  const row = db.prepare('SELECT * FROM race_schedule').get();
  assert.equal(row.race_id, '2026-11-06-01-1');
  assert.equal(row.preview_source, null);
  assert.equal(row.preview_observed_ms, null);
  assert.equal(row.odds_observed_ms, null);
  db.prepare(`UPDATE race_schedule SET preview_source='licensed-provider',
    preview_observed_ms=90000, odds_observed_ms=92000 WHERE race_id='2026-11-06-01-1'`).run();
  assert.equal(db.prepare('SELECT odds_observed_ms FROM race_schedule').get().odds_observed_ms, 92000);
  db.close();
});

test('immutable history checkpoint migration preserves existing forecast and result records', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(migration);
  db.exec(auditMigration);
  db.exec(provenanceMigration);
  db.prepare(`INSERT INTO race_schedule
    (race_id, race_date, stadium_number, race_number, deadline_ms, updated_ms, result_json)
    VALUES ('2026-11-06-01-1', '2026-11-06', 1, 1, 100000, 0, '{"trifecta_combination":"1-2-3"}')`).run();
  db.exec(historyMigration);
  db.exec(historyMigration);
  const row = db.prepare('SELECT result_json FROM race_schedule').get();
  assert.deepEqual(JSON.parse(row.result_json), { trifecta_combination: '1-2-3' });
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM model_a_history_active').get().n, 0);
  db.close();
});

test('field-level weather provenance migration leaves old captures unverified, never invents timestamps', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(migration);
  db.exec(auditMigration);
  db.exec(provenanceMigration);
  db.prepare(`INSERT INTO race_schedule
    (race_id, race_date, stadium_number, race_number, deadline_ms, updated_ms, preview_observed_ms)
    VALUES ('2026-11-06-01-1', '2026-11-06', 1, 1, 100000, 0, 90000)`).run();
  db.exec(weatherMigration);
  const row = db.prepare('SELECT preview_observed_ms, weather_observed_ms, weather_source FROM race_schedule').get();
  assert.equal(row.preview_observed_ms, 90000);
  assert.equal(row.weather_observed_ms, null);
  assert.equal(row.weather_source, null);
  db.close();
});

test('result reconciliation migration preserves final results and makes exhausted legacy results retryable', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(migration);
  db.exec(auditMigration);
  db.exec(provenanceMigration);
  db.exec(weatherMigration);
  db.prepare(`INSERT INTO race_schedule
    (race_id, race_date, stadium_number, race_number, deadline_ms, updated_ms, result_stage)
    VALUES ('2026-11-06-08-1', '2026-11-06', 8, 1, 100000, 0, 2)`).run();
  db.exec(resultMigration);
  const row = db.prepare('SELECT * FROM race_schedule').get();
  assert.equal(row.result_stage, 2);
  assert.equal(row.result_json, null);
  assert.equal(row.result_last_attempt_ms, null);
  assert.equal(row.result_failure_code, null);
  db.prepare('UPDATE race_schedule SET result_last_attempt_ms=120000 WHERE race_id=?').run(row.race_id);
  assert.equal(db.prepare('SELECT result_last_attempt_ms FROM race_schedule').get().result_last_attempt_ms, 120000);
  db.close();
});

test('frozen Model A asset migration preserves results and does not enable production models', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(migration);
  db.exec(auditMigration);
  db.exec(provenanceMigration);
  db.exec(weatherMigration);
  db.exec(resultMigration);
  db.prepare(`INSERT INTO race_schedule
    (race_id, race_date, stadium_number, race_number, deadline_ms, updated_ms, result_json)
    VALUES ('2026-11-07-01-1', '2026-11-07', 1, 1, 100000, 0, '{"status":"SETTLED"}')`).run();
  db.exec(modelAssetMigration);
  assert.equal(db.prepare('SELECT result_json FROM race_schedule').get().result_json, '{"status":"SETTLED"}');
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM model_a_frozen_bundle').get().n, 0);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM model_a_frozen_chunk').get().n, 0);
  db.close();
});

test('diagnostic program roster snapshot migration never mutates a race forecast or result', () => {
  const db = new DatabaseSync(':memory:');
  db.exec(migration);
  db.prepare(`INSERT INTO race_schedule
    (race_id, race_date, stadium_number, race_number, deadline_ms, updated_ms, result_json)
    VALUES ('2026-11-07-01-1', '2026-11-07', 1, 1, 100000, 0, '{"status":"SETTLED"}')`).run();
  db.exec(rosterMigration);
  db.exec(rosterMigration);
  db.prepare(`INSERT INTO program_roster_candidate (race_id, checked_ms, status, candidate_json)
    VALUES ('2026-11-07-01-1', 90000, 'SHAPE_ONLY_UNVERIFIED', '{"racers":[]}')`).run();
  assert.equal(db.prepare('SELECT result_json FROM race_schedule').get().result_json, '{"status":"SETTLED"}');
  assert.equal(db.prepare('SELECT decision FROM race_schedule').get().decision, null);
  assert.throws(() => db.prepare(`INSERT INTO program_roster_candidate
    (race_id, checked_ms, status, candidate_json)
    VALUES ('missing-race', 90000, 'SHAPE_ONLY_UNVERIFIED', '{}')`).run());
  assert.throws(() => db.prepare(`UPDATE program_roster_candidate SET status='SHAPE_ONLY_UNVERIFIED', candidate_json=NULL`).run());
  db.close();
});
