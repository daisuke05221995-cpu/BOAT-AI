import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';

const migration = readFileSync(new URL('../migrations/0001_initial.sql', import.meta.url), 'utf8');
const auditMigration = readFileSync(new URL('../migrations/0002_operational_audit.sql', import.meta.url), 'utf8');
const provenanceMigration = readFileSync(new URL('../migrations/0003_preclose_provenance.sql', import.meta.url), 'utf8');

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
