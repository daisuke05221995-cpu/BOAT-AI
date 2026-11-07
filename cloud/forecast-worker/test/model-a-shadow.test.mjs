import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateModelAShadow, parseShadowApprovals } from '../src/model-a-shadow.mjs';
import { FROZEN_MODEL_A_BUNDLE_SHA256 } from '../src/model-a-model-store.mjs';

const date = '2026-11-07';
const deadline = Date.parse('2026-11-07T09:00:00Z');
const nowMs = deadline - 7 * 60_000;
const iso = time => new Date(time).toISOString();
const row = { race_id: `${date}-01-1`, race_date: date,
  stadium_number: 1, race_number: 1, deadline_ms: deadline };
const approvals = { roster: ['approved-roster'], preview: ['approved-preview'],
  weather: ['approved-weather'], odds: ['approved-odds'] };
const key = 'a'.repeat(64);
const historyKey = 'b'.repeat(64);
const day = Math.floor(Date.parse(`${date}T00:00:00Z`) / 86_400_000) + 719_163 - 1;

function snapshots() {
  const roster = { date, stadium_number: 1, race_number: 1,
    racers: Object.fromEntries(Array.from({ length: 6 }, (_, index) => [String(index + 1), {
      entry_number: index + 1, number: 3100 + index, rank_number: 3,
      national_win_rate: 5.7, local_win_rate: 5.2,
    }])) };
  const preview = { date, stadium_number: 1, race_number: 1,
    wind_speed: 2, wind_direction_number: 4, wave_height: 3,
    air_temperature: 18, water_temperature: 16,
    weather_source: 'approved-weather', weather_observed_at: iso(nowMs - 40_000),
    racers: Object.fromEntries(Array.from({ length: 6 }, (_, index) => [String(index + 1), {
      number: 3100 + index, course_number: index + 1,
      exhibition_time: 6.72 + index * 0.01, start_timing: 0.1 + index * 0.01,
    }])) };
  const odds = Object.fromEntries(Array.from({ length: 6 }, (_, a) => a + 1)
    .flatMap(a => Array.from({ length: 6 }, (_, b) => b + 1)
      .flatMap(b => Array.from({ length: 6 }, (_, c) => c + 1)
        .filter(c => a !== b && a !== c && b !== c)
        .map(c => [`${a}-${b}-${c}`, 25.3]))));
  return {
    rosterSnapshot: { ...roster, source: 'approved-roster', observed_at: iso(nowMs - 50_000), roster },
    previewSnapshot: { date, stadium_number: 1, race_number: 1,
      source: 'approved-preview', observed_at: iso(nowMs - 30_000), preview },
    oddsSnapshot: { date, stadium_number: 1, race_number: 1,
      source: 'approved-odds', observed_at: iso(nowMs - 25_000), odds },
  };
}

function options(overrides = {}) {
  let pointerQueries = 0;
  let modelLoads = 0;
  let historyLoads = 0;
  const db = { prepare(sql) {
    assert.match(sql, /model_a_history_active/);
    pointerQueries++;
    return { first: async () => ({ sha256: historyKey, through_day: day }) };
  } };
  return {
    ...snapshots(), row, nowMs, approvals, db, cache: new Map(), bundleSha256: key,
    loadHistory: async () => {
      historyLoads++;
      return { sha256: historyKey, throughDay: day,
        state: { stats: {}, recent: {}, lastDay: day, updateRaces: 0 } };
    },
    loadModels: async () => {
      modelLoads++;
      const constant = () => 0;
      return { bundleSha256: key,
        stages: { stage0: constant, stage1: constant, stage2: constant } };
    },
    stats: () => ({ pointerQueries, modelLoads, historyLoads }),
    ...overrides,
  };
}

