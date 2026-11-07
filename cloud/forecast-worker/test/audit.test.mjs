import test from 'node:test';
import assert from 'node:assert/strict';
import { summarizeDailyAudit } from '../src/audit.mjs';
import { runScheduled } from '../src/worker.mjs';

const now = Date.parse('2026-11-06T12:00:00Z');
const fullOdds = Object.fromEntries(Array.from({ length: 6 }, (_, a) => a + 1)
  .flatMap(a => Array.from({ length: 6 }, (_, b) => b + 1)
    .flatMap(b => Array.from({ length: 6 }, (_, c) => c + 1)
      .filter(c => a !== b && b !== c && a !== c).map(c => [`${a}-${b}-${c}`, 20]))));
const sixRacers = Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i + 1), {
  course_number: i + 1, exhibition_time: 6.75, start_timing: 0.12,
}]));
const weather = (observedMs = now - 150_000) => ({
  wind_speed: 2, wind_direction_number: 5, wave_height: 3,
  air_temperature: 19, water_temperature: 17,
  weather_source: 'authorized-weather', weather_observed_at: new Date(observedMs).toISOString(),
});
const verified = {
  race_date: '2026-11-06', stadium_number: 1, race_number: 1,
  preview_json: JSON.stringify({ date: '2026-11-06', stadium_number: 1, race_number: 1,
    racers: sixRacers, ...weather() }),
  preview_source: 'authorized-exhibition', preview_observed_ms: now - 150_000,
  weather_source: 'authorized-weather', weather_observed_ms: now - 150_000,
  odds_json: JSON.stringify(fullOdds), odds_source: 'authorized-odds', odds_observed_ms: now - 150_000,
  captured_ms: now - 120_000,
};
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
    race('r3', { ...verified,
      forecast_json: '{"combinations":[]}', model_version: 'model-a', decision: 'BUY' }),
    race('r4', { ...verified,
      forecast_json: '{"combinations":[]}', model_version: 'model-a', decision: 'SKIP' }),
    race('r5', { ...verified, captured_ms: now + 1,
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

test('research-only roster candidates are never counted as trusted forecast inputs', () => {
  const rows = [
    race('candidate-1', { program_candidate_status: 'SHAPE_ONLY_UNVERIFIED' }),
    race('candidate-2', { program_candidate_status: 'SHAPE_ONLY_UNVERIFIED' }),
    race('missing-1', { program_candidate_status: 'UNAVAILABLE',
      program_candidate_failure_code: 'PROGRAM_SIX_RACERS_MISSING' }),
    race('not-checked'),
  ];
  const audit = summarizeDailyAudit('2026-11-06', now, rows);
  assert.deepEqual(audit.program_roster_candidate, {
    shape_complete_unverified: 2, unavailable: 1, not_checked: 1,
    source_timestamp_verified: 0, eligible_for_forecast: 0,
    failure_codes: { PROGRAM_SIX_RACERS_MISSING: 1 },
  });
  assert.equal(audit.capture.forecasts_ready, 0);
});

test('full six-finisher shape diagnostics exclude unformed/postponed and never certify history', () => {
  const rows = [
    race('final-1', { six_finish_candidate_status: 'SHAPE_ONLY_UNVERIFIED' }),
    race('final-2', { six_finish_candidate_status: 'NON_SETTLED' }),
    race('invalid', { six_finish_candidate_status: 'UNAVAILABLE',
      six_finish_candidate_failure_code: 'RESULT_SIX_RACERS_MISSING' }),
    race('unchecked'),
  ];
  const audit = summarizeDailyAudit('2026-11-06', now, rows);
  assert.deepEqual(audit.six_finish_candidate, {
    shape_complete_unverified: 1, non_settled: 1, unavailable: 1,
    not_checked: 1, certified_for_history: 0,
    failure_codes: { RESULT_SIX_RACERS_MISSING: 1 },
  });
  assert.equal(audit.capture.forecasts_ready, 0);
});

test('audit distinguishes win payouts, non-formation and postponement from missing results', () => {
  const rows = [
    race('settled', { result_json: JSON.stringify({ status: 'SETTLED', trifecta_combination: '1-2-3' }), result_recorded_ms: now }),
    race('unformed', { result_json: JSON.stringify({ status: 'UNFORMED', refund_per_100: 100 }), result_recorded_ms: now }),
    race('postponed', { result_json: JSON.stringify({ status: 'POSTPONED' }), result_recorded_ms: now }),
    race('cancelled', { result_json: JSON.stringify({ status: 'CANCELLED' }), result_recorded_ms: now }),
    race('legacy', { result_json: JSON.stringify({ trifecta_combination: '4-2-1', trifecta_payout: 1200 }), result_recorded_ms: now }),
    race('missing', { result_failure_code: 'RESULT_NOT_FINAL' }),
  ].map(row => ({ ...row, deadline_ms: now - 25 * 60_000 }));
  const audit = summarizeDailyAudit('2026-11-06', now, rows);
  assert.deepEqual(audit.results, { due: 6, recorded: 5, settled: 1, unformed: 1,
    postponed: 1, cancelled: 1, legacy_settled: 1, unresolved_due: 1 });
  assert.deepEqual(audit.result_failure_codes, { RESULT_NOT_FINAL: 1 });
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
  assert.deepEqual(batched.map(batch => batch.length), [48, 48, 48, 12, 48, 48, 48, 12]);
  assert.equal(batched.flat().filter(stmt => stmt.sql.includes('INSERT INTO race_schedule')).length, 156);
  const candidates = batched.flat().filter(stmt => stmt.sql.includes('INSERT INTO program_roster_candidate'));
  assert.equal(candidates.length, 156);
  assert.equal(candidates.every(stmt => stmt.args[2] === 'UNAVAILABLE' &&
    stmt.args[3] === 'PROGRAM_CHECKED_AFTER_DEADLINE' && stmt.args[4] === null), true);
  assert.equal(singleWrites.some(stmt => stmt.sql.includes('UPDATE daily_import SET race_count') && stmt.args[0] === 156), true);
  assert.equal(singleWrites.some(stmt => stmt.sql.includes('forecast_json')), false);
});

test('morning import stages only six-entrant program shape, never a BUY or source-time assertion', async () => {
  const nowMs = Date.parse('2026-11-07T07:00:00+09:00');
  const racers = Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i + 1), {
    entry_number: i + 1, number: i + 4000, rank_number: 3, national_win_rate: 4.8,
  }]));
  const program = { programs: { stadiums: { '1': { races: { '1': {
    date: '2026-11-07', stadium_number: 1, race_number: 1,
    closed_at: '2026-11-07 10:30:00', racers,
    preview: { racers: { '1': { start_timing: 0.2 } } },
    result: { trifecta_combination: '4-2-1' },
  } } } } } };
  const saved = [], originals = { fetch: globalThis.fetch, now: Date.now };
  globalThis.fetch = async () => new Response(JSON.stringify(program), { status: 200 });
  Date.now = () => nowMs;
  const env = { DB: {
    prepare(sql) { return { bind(...args) { return {
      sql, args,
      first: async () => null,
      all: async () => ({ results: [] }),
      run: async () => ({ meta: { changes: 1 } }),
    }; } }; },
    async batch(statements) { saved.push(...statements); return statements.map(() => ({ meta: { changes: 1 } })); },
  } };
  try { await runScheduled(env, nowMs); }
  finally { globalThis.fetch = originals.fetch; Date.now = originals.now; }
  const candidate = saved.find(stmt => stmt.sql.includes('INSERT INTO program_roster_candidate'));
  assert.ok(candidate);
  assert.equal(candidate.args[2], 'SHAPE_ONLY_UNVERIFIED');
  assert.equal(candidate.args[3], null);
  assert.equal(JSON.parse(candidate.args[4]).racers.length, 6);
  assert.equal(candidate.args[4].includes('start_timing'), false);
  assert.equal(candidate.args[4].includes('trifecta_combination'), false);
  assert.equal(saved.some(stmt => stmt.sql.includes('forecast_json')), false);
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

