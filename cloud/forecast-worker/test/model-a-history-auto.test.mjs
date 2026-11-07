import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseHistorySourceApprovals, verifyHistoricalDailyFeed,
  promoteHistoricalDay, runAutomaticHistoryCatchup } from '../src/model-a-history-auto.mjs';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/python-model-a-features.json', import.meta.url)));
const clone = obj => structuredClone(obj);
const date = '2026-11-06';
const nowMs = Date.parse('2026-11-07T02:00:00Z');
const sha = 'b'.repeat(64);
const sources = { coverage: ['licensed-national'], schedule: ['licensed-schedule'],
  result: ['licensed-results'], roster: ['licensed-roster'],
  preview: ['licensed-preview'], weather: ['licensed-weather'] };
const precloseAt = '2026-11-06T05:52:30Z';
const observedAt = '2026-11-06T05:52:00Z';
const finishAt = '2026-11-06T07:00:00Z';

function dailyFeed() {
  const races = fixture.cases.slice(1).map(sample => {
    const race = clone(sample.race);
    const id = `${date}-${String(race.stadiumNumber).padStart(2, '0')}-${race.raceNumber}`;
    return { ...race, raceId: id, deadlineMs: Date.parse('2026-11-06T06:00:00Z'),
      result: { status: 'SETTLED', finishOrder: [1, 2, 3, 4, 5, 6] },
      sourceEvidence: {
        resultSource: 'licensed-results', resultRecordId: `${id}/result`,
        resultRaceId: id, resultObservedAt: finishAt,
        rosterSource: 'licensed-roster', previewSource: 'licensed-preview',
        weatherSource: 'licensed-weather',
        registrationNumbersByLane: [...race.racers].sort((a, b) => a.lane - b.lane)
          .map(racer => racer.registrationNumber),
        capturedAt: precloseAt, rosterObservedAt: observedAt,
        previewObservedAt: observedAt, weatherObservedAt: observedAt,
      } };
  });
  const manifest = { date, scheduledRaceIds: races.map(race => race.raceId),
    expectedRaceCount: races.length, scheduleSource: 'licensed-schedule',
    resultSource: 'licensed-results', coverageSource: 'licensed-national',
    coverageStatus: 'NATIONAL_ALL_VENUES_COMPLETE',
    coverageConfirmedAt: '2026-11-06T16:00:00Z',
    confirmedAt: '2026-11-06T16:00:00Z' };
  return { manifest, races };
}

test('explicit approved nationwide manifest and original pre-close timestamps pass history gate', () => {
  const feed = dailyFeed();
  const result = verifyHistoricalDailyFeed(feed, date, nowMs, sources);
  assert.equal(result.races.length, 2);
  assert.equal(result.manifest.expectedRaceCount, 2);
});

test('late, missing or spoofed preclose observations are rejected before state mutation', () => {
  const cases = [
    feed => { feed.races[0].sourceEvidence.previewObservedAt = '2026-11-06T05:48:00Z'; },
    feed => { feed.races[0].sourceEvidence.capturedAt = '2026-11-06T06:00:00Z'; },
    feed => { feed.races[0].sourceEvidence.registrationNumbersByLane[0] = 99999; },
    feed => { feed.races[0].sourceEvidence.rosterSource = 'unapproved'; },
    feed => { feed.races[0].sourceEvidence.resultObservedAt = observedAt; },
    feed => { delete feed.races[0].sourceEvidence.resultRecordId; },
    feed => { feed.races[0].sourceEvidence.resultRaceId = 'different-race'; },
    feed => { feed.races[0].sourceEvidence.previewObservedAt = '2026-11-06T06:01:00Z'; },
  ];
  for (const mutate of cases) {
    const feed = dailyFeed(); mutate(feed);
    assert.throws(() => verifyHistoricalDailyFeed(feed, date, nowMs, sources));
  }
});

test('uncertified national coverage, future publication, missing or unapproved origin are rejected', () => {
  const cases = [
    feed => { feed.manifest.coverageStatus = 'LOCAL_ONLY'; },
    feed => { feed.manifest.coverageSource = 'unknown'; },
    feed => { feed.manifest.coverageConfirmedAt = '2026-11-06T14:00:00Z'; },
    feed => { feed.manifest.expectedRaceCount = 3; },
    feed => { feed.manifest.resultSource = 'unknown'; },
    feed => { feed.races.push(feed.races[0]); },
  ];
  for (const mutate of cases) {
    const feed = dailyFeed(); mutate(feed);
    assert.throws(() => verifyHistoricalDailyFeed(feed, date, nowMs, sources));
  }
  assert.equal(parseHistorySourceApprovals(undefined), null);
  assert.deepEqual(parseHistorySourceApprovals(JSON.stringify(sources)), sources);
  assert.throws(() => parseHistorySourceApprovals('{}'), /APPROVALS_INVALID/);
});