test('complete explicitly approved input + previous-day history -> 120 forecast-only probabilities', async () => {
  const args = options();
  const result = await evaluateModelAShadow(args);
  assert.equal(result.status, 'FORECAST_ONLY');
  assert.equal(result.reason, null);
  assert.equal(result.forecast.combinations.length, 120);
  assert.equal(result.forecast.probabilities.length, 120);
  assert.ok(result.forecast.probabilities.every(p => Math.abs(p - 1 / 120) < 1e-10));
  assert.equal(result.historySha256, historyKey);
  assert.equal(result.modelBundleSha256, key);
  assert.equal(result.provenance.rosterSource, 'approved-roster');
  assert.deepEqual(args.stats(), { pointerQueries: 1, modelLoads: 1, historyLoads: 1 });
  assert.equal('decision' in result, false);
  assert.equal('stakes' in result, false);
});

test('stale history prevents all model/history loads and never invents predictions', async () => {
  const args = options({ db: { prepare: () => ({ first: async () =>
    ({ sha256: historyKey, through_day: day - 1 }) }) } });
  const result = await evaluateModelAShadow(args);
  assert.equal(result.status, 'UNAVAILABLE');
  assert.equal(result.reason, 'MODEL_A_HISTORY_STALE');
  assert.equal(result.forecast, null);
  assert.deepEqual(args.stats(), { pointerQueries: 0, modelLoads: 0, historyLoads: 0 });
});

test('missing, stale, mismatched or unapproved source fails before D1 access', async () => {
  const missing = options({ oddsSnapshot: null });
  assert.equal((await evaluateModelAShadow(missing)).reason, 'MODEL_A_LIVE_SOURCES_INCOMPLETE');
  const unapproved = options({ approvals: null });
  assert.equal((await evaluateModelAShadow(unapproved)).reason, 'MODEL_A_SOURCES_NOT_APPROVED');
  const stale = options();
  stale.rosterSnapshot.observed_at = iso(nowMs - 150_000);
  assert.match((await evaluateModelAShadow(stale)).reason, /ROSTER_STALE/);
  const mismatched = options();
  mismatched.previewSnapshot.preview.racers['2'].number = 9999;
  assert.match((await evaluateModelAShadow(mismatched)).reason, /PREVIEW_PLAYER_ID_MISMATCH/);
  const late = options({ nowMs: deadline });
  assert.match((await evaluateModelAShadow(late)).reason, /CAPTURE_NOT_BEFORE_DEADLINE/);
  for (const args of [missing, unapproved, stale, mismatched, late]) {
    assert.deepEqual(args.stats(), { pointerQueries: 0, modelLoads: 0, historyLoads: 0 });
  }
});

test('asset identity failure and probability corruption fail without purchase policy', async () => {
  const corrupt = options({ loadModels: async () => ({ bundleSha256: 'c'.repeat(64), stages: {} }) });
  assert.equal((await evaluateModelAShadow(corrupt)).reason, 'MODEL_A_ASSET_POINTER_MISMATCH');
  const unavailable = options({ bundleSha256: null });
  assert.equal((await evaluateModelAShadow(unavailable)).reason, 'MODEL_A_BUNDLE_NOT_CONFIGURED');
  const noActive = options({ db: { prepare: () => ({ first: async () => null }) } });
  assert.equal((await evaluateModelAShadow(noActive)).reason, 'MODEL_A_HISTORY_NOT_ACTIVE');
});

test('approved-source configuration is explicit and frozen bundle identity stays fixed', () => {
  assert.deepEqual(parseShadowApprovals(JSON.stringify(approvals)), approvals);
  assert.equal(parseShadowApprovals(undefined), null);
  assert.throws(() => parseShadowApprovals('{'), /MODEL_A_APPROVALS_INVALID/);
  assert.throws(() => parseShadowApprovals(JSON.stringify({ roster: ['x'] })), /MODEL_A_APPROVALS_INVALID/);
  assert.match(FROZEN_MODEL_A_BUNDLE_SHA256, /^[0-9a-f]{64}$/);
});