test('T-8 authorized provider snapshots persist both real source clocks but do not invent AI output', async () => {
  const nowMs = Date.now();
  const date = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit' }).format(nowMs);
  const dueRace = { race_id: `${date}-01-1`, race_date: date, stadium_number: 1, race_number: 1,
    deadline_ms: nowMs + 7 * 60_000, capture_stage: 0 };
  const originalFetch = globalThis.fetch;
  const seen = [];
  globalThis.fetch = async url => {
    const u = new URL(url);
    seen.push(u.pathname);
    const common = { date, stadium_number: 1, race_number: 1,
      observed_at: new Date(Date.now() - 10_000).toISOString() };
    const content = u.pathname === '/preview'
      ? { ...common, source: 'authorized-exhibition', preview: { ...common,
        racers: sixRacers, ...weather(Date.now() - 10_000) } }
      : { ...common, source: 'authorized-odds', odds: fullOdds };
    return new Response(JSON.stringify(content), { status: 200 });
  };
  const batched = [];
  const env = { PREVIEW_API_URL: 'https://test-provider.invalid/preview',
    ODDS_API_URL: 'https://test-provider.invalid/odds', DB: {
      prepare(sql) { return { bind(...args) { return {
        sql, args,
        first: async () => ({ race_count: 156, last_attempt_ms: nowMs }),
        all: async () => ({ results: sql.includes('capture_stage < 2') ? [dueRace] : [] }),
        run: async () => ({ meta: { changes: 1 } }),
      }; } }; },
      async batch(statements) { batched.push(statements); return statements.map(() => ({ meta: { changes: 1 } })); },
    } };
  try { await runScheduled(env, nowMs); }
  finally { globalThis.fetch = originalFetch; }
  assert.deepEqual(seen, ['/preview', '/odds']);
  assert.deepEqual(batched.map(batch => batch.length), [1, 1, 2]);
  const saved = batched[2].find(stmt => stmt.sql.includes('UPDATE race_schedule'));
  assert.ok(saved);
  assert.equal(saved.args[0], 2); // completed capture; model still not deployed
  assert.equal(saved.args[3], 'authorized-exhibition');
  assert.ok(Number.isFinite(saved.args[4]));
  assert.equal(saved.args[5], 'authorized-weather');
  assert.ok(Number.isFinite(saved.args[6]));
  assert.equal(saved.args[8], 'authorized-odds');
  assert.ok(Number.isFinite(saved.args[9]));
  assert.equal(saved.args[10], null); // no acquisition error
  assert.equal(saved.sql.includes('forecast_json'), false);
});

