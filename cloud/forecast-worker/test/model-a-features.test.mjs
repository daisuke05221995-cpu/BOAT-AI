import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { ModelAPlayerHistory } from '../src/model-a-history.mjs';
import { buildModelAFeatures } from '../src/model-a-features.mjs';

const golden = JSON.parse(readFileSync(new URL('./fixtures/python-model-a-features.json', import.meta.url), 'utf8'));
const clone = (value) => JSON.parse(JSON.stringify(value));

test('complete 6-lane 82+24 vectors match independent Python r2/r4 synthetic goldens', () => {
  let checked = 0;
  let maxDifference = 0;
  for (const fixture of golden.cases) {
    const history = new ModelAPlayerHistory(clone(fixture.state));
    const result = buildModelAFeatures(fixture.race, history);
    assert.equal(result.usable, true);
    assert.equal(result.reason, null);
    assert.deepEqual([result.predictionDayOrdinal, result.historyThroughDayOrdinal, result.historyFreshForDay],
      [fixture.expected.predictionDayOrdinal, fixture.expected.historyThroughDayOrdinal,
        fixture.expected.historyFreshForDay]);
    assert.deepEqual(result.laneHistory.map((ctx) => ctx.flags), fixture.expected.flags);
    assert.equal(result.input.venue, fixture.race.stadiumNumber);
    assert.equal(result.input.raceNumber, fixture.race.raceNumber);
    assert.equal(result.input.boat.length, 6);
    assert.equal(result.input.global.length, 24);

    for (const [actual, expected] of [
      ...result.input.boat.map((row, lane) => [row, fixture.expected.boat[lane]]),
      [result.input.global, fixture.expected.global],
    ]) {
      assert.equal(actual.length, expected.length);
      for (let feature = 0; feature < expected.length; feature++) {
        if (expected[feature] === null) {
          assert.ok(Number.isNaN(actual[feature]), `missing feature at ${feature} was filled`);
        } else {
          const difference = Math.abs(actual[feature] - expected[feature]);
          maxDifference = Math.max(maxDifference, difference);
          assert.ok(difference <= 1e-6,
            `Python/JS mismatch feature=${feature}: ${actual[feature]} vs ${expected[feature]}`);
        }
        checked++;
      }
    }
  }
  assert.equal(checked, 3 * (6 * 82 + 24));
  assert.ok(maxDifference < 1e-6);
});

test('feature builder rejects missing/duplicate contestants and unverified pre-race inputs', () => {
  const base = clone(golden.cases[0].race);
  const history = new ModelAPlayerHistory();
  const failure = (race, reason) => {
    const value = buildModelAFeatures(race, history);
    assert.equal(value.usable, false);
    assert.equal(value.input, null);
    assert.equal(value.reason, reason);
  };
  failure({ ...base, date: '2026-02-30' }, 'Invalid race date');
  failure({ ...base, stadiumNumber: 25 }, 'Invalid venue/race number');
  failure({ ...base, racers: base.racers.slice(0, 5) }, 'Model A requires exactly lanes 1..6');
  failure({ ...base, racers: base.racers.map((r, i) => i === 1 ? { ...r, lane: 1 } : r) },
    'Model A requires exactly lanes 1..6');
  failure({ ...base, racers: base.racers.map((r, i) => i === 1 ? { ...r, registrationNumber: base.racers[0].registrationNumber } : r) },
    'Missing or duplicate racer registration number');
  failure({ ...base, racers: base.racers.map((r, i) => i === 2 ? { ...r, nationalWinRate: null } : r) },
    'Missing required Model A pre-race input');
  failure({ ...base, racers: base.racers.map((r, i) => i === 2 ? { ...r, preview: { ...r.preview, startTiming: null } } : r) },
    'Missing required Model A pre-race input');
  failure({ ...base, racers: base.racers.map((r, i) => i === 1 ? { ...r, preview: { ...r.preview, course: base.racers[0].preview.course } } : r) },
    'Missing required Model A pre-race input');
});

test('already committed same-day history cannot generate a retrospective forecast', () => {
  const fixture = golden.cases[1];
  const history = new ModelAPlayerHistory(clone(fixture.state));
  const base = buildModelAFeatures(fixture.race, history);
  assert.equal(base.usable, true);
  history.exportState().lastDay = base.predictionDayOrdinal;
  const after = buildModelAFeatures(fixture.race, history);
  assert.equal(after.usable, false);
  assert.match(after.reason, /strictly earlier/);
});
