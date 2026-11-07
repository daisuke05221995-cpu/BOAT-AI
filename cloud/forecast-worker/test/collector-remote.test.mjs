import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/worker.mjs';
import { requestRemoteRefresh, pollRemoteRefresh, acknowledgeRemoteRefresh } from '../src/collector-remote.mjs';

const token = 'this-is-a-test-token-with-more-than-32-characters';
const deviceId = 'a4bc0020-16cc-4db5-9448-a709029b2017';
const now = Date.parse('2026-11-08T04:00:00Z');
const root = 'https://boat.example/v1/device-collector/remote';
const headers = { authorization: `Bearer ${token}`, 'content-type': 'application/json' };
const jsonRequest = (path, body, bearer = headers) => new Request(root + path, {
  method: 'POST', headers: bearer, body: JSON.stringify(body),
});

function fakeDb(active = true) {
  const state = { commands: [], device: active ? { device_id: deviceId } : null };
  const db = { prepare(sql) {
    let params = [];
    return {
      bind(...args) { params = args; return this; },
      async first() {
        if (sql.includes('FROM collector_device_heartbeat')) return state.device;
        if (sql.includes('status=\'PENDING\' LIMIT 1'))
          return state.commands.find(c => c.device_id === params[0] && c.status === 'PENDING') ?? null;
        if (sql.includes('ORDER BY requested_ms DESC'))
          return [...state.commands].reverse().find(c => c.device_id === params[0]) ?? null;
        if (sql.includes('expires_ms>? ORDER BY requested_ms'))
          return state.commands.find(c => c.device_id === params[0] && c.status === 'PENDING' && c.expires_ms > params[1]) ?? null;
        if (sql.includes('SELECT status FROM collector_remote_refresh'))
          return state.commands.find(c => c.command_id === params[0] && c.device_id === params[1]) ?? null;
        throw new Error('UNEXPECTED_SQL_FIRST ' + sql);
      },
      async run() {
        if (sql.includes("status='EXPIRED'")) {
          state.commands.forEach(c => { if (c.status === 'PENDING' && c.expires_ms <= params[0]) c.status = 'EXPIRED'; });
        } else if (sql.includes('INSERT INTO collector_remote_refresh')) {
          if (state.commands.some(c => c.device_id === params[1] && c.status === 'PENDING'))
            throw new Error('UNIQUE_PENDING');
          state.commands.push({ command_id: params[0], device_id: params[1], action: 'REFRESH_NOW',
            status: 'PENDING', requested_ms: params[2], expires_ms: params[3] });
        } else if (sql.includes("status='ACCEPTED'")) {
          const c = state.commands.find(c => c.command_id === params[1] && c.device_id === params[2]);
          if (c?.status === 'PENDING' && c.expires_ms > params[3]) c.status = 'ACCEPTED';
        } else throw new Error('UNEXPECTED_SQL_RUN ' + sql);
        return { success: true };
      },
    };
  } };
  return { state, db };
}

test('all remote actions require auth; no arbitrary navigation, tap or purchase', async () => {
  const db = { prepare() { throw new Error('DB_MUST_NOT_BE_USED'); } };
  const env = { DB: db, COLLECTOR_INGEST_TOKEN: token };
  assert.equal((await requestRemoteRefresh(jsonRequest('/refresh', { schema_version: 1, action: 'REFRESH_NOW' },
    { 'content-type': 'application/json' }), env, now)).status, 401);
  assert.equal((await requestRemoteRefresh(jsonRequest('/refresh', { schema_version: 1, action: 'BUY' }), env, now)).status, 400);
  assert.equal((await requestRemoteRefresh(jsonRequest('/refresh', { schema_version: 1, action: 'REFRESH_NOW', amount: 100 }), env, now)).status, 400);
  assert.equal((await pollRemoteRefresh(new Request(root + `/next?device_id=${deviceId}`), env, now)).status, 401);
  assert.equal((await acknowledgeRemoteRefresh(jsonRequest('/ack', { schema_version: 1, action: 'REFRESH_NOW',
    device_id: deviceId, command_id: crypto.randomUUID() }, { 'content-type': 'application/json' }), env, now)).status, 401);
  assert.equal((await worker.fetch(jsonRequest('/refresh', { schema_version: 1, action: 'REFRESH_NOW' }), { DB: db })).status, 503);
});

test('active collector accepts one bounded refresh, acknowledges and rate limits', async () => {
  const { state, db } = fakeDb();
  const env = { DB: db, COLLECTOR_INGEST_TOKEN: token };
  const req = jsonRequest('/refresh', { schema_version: 1, action: 'REFRESH_NOW' });
  const created = await requestRemoteRefresh(req, env, now);
  assert.equal(created.status, 202);
  assert.equal(created.payload.action, 'REFRESH_NOW');
  const coalesced = await requestRemoteRefresh(jsonRequest('/refresh', { schema_version: 1, action: 'REFRESH_NOW' }), env, now + 5_000);
  assert.equal(coalesced.status, 202);
  assert.equal(coalesced.payload.coalesced, true);
  assert.equal(state.commands.length, 1);
  const polled = await pollRemoteRefresh(new Request(root + `/next?device_id=${deviceId}`, { headers }), env, now + 6_000);
  assert.equal(polled.payload.command_id, created.payload.command_id);
  const ack = await acknowledgeRemoteRefresh(jsonRequest('/ack', { schema_version: 1,
    action: 'REFRESH_NOW', device_id: deviceId, command_id: created.payload.command_id }), env, now + 10_000);
  assert.equal(ack.status, 202);
  assert.equal(state.commands[0].status, 'ACCEPTED');
  assert.equal((await pollRemoteRefresh(new Request(root + `/next?device_id=${deviceId}`, { headers }), env, now + 11_000)).payload.action, null);
  assert.equal((await requestRemoteRefresh(jsonRequest('/refresh', { schema_version: 1, action: 'REFRESH_NOW' }), env, now + 12_000)).status, 429);
});

test('expired request is not delivered; offline device cannot be commanded', async () => {
  const { state, db } = fakeDb();
  const env = { DB: db, COLLECTOR_INGEST_TOKEN: token };
  await requestRemoteRefresh(jsonRequest('/refresh', { schema_version: 1, action: 'REFRESH_NOW' }), env, now);
  const tooLate = await pollRemoteRefresh(new Request(root + `/next?device_id=${deviceId}`, { headers }), env, now + 180_001);
  assert.equal(tooLate.payload.action, null);
  const refreshed = await requestRemoteRefresh(jsonRequest('/refresh', { schema_version: 1, action: 'REFRESH_NOW' }), env, now + 180_001);
  assert.equal(refreshed.status, 202);
  assert.equal(state.commands[0].status, 'EXPIRED');
  const offline = fakeDb(false);
  assert.equal((await requestRemoteRefresh(jsonRequest('/refresh', { schema_version: 1, action: 'REFRESH_NOW' }),
    { ...env, DB: offline.db }, now)).status, 409);
});
