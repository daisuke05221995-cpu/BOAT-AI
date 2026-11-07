import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { stagePurchaseHandoff, nextPurchaseHandoff, acknowledgePurchaseHandoff } from '../src/collector-purchase-handoff.mjs';

const token = 'this-is-a-test-token-with-more-than-32-characters';
const deviceId = 'a4bc0020-16cc-4db5-9448-a709029b2017';
const now = Date.parse('2026-11-08T05:00:00Z');
const root = 'https://boat.example/v1/device-collector/purchase-handoff';
const auth = { authorization: `Bearer ${token}`, 'content-type': 'application/json' };
const request = (path, body, headers = auth) => new Request(root + path, {
  method: 'POST', headers, body: JSON.stringify(body),
});
const session = {
  id: '239dbb72-a154-4d5b-93ca-fda75d1a05c9', createdAt: now,
  races: [{ raceId: '2026-11-08-01-1', date: '2026-11-08', stadiumNumber: 1,
    raceNumber: 1, venueName: '桐生', recommended: true,
    tickets: [{ combination: '1-3-5', amount: 500 }] }],
  selectedRaceIds: ['2026-11-08-01-1'],
};

function fakeDb(active = true) {
  const sql = new DatabaseSync(':memory:');
  sql.exec(readFileSync(new URL('../migrations/0001_initial.sql', import.meta.url), 'utf8'));
  sql.exec(readFileSync(new URL('../migrations/0012_device_collector_heartbeat.sql', import.meta.url), 'utf8'));
  sql.exec(readFileSync(new URL('../migrations/0014_collector_purchase_handoff.sql', import.meta.url), 'utf8'));
  if (active) sql.prepare(`INSERT INTO collector_device_heartbeat
    (device_id, race_date, device_sent_ms, received_ms, app_version, race_count, odds_attempted, odds_succeeded, odds_failed)
    VALUES (?, '2026-11-08', ?, ?, '0.18.30', 1, 0, 0, 0)`)
    .run(deviceId, now, now);
  return { DB: { prepare(query) {
    const statement = sql.prepare(query);
    return { bind(...args) {
      const bound = args;
      return { async first() { return statement.get(...bound) ?? null; },
        async run() { return statement.run(...bound); } };
    } };
  } }, COLLECTOR_INGEST_TOKEN: token, close: () => sql.close() };
}

test('handoff requires auth, validates picks, and never submits a wager', async () => {
  const env = fakeDb();
  try {
    assert.equal((await stagePurchaseHandoff(request('/stage', { schema_version: 1, session },
      { 'content-type': 'application/json' }), env, now)).status, 401);
    const invalid = { ...session, races: [{ ...session.races[0], tickets: [{ combination: '1-1-1', amount: 100 }] }] };
    assert.equal((await stagePurchaseHandoff(request('/stage', { schema_version: 1, session: invalid }), env, now)).status, 400);
    const past = { ...session, races: [{ ...session.races[0], date: '2026-11-07' }] };
    assert.equal((await stagePurchaseHandoff(request('/stage', { schema_version: 1, session: past }), env, now)).status, 400);
    const leaked = { ...session, secret: 'never-store-this' };
    assert.equal((await stagePurchaseHandoff(request('/stage', { schema_version: 1, session: leaked }), env, now)).status, 400);
    assert.equal((await stagePurchaseHandoff(request('/stage', { schema_version: 1, session, action: 'BET' }), env, now)).status, 400);
    assert.equal((await nextPurchaseHandoff(new Request(root + `/next?device_id=${deviceId}`), env, now)).status, 401);
  } finally { env.close(); }
});

test('paired phone can retrieve and acknowledge one proposal; expiry prevents delivery', async () => {
  const env = fakeDb();
  try {
    const staged = await stagePurchaseHandoff(request('/stage', { schema_version: 1, session }), env, now);
    assert.equal(staged.status, 202);
    assert.equal(staged.payload.staged, true);
    assert.equal((await stagePurchaseHandoff(request('/stage', { schema_version: 1, session }), env, now + 5_000)).status, 409);
    const next = await nextPurchaseHandoff(new Request(root + `/next?device_id=${deviceId}`, { headers: auth }), env, now + 5_000);
    assert.equal(next.status, 200);
    assert.deepEqual(next.payload.session, session);
    const ack = await acknowledgePurchaseHandoff(request('/ack', { schema_version: 1,
      device_id: deviceId, handoff_id: staged.payload.handoff_id }), env, now + 10_000);
    assert.equal(ack.status, 202);
    assert.equal((await nextPurchaseHandoff(new Request(root + `/next?device_id=${deviceId}`, { headers: auth }), env, now + 12_000)).payload.session, null);
  } finally { env.close(); }

  const offline = fakeDb(false);
  try {
    assert.equal((await stagePurchaseHandoff(request('/stage', { schema_version: 1, session }), offline, now)).status, 409);
  } finally { offline.close(); }
});
