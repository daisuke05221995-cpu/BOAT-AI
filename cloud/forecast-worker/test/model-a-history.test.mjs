import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { ModelAPlayerHistory } from '../src/model-a-history.mjs';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/python-model-a-history.json', import.meta.url), 'utf8'));

test('all synthetic player-history snapshots match independent Python r4 features and reaction flags', () => {
  const history = new ModelAPlayerHistory();
  let checked = 0;
  let maxError = 0;
  for (const event of fixture.events) {
    if (event.type === 'commit') {
      history.commitDay(event.day, event.updates);
      continue;
    }
    const actual = history.snapshot(event.args);
    assert.deepEqual(actual.flags, event.expected.flags);
    assert.equal(actual.history.length, 32);
    assert.equal(actual.reaction.length, 20);
    for (const [key, length] of [['history', 32], ['reaction', 20]]) {
      for (let i = 0; i < length; i++) {
        maxError = Math.max(maxError, Math.abs(actual[key][i] - event.expected[key][i]));
        checked++;
      }
    }
  }
  assert.deepEqual({ lastDay: history.lastDay, updateRaces: history.updateRaces,
    registeredPlayers: history.registeredPlayers }, fixture.expected_state);
  assert.equal(checked, 38 * 52);
  assert.ok(maxError < 1e-6, `Python history feature discrepancy: ${maxError}`);
});

test('committing a day blocks same-day snapshots, nonchronological updates and partial races', () => {
  const history = new ModelAPlayerHistory();
  const base = {
    player: 1234, course: 1, racerClass: 1,
    exhibitionTime: 6.8, previewStartTiming: 0.17,
    flags: { fastExhibition: false, goodPreviewStart: false, courseChanged: false },
    win: false, top2: false, top3: false,
  };
  assert.throws(() => history.commitDay(10, [base]), /HISTORY_DAY_NOT_COMPLETE/);
  assert.equal(history.lastDay, 0);
  const complete = Array.from({ length: 6 }, (_, index) => ({ ...base, player: 1234 + index }));
  history.commitDay(10, complete);
  assert.equal(history.lastDay, 10);
  assert.equal(history.updateRaces, 1);
  assert.throws(() => history.snapshot({ ...base, day: 10 }), /INVALID_HISTORY_SNAPSHOT/);
  assert.throws(() => history.commitDay(10, complete), /HISTORY_DAY_NOT_COMPLETE/);
  assert.throws(() => history.commitDay(9, complete), /HISTORY_DAY_NOT_COMPLETE/);
  assert.equal(history.updateRaces, 1);
});

test('bad outcomes fail atomically before any player statistics are changed', () => {
  const history = new ModelAPlayerHistory();
  const good = {
    player: 1234, course: 1, racerClass: 1,
    exhibitionTime: 6.8, previewStartTiming: 0.17,
    flags: { fastExhibition: true, goodPreviewStart: false, courseChanged: false },
    win: false, top2: false, top3: true,
  };
  const batch = Array.from({ length: 6 }, (_, index) => ({ ...good, player: 1234 + index }));
  batch[5] = { ...batch[5], win: true, top2: false };
  assert.throws(() => history.commitDay(10, batch), /INVALID_HISTORY_OUTCOME/);
  assert.deepEqual(Object.keys(history.exportState().stats), []);
  assert.equal(history.registeredPlayers, 0);
  assert.equal(history.lastDay, 0);
});

test('state export can be JSON serialized and resumed without changing snapshots', () => {
  const history = new ModelAPlayerHistory();
  const events = fixture.events.slice(0, 7); // first complete day and next-day candidate
  for (const event of events) {
    if (event.type === 'commit') history.commitDay(event.day, event.updates);
  }
  const args = { player: 1000, course: 1, racerClass: 2, exhibitionTime: 6.7,
    previewStartTiming: 0.1, courseChanged: false, day: 10001 };
  const before = history.snapshot(args);
  const resumed = new ModelAPlayerHistory(JSON.parse(JSON.stringify(history.exportState())));
  assert.deepEqual(resumed.snapshot(args), before);
});
