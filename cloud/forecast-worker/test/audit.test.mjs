import test from 'node:test';
import assert from 'node:assert/strict';
import { summarizeDailyAudit } from '../src/audit.mjs';
import { runScheduled } from '../src/worker.mjs';

const now = Date.parse('2026-11-06T12:00:00Z');
const race = (id, extra = {}) => ({
  race_id: id, deadline_ms: now - 60_000, capture_stage: 2,
  captured_ms: null, preview_json: null, odds_json: null,
  forecast_json: null, model_version: null, decision: null,
  result_json: null, result_recorded_ms: null,
  ...extra,
});

test('audit counts only verified pre-close forecasts as BUY or SKIP', () => {
  const rows = [
    race('r1', { deadline_ms: now + 60_000, capture_stage: 0 }),
    race('r2', { preview_json: '{}', failure_code: 'ODDS_PROVIDER_NOT_CONFIGURED' }),
    race('r3', { preview_json: '{}', odds_json: '{}', captured_ms: now - 120_000,
      forecast_json: '{"combinations":[]}', model_version: 'model-a', decision: 'BUY' }),
    race('r4', { preview_json: '{}', odds_json: '{}', captured_ms: now - 120_000,
      forecast_json: '{"combinations":[]}', model_version: 'model-a', decision: 'SKIP' }),
    race('r5', { preview_json: '{}', odds_json: '{}', captured_ms: now + 1,
      forecast_json: '{"combinations":[]}', model_version: 'model-a', decision: 'BUY' }),
  ];
  const attempts = [
    { stage: 1, finished_ms: now - 90_000, failure_code: 'EXHIBITION_NOT_AVAILABLE' },
    { stage: 2, finished_ms: now - 60_000, failure_code: 'ODDS_PROVIDER_NOT_CONFIGURED' },
    { stage: 1, finished_ms: null, failure_code: null },
  ];
  const audit = summarizeDailyAudit('2026-11-06', now, rows, attempts, { race_count: 5 }, {
    last_started_ms: now - 1_000, last_completed_ms: now - 1_000,
    started_count: 100, completed_count: 99,
  });
  assert.equal(audit.scheduled_races, 5);
  assert.equal(audit.deadlines_passed, 4);
  assert.equal(audit.capture.t8_attempts, 2);
  assert.equal(audit.capture.t5_attempts, 1);
  assert.equal(audit.capture.running_attempts, 1);
  assert.equal(audit.capture.complete_observations, 2);
  assert.equal(audit.capture.forecasts_ready, 2);
  assert.equal(audit.capture.buy, 1);
  assert.equal(audit.capture.skip, 1);
  assert.equal(audit.capture.missed_after_deadline, 2);
  assert.equal(audit.capture.due_without_attempt, 1);
  assert.equal(audit.results.due, 0);
  assert.equal(audit.cron.status, 'ACTIVE');
  assert.equal(audit.capture_failure_codes.EXHIBITION_NOT_AVAILABLE, 1);
});

test('audit marks absent or delayed cron as unobserved or stale', () => {
  const empty = summarizeDailyAudit('2026-11-06', now);
  assert.equal(empty.cron.status, 'NOT_OBSERVED');
  const stale = summarizeDailyAudit('2026-11-06', now, [], [], null, {
    last_started_ms: now - 600_000, last_completed_ms: now - 600_000,
  });
  assert.equal(stale.cron.status, 'STALE');
});

test('cron execution records started and completed without making forecasts up', async () => {
  const statements = [];
  const env = { DB: { prepare(sql) {
    return { bind(...args) {
      return {
        first: async () => null,
        all: async () => ({ results: [] }),
        run: async () => { statements.push({ sql, args }); return { meta: { changes: 1 } }; },
      };
    } };
  } } };
  await runScheduled(env, Date.parse('2026-11-06T19:10:00Z')); // 04:10 JST, no upstream load
  assert.ok(statements.some(({ sql }) => sql.includes('INSERT INTO cron_heartbeat')));
  assert.ok(statements.some(({ sql }) => sql.includes('last_completed_ms')));
  assert.equal(statements.some(({ sql }) => sql.includes('forecast_json')), false);
});

test('late-night bootstrap batches a full 156-race timetable without backfilled forecasts', async () => {
  const nowMs = Date.parse('2026-11-06T21:00:00+09:00');
  const races = Object.fromEntries(Array.from({ length: 13 }, (_, venueIndex) => [String(venueIndex + 1), {
    races: Object.fromEntries(Array.from({ length: 12 }, (_, raceIndex) => [String(raceIndex + 1), {
      date: '2026-11-06', closed_at: `2026-11-06 ${String(9 + raceIndex).padStart(2, '0')}:30:00`,
    }])) },
  ]));
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ programs: { stadiums: races } }), { status: 200 });
  const batched = [], singleWrites = [];
  const env = { DB: {
    prepare(sql) { return { bind(...args) { return {
      sql, args,
      first: async () => null,
      all: async () => ({ results: [] }),
      run: async () => { singleWrites.push({ sql, args }); return { meta: { changes: 1 } }; },
    }; } }; },
    async batch(statements) { batched.push(statements); return statements.map(() => ({ meta: { changes: 1 } })); },
  } };
  try {
    await runScheduled(env, nowMs);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.deepEqual(batched.map(batch => batch.length), [48, 48, 48, 12]);
  assert.equal(batched.flat().filter(stmt => stmt.sql.includes('INSERT INTO race_schedule')).length, 156);
  assert.equal(singleWrites.some(stmt => stmt.sql.includes('UPDATE daily_import SET race_count') && stmt.args[0] === 156), true);
  assert.equal(singleWrites.some(stmt => stmt.sql.includes('forecast_json')), false);
});

test('simultaneous T-8 claims use D1 batch calls instead of per-race writes', async () => {
  const nowMs = Date.parse('2026-11-06T21:00:00+09:00');
  const due = Array.from({ length: 25 }, (_, i) => ({
    race_id: `2026-11-06-${String(1 + Math.floor(i / 12)).padStart(2, '0')}-${1 + i % 12}`,
    race_date: '2026-11-06', stadium_number: 1 + Math.floor(i / 12), race_number: 1 + i % 12,
    deadline_ms: nowMs + 7 * 60_000, capture_stage: 0,
  }));
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ programs: { stadiums: {} } }), { status: 200 });
  const batched = [];
  const env = { DB: {
    prepare(sql) { return { bind(...args) { return {
      sql, args,
      first: async () => ({ race_count: 156, last_attempt_ms: nowMs }),
      all: async () => ({ results: sql.includes('capture_stage < 2') ? due : [] }),
      run: async () => ({ meta: { changes: 1 } }),
    }; } }; },
    async batch(statements) { batched.push(statements); return statements.map(() => ({ meta: { changes: 1 } })); },
  } };
  try {
    await runScheduled(env, nowMs);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.deepEqual(batched.map(batch => batch.length), [25, 25, 50]);
  assert.equal(batched[2].filter(stmt => stmt.sql.includes('UPDATE race_schedule')).length, 25);
  assert.equal(batched[2].filter(stmt => stmt.sql.includes('UPDATE capture_attempt')).length, 25);
});
