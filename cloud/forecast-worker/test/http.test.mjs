import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/worker.mjs';

test('health route is read-only and excludes internal tokens', async () => {
  const res = await worker.fetch(new Request('https://example.net/v1/health'), {});
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { ok: true, service: 'boat-ai-cloud', schema_version: 1 });
  assert.equal(res.headers.get('cache-control'), 'no-store');
});

test('invalid dates, unknown routes and writes fail closed', async () => {
  assert.equal((await worker.fetch(new Request('https://example.net/v1/forecasts?date=2026-02-30'), {})).status, 400);
  assert.equal((await worker.fetch(new Request('https://example.net/v1/private'), {})).status, 404);
  assert.equal((await worker.fetch(new Request('https://example.net/v1/health', { method: 'POST' }), {})).status, 405);
});

test('forecast listing returns a versioned empty schedule without making one up', async () => {
  const db = { prepare: sql => ({ bind: date => ({ all: async () => {
    assert.match(sql, /SELECT \* FROM race_schedule/);
    assert.equal(date, '2026-11-06');
    return { results: [] };
  } }) }) };
  const res = await worker.fetch(new Request('https://example.net/v1/forecasts?date=2026-11-06'), { DB: db });
  const payload = await res.json();
  assert.equal(payload.schema_version, 1);
  assert.equal(payload.date, '2026-11-06');
  assert.deepEqual(payload.races, []);
});

test('audit route is read-only, date validated, and does not disclose row-level data', async () => {
  const db = { prepare: sql => ({ bind: date => ({
    all: async () => {
      assert.equal(date, '2026-11-06');
      return { results: sql.includes('capture_attempt') ? [] : [{
        race_id: '2026-11-06-01-1', deadline_ms: Date.parse('2026-11-06T09:00:00Z'),
        capture_stage: 2, failure_code: 'ODDS_PROVIDER_NOT_CONFIGURED',
      }] };
    },
    first: async () => null,
  }) }) };
  const res = await worker.fetch(new Request('https://example.net/v1/audit?date=2026-11-06'), { DB: db });
  assert.equal(res.status, 200);
  const audit = await res.json();
  assert.equal(audit.scheduled_races, 1);
  assert.equal(audit.capture.forecasts_ready, 0);
  assert.equal(audit.program_roster_candidate.not_checked, 1);
  assert.equal(audit.program_roster_candidate.eligible_for_forecast, 0);
  assert.equal(audit.import.count, 0);
  assert.equal(JSON.stringify(audit).includes('race_id'), false);
  assert.equal((await worker.fetch(new Request('https://example.net/v1/audit?date=2026-11-31'), { DB: db })).status, 400);
  assert.equal((await worker.fetch(new Request('https://example.net/v1/audit?date=2026-11-06', { method: 'POST' }), { DB: db })).status, 405);
});
