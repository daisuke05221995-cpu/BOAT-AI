import test from 'node:test';
import assert from 'node:assert/strict';
import { compareHistoryGapForResearch } from '../src/history-gap-diagnostic.mjs';

const date = '2026-11-06';
const checked = Date.parse('2026-11-07T01:00:00Z');
const ordinal = Math.trunc(Date.parse(`${date}T00:00:00Z`) / 86_400_000) + 719_163;
function race(number, fullSix = true) {
  const id = { date, stadium_number: 1, race_number: number };
  return { ...id, closed_at: `2026-11-06 ${String(number + 9).padStart(2, '0')}:00:00`,
    racers: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i + 1), {
      entry_number: i + 1, number: 4000 + i + number * 10,
    }])),
    result: { ...id,
      payouts: { trifecta: [{ combination: '1-2-3', amount: 1230 }] },
      racers: fullSix ? Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i + 1), {
        entry_number: i + 1, number: 4000 + i + number * 10, place_number: i + 1,
      }])) : {},
    } };
}
function feed() {
  const postponed = { ...race(3), day_number_source: '順延' };
  postponed.result.payouts.trifecta = [];
  return { programs: { stadiums: { 1: { races: { 1: race(1), 2: race(2, false), 3: postponed } } } } };
}
const state = (players = []) => ({ lastDay: ordinal, updateRaces: 1,
  recent: Object.fromEntries(players.map(n => [String(n), { days: [ordinal] }])) });

test('count discrepancy separates payout settlement, valid six finish and player appearances', () => {
  const history = state(Array.from({ length: 6 }, (_, i) => 4010 + i));
  const audit = compareHistoryGapForResearch(feed(), date, history, checked);
  assert.equal(audit.status, 'RESEARCH_SOURCE_AND_HISTORY_UNCERTIFIED');
  assert.equal(audit.published_program_rows, 3);
  assert.equal(audit.scheduled_rows_parsed, 3);
  assert.equal(audit.settled, 2);
  assert.equal(audit.full_six, 1);
  assert.equal(audit.non_settled.POSTPONED, 1);
  assert.equal(audit.full_six_unavailable.RESULT_SIX_RACERS_MISSING, 1);
  assert.equal(audit.candidate_history_races, 1);
  assert.equal(audit.settled_minus_candidate, 1);
  assert.equal(audit.verified_six_minus_candidate, 0);
  assert.deepEqual(audit.suspect_races_not_proven_missing, []);
  assert.equal(audit.limitations.length, 5);
});

test('raw post-race non-six codes identify review cases without inventing finishing places', () => {
  const data = feed();
  const outcome = data.programs.stadiums[1].races[1].result.racers;
  outcome[5].place_number = 9;
  outcome[5].place_number_source = '転';
  outcome[6].place_number = 16;
  outcome[6].place_number_source = '欠';
  const audit = compareHistoryGapForResearch(data, date, state([]), checked);
  assert.equal(audit.full_six, 0);
  assert.equal(audit.full_six_unavailable.RESULT_SIX_FINISH_ORDER_INVALID, 1);
  assert.deepEqual(audit.invalid_finish_raw_code_counts, { '16:欠': 1, '9:転': 1 });
  assert.deepEqual(audit.invalid_six_race_details, [{ race_id: '2026-11-06-01-1',
    invalid_finish_entries: [
      { lane: 5, place_number: 9, place_number_source: '転' },
      { lane: 6, place_number: 16, place_number_source: '欠' },
    ] }]);
  assert.equal(audit.status, 'RESEARCH_SOURCE_AND_HISTORY_UNCERTIFIED');
});

test('duplicate valid-looking places are still invalid, not double-counted as complete results', () => {
  const data = feed();
  const outcome = data.programs.stadiums[1].races[1].result.racers;
  outcome[6].place_number = 5;
  outcome[6].place_number_source = '同';
  const audit = compareHistoryGapForResearch(data, date, state([]), checked);
  assert.equal(audit.full_six, 0);
  assert.deepEqual(audit.invalid_six_race_details[0].invalid_finish_entries, [
    { lane: 5, place_number: 5, place_number_source: null },
    { lane: 6, place_number: 5, place_number_source: '同' },
  ]);
  assert.deepEqual(audit.invalid_finish_raw_code_counts, { '5:?': 1, '5:同': 1 });
});

test('player deficits flag only suspects and never assign a missing race as fact', () => {
  const history = { lastDay: ordinal, updateRaces: 0, recent: {} };
  const audit = compareHistoryGapForResearch(feed(), date, history, checked);
  assert.equal(audit.candidate_history_races, 0);
  assert.equal(audit.deficient_player_appearances, 6);
  assert.deepEqual(audit.suspect_races_not_proven_missing,
    [{ race_id: '2026-11-06-01-1', deficient_player_count: 6 }]);
});

test('future day, invalid identity, duplicate venue key or six-count inconsistency fail closed', () => {
  assert.throws(() => compareHistoryGapForResearch(feed(), date, state([]),
    Date.parse('2026-11-06T00:00:00Z')), /DAY_NOT_CLOSED/);
  const wrong = feed();
  wrong.programs.stadiums['01'] = wrong.programs.stadiums['1'];
  assert.throws(() => compareHistoryGapForResearch(wrong, date, state([]), checked), /PROGRAM_IDENTITY_INVALID_OR_DUPLICATE/);
  assert.throws(() => compareHistoryGapForResearch(feed(), date,
    state([4010]), checked), /INVALID_APPEARANCE_COUNT/);
  assert.throws(() => compareHistoryGapForResearch(feed(), date,
    { lastDay: ordinal - 1, recent: {} }, checked), /CANDIDATE_NOT_UPDATED/);
});