test('one full day is sealed, verified and promoted without touching the original history', async () => {
  const current = clone(fixture.cases[1].state);
  const original = clone(current);
  const stored = new Map();
  const activations = [];
  const db = { prepare(sql) {
    if (sql.includes('FROM race_schedule')) return { bind: () => ({ all: async () => ({ results: [] }) }) };
    if (sql.includes('FROM model_a_history_active')) return { first: async () => ({ sha256: sha }) };
    throw Error(`Unexpected query: ${sql}`);
  } };
  const load = async (_, id) => id === sha ? { sha256: sha, state: clone(current) } : stored.get(id);
  const stage = async (_, checkpoint) => {
    stored.set(checkpoint.sha256, { sha256: checkpoint.sha256,
      previousSha256: checkpoint.previousSha256, throughDay: checkpoint.throughDay });
  };
  const promote = async (_, id) => { activations.push(id); };
  const result = await promoteHistoricalDay(db, date, nowMs, dailyFeed(), sources,
    sha, load, stage, promote);
  assert.equal(result.expectedRaces, 2);
  assert.equal(result.committedRaces, 2);
  assert.deepEqual(activations, [result.sha256]);
  assert.deepEqual(current, original);
  assert.equal(stored.get(result.sha256).throughDay, current.lastDay + 1);
});

test('local schedule disagreement fails before reading/advancing history', async () => {
  let reads = 0;
  const db = { prepare(sql) {
    assert.match(sql, /FROM race_schedule/);
    return { bind: () => ({ all: async () => ({ results: [{ race_id: 'other-race' }] }) }) };
  } };
  await assert.rejects(promoteHistoricalDay(db, date, nowMs, dailyFeed(), sources,
    sha, async () => { reads++; }), /LOCAL_SCHEDULE_DISAGREES/);
  assert.equal(reads, 0);
});

test('missing daily feed configuration makes history Cron a no-op', async () => {
  const result = await runAutomaticHistoryCatchup({ DB: { prepare: () => { throw Error('D1 access prohibited'); } } }, nowMs);
  assert.deepEqual(result, { status: 'DISABLED' });
});

test('automatic catch-up chooses only the next day and never repeats within retry window', async () => {
  let claimCount = 0;
  const seen = [];
  const db = { prepare(sql) {
    if (sql.startsWith('SELECT * FROM model_a_history_active')) {
      return { first: async () => ({ through_day: 739925, sha256: sha }) };
    }
    if (sql.startsWith('INSERT INTO model_a_history_day_attempt')) return { bind(...args) {
      seen.push(['claim', ...args]);
      return { run: async () => ({ meta: { changes: ++claimCount === 1 ? 1 : 0 } }) };
    } };
    if (sql.startsWith('UPDATE model_a_history_day_attempt')) return { bind(...args) {
      seen.push(['complete', ...args]);
      return { run: async () => ({ meta: { changes: 1 } }) };
    } };
    throw Error(`Unexpected SQL: ${sql}`);
  } };
  const env = { DB: db, HISTORY_DAILY_FEED_URL: 'https://licensed.example/daily',
    HISTORY_APPROVED_SOURCES_JSON: JSON.stringify(sources) };
  const download = async (_, requestDate) => {
    seen.push(['download', requestDate]); return dailyFeed();
  };
  const promote = async (_, requestDate, __, ___, ____, previousSha) => {
    seen.push(['promote', requestDate, previousSha]);
    return { sha256: 'c'.repeat(64), expectedRaces: 2, committedRaces: 2 };
  };
  const first = await runAutomaticHistoryCatchup(env, nowMs, download, promote);
  const second = await runAutomaticHistoryCatchup(env, nowMs, download, promote);
  assert.equal(first.status, 'PROMOTED');
  assert.equal(first.date, date);
  assert.equal(second.status, 'RATE_LIMITED');
  assert.deepEqual(seen.filter(item => item[0] === 'download'), [['download', date]]);
  assert.deepEqual(seen.find(item => item[0] === 'promote'), ['promote', date, sha]);
});
