import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/worker.mjs';
import { normalizeDeviceHeartbeat, collectorKeyMatches, ingestCollectorHeartbeat } from '../src/device-collector.mjs';

const now = Date.parse('2026-11-07T05:01:00Z');
const date = '2026-11-07';
const token = 'test-collector-token-example-long-enough';
const message = () => ({
  schema_version: 1, date, device_id: 'a4bc0020-16cc-4db5-9448-a709029b2017',
  app_version: '0.18.27', sent_at: '2026-11-07T05:00:59Z',
  program_received_at: '2026-11-07T05:00:50Z', race_count: 144,
  odds_attempted: 3, odds_succeeded: 2, odds_failed: 1,
  odds_last_attempt_at: '2026-11-07T05:00:55Z',
  odds_last_success_at: '2026-11-07T05:00:45Z',
});

test('accept only bounded device receipt metadata, never user values or forecast evidence', () => {
  const value = normalizeDeviceHeartbeat(message(), now);
  assert.equal(value.succeeded, 2);
  assert.equal(value.receivedMs, now);
  assert.equal(Object.keys(value).some(key => /odds_json|probabilit|forecast|amount/i.test(key)), false);
  assert.throws(() => normalizeDeviceHeartbeat({ ...message(), odds_succeeded: 4 }, now), /INVALID_SUCCEEDED/);
  assert.throws(() => normalizeDeviceHeartbeat({ ...message(), odds: { '1-2-3': 10 } }, now), /UNEXPECTED_FIELD/);
  assert.throws(() => normalizeDeviceHeartbeat({ ...message(), user_account: 'private' }, now), /UNEXPECTED_FIELD/);
  assert.throws(() => normalizeDeviceHeartbeat({ ...message(), odds_attempted: 2 }, now), /INVALID_ODDS_COUNTS/);
  assert.throws(() => normalizeDeviceHeartbeat({ ...message(), date: '2026-11-06' }, now), /INVALID_DATE/);
  assert.throws(() => normalizeDeviceHeartbeat({ ...message(), sent_at: '2026-11-07T03:00:00Z' }, now), /STALE_DEVICE_CLOCK/);
  assert.throws(() => normalizeDeviceHeartbeat({ ...message(), device_id: 'my-email@example.com' }, now), /INVALID_DEVICE_ID/);
  assert.equal(collectorKeyMatches(token, token), true);
  assert.equal(collectorKeyMatches(token + 'a', token), false);
  assert.equal(collectorKeyMatches('', token), false);
});

test('auth denied and disabled routes never attempt D1 writes', async () => {
  const db = { prepare: () => { throw new Error('DB_MUST_NOT_BE_USED'); } };
  const request = headers => new Request('https://example.net/v1/device-collector/heartbeat', {
    method: 'POST', headers: { 'content-type': 'application/json', ...headers }, body: JSON.stringify(message()),
  });
  assert.equal((await worker.fetch(request({}), { DB: db, COLLECTOR_INGEST_TOKEN: token })).status, 401);
  assert.equal((await worker.fetch(request({ authorization: `Bearer ${token}` }), { DB: db })).status, 503);
  assert.equal((await worker.fetch(new Request('https://example.net/v1/device-collector/heartbeat'), { DB: db })).status, 404);
});

test('authenticated heartbeat writes only receipt counts and returns non-forecast classification', async () => {
  let binds;
  const db = { prepare: sql => {
    assert.match(sql, /INSERT INTO collector_device_heartbeat/);
    return { bind: (...args) => { binds = args; return { run: async () => ({ success: true }) }; } };
  } };
  const req = new Request('https://example.net/v1/device-collector/heartbeat', {
    method: 'POST', headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
    body: JSON.stringify(message()),
  });
  const response = await ingestCollectorHeartbeat(req, { DB: db, COLLECTOR_INGEST_TOKEN: token }, now);
  assert.equal(response.status, 202);
  assert.equal(response.payload.classification, 'DEVICE_RECEIPT_ONLY');
  assert.equal(response.payload.eligible_for_forecast, false);
  assert.equal(binds.length, 12);
  assert.equal(binds[0], message().device_id);
  assert.equal(binds[7], 3);
});

test('public device status reports aggregate only; never leaks device identifier or token', async () => {
  const db = { prepare: () => ({ bind: dateArg => {
    assert.equal(dateArg, date);
    return { all: async () => ({ results: [{ received_ms: now, race_count: 144,
      odds_attempted: 3, odds_succeeded: 2, odds_failed: 1, odds_last_success_ms: now - 15_000 }] }) };
  } }) };
  const res = await worker.fetch(new Request(`https://example.net/v1/device-collector/status?date=${date}`), { DB: db });
  const result = await res.json();
  assert.equal(result.mode, 'DEVICE_RECEIPT_ONLY');
  assert.equal(result.eligible_for_forecast, false);
  assert.equal(result.latest_device_odds_succeeded, 2);
  assert.equal(JSON.stringify(result).includes('device_id'), false);
  assert.equal((await worker.fetch(new Request('https://example.net/v1/device-collector/status?date=no'), { DB: db })).status, 400);
});
