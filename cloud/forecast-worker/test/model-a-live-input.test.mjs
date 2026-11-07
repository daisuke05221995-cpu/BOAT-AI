import test from 'node:test';
import assert from 'node:assert/strict';
import { assembleAuthorizedModelARace } from '../src/model-a-live-input.mjs';
import { ModelAPlayerHistory } from '../src/model-a-history.mjs';
import { buildModelAFeatures } from '../src/model-a-features.mjs';

const date = '2026-11-07';
const deadline = Date.parse('2026-11-07T09:00:00Z');
const now = deadline - 7 * 60_000;
const row = { race_id: `${date}-01-1`, race_date: date, stadium_number: 1,
  race_number: 1, deadline_ms: deadline };
const approved = { roster: ['reviewed-roster'], preview: ['reviewed-preview'],
  weather: ['reviewed-weather'], odds: ['reviewed-odds'] };
const at = millis => new Date(millis).toISOString();
function inputs() {
  const program = { date, stadium_number: 1, race_number: 1,
    racers: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i + 1), {
      entry_number: i + 1, number: 3100 + i, rank_number: 3,
      national_win_rate: 5.7, local_win_rate: 5.2,
    }])) };
  const preview = { date, stadium_number: 1, race_number: 1,
    wind_speed: 2, wind_direction_number: 4, wave_height: 3,
    air_temperature: 18, water_temperature: 16,
    weather_source: 'reviewed-weather', weather_observed_at: at(now - 40_000),
    racers: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i + 1), {
      number: 3100 + i, course_number: i + 1,
      exhibition_time: 6.72 + i * 0.01, start_timing: 0.1 + i * 0.01,
      tilt_adjustment: 0, weight_adjustment: 0,
    }])) };
  const odds = Object.fromEntries(Array.from({ length: 6 }, (_, i) => i + 1)
    .flatMap(a => Array.from({ length: 6 }, (_, i) => i + 1)
      .flatMap(b => Array.from({ length: 6 }, (_, i) => i + 1)
        .filter(c => a !== b && b !== c && a !== c).map(c => [`${a}-${b}-${c}`, 32.5]))));
  return [
    { ...program, source: 'reviewed-roster', observed_at: at(now - 50_000), roster: program },
    { date, stadium_number: 1, race_number: 1, source: 'reviewed-preview',
      observed_at: at(now - 30_000), preview },
    { date, stadium_number: 1, race_number: 1, source: 'reviewed-odds',
      observed_at: at(now - 25_000), odds },
  ];
}
const assemble = (items, time = now, allow = approved) =>
  assembleAuthorizedModelARace(row, ...items, time, allow);

test('explicitly authorized fresh four-source inputs map into six-boat Model A features', () => {
  const output = assemble(inputs());
  assert.equal(output.inputContractVerified, true);
  assert.equal(output.forecastEnabled, false);
  assert.equal(output.race.racers.length, 6);
  assert.equal(Object.keys(output.odds).length, 120);
  assert.equal(output.race.racers[0].registrationNumber, 3100);
  assert.equal(output.race.racers[0].preview.course, 1);
  assert.equal(output.race.preview.windDirectionNumber, 4);
  assert.equal(output.provenance.rosterObservedMs, now - 50_000);
  assert.equal(output.provenance.oddsObservedMs, now - 25_000);
  const ordinal = Math.trunc(Date.parse(`${date}T00:00:00Z`) / 86_400_000) + 719_163;
  const history = new ModelAPlayerHistory({ stats: {}, recent: {},
    lastDay: ordinal - 1, updateRaces: 0 });
  const features = buildModelAFeatures(output.race, history);
  assert.equal(features.usable, true);
  assert.equal(features.input.boat.length, 6);
  assert.equal(features.input.boat[0].length, 82);
  assert.equal(features.input.global.length, 24);
});

test('unapproved sources and absent allowlist are rejected regardless of source claims', () => {
  assert.throws(() => assemble(inputs(), now, null), /ROSTER_SOURCE_NOT_APPROVED/);
  const snapshots = inputs();
  snapshots[0].source = 'licensed-roster';
  assert.throws(() => assemble(snapshots), /ROSTER_SOURCE_NOT_APPROVED/);
  const replaced = inputs();
  replaced[1].preview.weather_source = 'other-weather';
  assert.throws(() => assemble(replaced), /WEATHER_SOURCE_NOT_APPROVED/);
});

test('stale roster, mixed venue, missing preview player ID and incomplete odds all fail closed', () => {
  const stale = inputs();
  stale[0].observed_at = at(now - 121_000);
  assert.throws(() => assemble(stale), /ROSTER_STALE/);
  const otherRace = inputs();
  otherRace[0].roster.race_number = 2;
  assert.throws(() => assemble(otherRace), /ROSTER_WRONG_RACE|PROGRAM_IDENTITY_MISMATCH/);
  const swap = inputs();
  swap[1].preview.racers['2'].number = 9000;
  assert.throws(() => assemble(swap), /PREVIEW_PLAYER_ID_MISMATCH/);
  const noIdentity = inputs();
  delete noIdentity[1].preview.racers['3'].number;
  assert.throws(() => assemble(noIdentity), /PREVIEW_PLAYER_ID_MISMATCH/);
  const partialOdds = inputs();
  delete partialOdds[2].odds['1-2-3'];
  assert.throws(() => assemble(partialOdds), /ODDS_NOT_COMPLETE/);
  assert.throws(() => assemble(inputs(), deadline), /CAPTURE_NOT_BEFORE_DEADLINE/);
});
