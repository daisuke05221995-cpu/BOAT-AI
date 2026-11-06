import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { reconcileModelAHistoryDay } from '../src/model-a-daily-reconcile.mjs';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/python-model-a-features.json', import.meta.url)));
const clone = value => structuredClone(value);
const date = '2026-11-06';
const now = Date.parse('2026-11-07T02:00:00Z');
const races = fixture.cases.slice(1).map(sample => ({ ...clone(sample.race),
  raceId: `${date}-${String(sample.race.stadiumNumber).padStart(2, '0')}-${sample.race.raceNumber}`,
  result: { status: 'SETTLED', finishOrder: [1, 2, 3, 4, 5, 6] },
}));
const manifest = {
  date, scheduledRaceIds: races.map(race => race.raceId), expectedRaceCount: races.length,
  scheduleSource: 'audited-program-feed', resultSource: 'audited-results-feed',
  confirmedAt: '2026-11-06T16:00:00Z',
};
const state = fixture.cases[1].state;
const run = (s = state, m = manifest, r = races, clock = now) =>
  reconcileModelAHistoryDay(s, m, r, clock);

test('complete cross-referenced day advances only the copied history, once', () => {
  const before = clone(state);
  const result = run();
  assert.deepEqual(state, before);
  assert.deepEqual({ ...result.audit }, {
    status: 'VALIDATED_AGAINST_SUPPLIED_MANIFEST', date, dayOrdinal: 739926,
    expectedRaces: 2, settledRaces: 2, cancelledRaces: 0, committedRaces: 2,
    previousLastDay: 739925, historyLastDay: 739926,
    scheduleSource: manifest.scheduleSource, resultSource: manifest.resultSource,
    confirmedAt: manifest.confirmedAt,
  });
  assert.equal(result.state.updateRaces, state.updateRaces + 2);
  assert.throws(() => run(result.state), /MODEL_A_DAY_NONCONSECUTIVE/);
});

test('missing, duplicate, unscheduled and incomplete races never advance history', () => {
  const before = clone(state);
  assert.throws(() => run(state, manifest, races.slice(0, 1)), /RACE_COUNT_MISMATCH/);
  assert.throws(() => run(state, manifest, [races[0], races[0]]), /DUPLICATE_RACE/);
  assert.throws(() => run(state, manifest, [races[0], {
    ...races[1], stadiumNumber: 9, raceId: `${date}-09-8`,
  }]), /UNSCHEDULED_RACE/);
  assert.throws(() => run(state, manifest, [races[0], {
    ...races[1], result: { status: 'SETTLED', finishOrder: [1, 2, 3, 4, 5] },
  }]), /RESULT_INCOMPLETE/);
  assert.throws(() => run(state, manifest, [races[0], {
    ...races[1], racers: races[1].racers.slice(0, 5),
  }]), /FEATURE_INCOMPLETE/);
  assert.deepEqual(state, before);
});

test('date continuity and independently supplied schedule count are mandatory', () => {
  assert.throws(() => run(state, { ...manifest, expectedRaceCount: 3 }), /INVALID_SCHEDULE/);
  assert.throws(() => run(state, { ...manifest,
    scheduledRaceIds: [races[0].raceId, races[0].raceId],
  }), /INVALID_SCHEDULE/);
  assert.throws(() => run({ ...state, lastDay: state.lastDay - 1 }), /NONCONSECUTIVE/);
  assert.throws(() => run(state, manifest, [{ ...races[0], date: '2026-11-05' }, races[1]]), /WRONG_DATE/);
});

test('finalization after JST day-end must be attestable, not assumed from HTTP fetch', () => {
  assert.throws(() => run(state, { ...manifest, confirmedAt: '2026-11-06T14:59:59Z' }), /UNVERIFIED_MANIFEST/);
  assert.throws(() => run(state, { ...manifest, confirmedAt: '2026-11-07T05:00:00Z' }), /UNVERIFIED_MANIFEST/);
  assert.throws(() => run(state, { ...manifest, resultSource: '' }), /UNVERIFIED_MANIFEST/);
  assert.throws(() => run(state, manifest, races, Date.parse('2026-11-06T13:00:00Z')), /NOT_FINAL/);
});

test('explicitly documented cancellations count as terminal but never become synthetic outcome rows', () => {
  const cancelled = { ...races[1], result: { status: 'CANCELLED', reason: 'Venue officially cancelled' } };
  const result = run(state, manifest, [races[0], cancelled]);
  assert.equal(result.audit.cancelledRaces, 1);
  assert.equal(result.audit.committedRaces, 1);
  assert.equal(result.state.updateRaces, state.updateRaces + 1);
  assert.throws(() => run(state, manifest, [races[0], {
    ...cancelled, result: { status: 'CANCELLED' },
  }]), /CANCELLATION_UNVERIFIED/);
});