test('same-deadline provider calls run concurrently with a strict four-race cap', async () => {
  const nowMs = Date.now();
  const date = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit' }).format(nowMs);
  const races = Array.from({ length: 8 }, (_, i) => ({
    race_id: `${date}-01-${i + 1}`, race_date: date, stadium_number: 1,
    race_number: i + 1, deadline_ms: nowMs + 7 * 60_000, capture_stage: 0,
  }));
  const originalFetch = globalThis.fetch;
  let active = 0, maxActive = 0, calls = 0;
  globalThis.fetch = async url => {
    const u = new URL(url);
    active++;
    calls++;
    maxActive = Math.max(maxActive, active);
    await new Promise(resolve => setTimeout(resolve, 8));
    active--;
    const number = Number(u.searchParams.get('race'));
    const common = { date, stadium_number: 1, race_number: number,
      observed_at: new Date(Date.now() - 10_000).toISOString() };
    const payload = u.pathname === '/preview'
      ? { ...common, source: 'authorized-exhibition', preview: { date, stadium_number: 1,
        race_number: number, racers: sixRacers, ...weather(Date.now() - 10_000) } }
      : { ...common, source: 'authorized-odds', odds: fullOdds };
    return new Response(JSON.stringify(payload));
  };
  const env = { PREVIEW_API_URL: 'https://test-provider.invalid/preview',
    ODDS_API_URL: 'https://test-provider.invalid/odds', DB: {
      prepare(sql) { return { bind() { return {
        first: async () => ({ race_count: 156, last_attempt_ms: nowMs }),
        all: async () => ({ results: sql.includes('capture_stage < 2') ? races : [] }),
        run: async () => ({ meta: { changes: 1 } }),
      }; } }; },
      batch: async statements => statements.map(() => ({ meta: { changes: 1 } })),
    } };
  try { await runScheduled(env, nowMs); }
  finally { globalThis.fetch = originalFetch; }
  assert.equal(calls, 16);
  assert.ok(maxActive > 1);
  assert.ok(maxActive <= 4);
});
