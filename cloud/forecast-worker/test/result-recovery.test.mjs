import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { runScheduled } from '../src/worker.mjs';

function d1Sqlite() {
  const db = new DatabaseSync(':memory:');
  for (const n of ['0001_initial', '0002_operational_audit', '0003_preclose_provenance',
    '0004_model_a_history_generations', '0005_weather_provenance', '0006_result_reconciliation']) {
    db.exec(readFileSync(new URL(`../migrations/${n}.sql`, import.meta.url), 'utf8'));
  }
  const wrap = (statement, args) => ({
    first: async () => statement.get(...args) ?? null,
    all: async () => ({ results: statement.all(...args) }),
    run: async () => ({ meta: { changes: statement.run(...args).changes } }),
  });
  const D1 = {
    prepare(sql) { return { bind(...args) { return wrap(db.prepare(sql), args); } }; },
    async batch(statements) { return Promise.all(statements.map(stmt => stmt.run())); },
  };
  return { db, D1 };
}

test('cron recovers yesterday postponed and today unformed outcomes, then retries late final result', async () => {
  const { db, D1 } = d1Sqlite();
  const now = Date.parse('2026-11-07T08:10:00Z');
  const put = db.prepare(`INSERT INTO race_schedule
    (race_id, race_date, stadium_number, race_number, deadline_ms, result_stage, updated_ms)
    VALUES (?, ?, ?, ?, ?, ?, ?)`);
  put.run('2026-11-06-08-1', '2026-11-06', 8, 1, Date.parse('2026-11-06T01:00:00Z'), 2, now);
  put.run('2026-11-07-03-2', '2026-11-07', 3, 2, Date.parse('2026-11-07T02:25:00Z'), 2, now);
  put.run('2026-11-07-12-3', '2026-11-07', 12, 3, Date.parse('2026-11-07T07:27:00Z'), 1, now);
  db.prepare(`INSERT INTO daily_import (race_date,last_attempt_ms,last_success_ms,race_count)
    VALUES ('2026-11-07', ?, ?, 132)`).run(now, now);

  const id = (date, stadium, race) => ({ date, stadium_number: stadium, race_number: race });
  const sourceResult = (stadium, race, trifecta) => ({ ...id('2026-11-07', stadium, race),
    result: { ...id('2026-11-07', stadium, race), payouts: { trifecta } } });
  let latePublished = false;
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async url => {
    calls.push(String(url));
    const yesterday = String(url).includes('20261106.json');
    const feed = yesterday ? { programs: { stadiums: { 8: { races: { 1: {
      ...id('2026-11-06', 8, 1), day_number_source: '順延',
      result: { ...id('2026-11-06', 8, 1), payouts: { trifecta: [] } },
    } } } } } } : { programs: { stadiums: {
      3: { races: { 2: sourceResult(3, 2, [{ combination: null, amount: 100, label: '不成立' }]) } },
      12: { races: { 3: latePublished ? sourceResult(12, 3,
        [{ combination: '1-3-6', amount: 1820 }]) : { ...id('2026-11-07', 12, 3) } } },
    } } };
    return new Response(JSON.stringify(feed), { status: 200 });
  };
  try {
    await runScheduled({ DB: D1 }, now);
    const read = key => db.prepare('SELECT * FROM race_schedule WHERE race_id=?').get(key);
    assert.equal(JSON.parse(read('2026-11-06-08-1').result_json).status, 'POSTPONED');
    assert.equal(JSON.parse(read('2026-11-07-03-2').result_json).status, 'UNFORMED');
    assert.equal(read('2026-11-07-12-3').result_json, null);
    assert.equal(read('2026-11-07-12-3').result_failure_code, 'RESULT_NOT_FINAL');
    assert.equal(calls.length, 2); // one source request per day, not per race

    latePublished = true;
    await runScheduled({ DB: D1 }, now + 5 * 60_000);
    assert.equal(calls.length, 2); // backoff prevents flood
    await runScheduled({ DB: D1 }, now + 16 * 60_000);
    assert.equal(calls.length, 3);
    assert.equal(JSON.parse(read('2026-11-07-12-3').result_json).trifecta_payout, 1820);
    assert.equal(read('2026-11-07-12-3').result_failure_code, null);
    assert.equal(read('2026-11-07-12-3').result_stage, 2);
    assert.equal(db.prepare('SELECT COUNT(*) AS n FROM race_schedule WHERE forecast_json IS NOT NULL').get().n, 0);
  } finally {
    globalThis.fetch = original;
    db.close();
  }
});
