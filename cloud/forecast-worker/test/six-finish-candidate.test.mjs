import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectSixFinishCandidate } from '../src/six-finish-candidate.mjs';

const row = {
  race_date: '2026-11-07', stadium_number: 1, race_number: 2,
  deadline_ms: 100_000,
};
const settled = { status: 'SETTLED', trifecta_combination: '4-3-2' };
function record() {
  return {
    date: '2026-11-07', stadium_number: 1, race_number: 2,
    racers: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i + 1), {
      entry_number: i + 1, number: i + 3000, national_win_rate: 5.2,
    }])),
    result: {
      date: '2026-11-07', stadium_number: 1, race_number: 2,
      racers: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i + 1), {
        entry_number: i + 1, number: i + 3000, place_number: 6 - i,
        start_timing: 0.15,
      }])),
    },
  };
}

test('six validated finishing positions are result-only and unverified for the history chain', () => {
  const output = inspectSixFinishCandidate(record(), row, settled, 130_000);
  assert.equal(output.status, 'SHAPE_ONLY_UNVERIFIED');
  assert.deepEqual(output.candidate.finishOrder, [6, 5, 4, 3, 2, 1]);
  assert.deepEqual(output.candidate.registrationNumbersByLane, [3000, 3001, 3002, 3003, 3004, 3005]);
  assert.equal(JSON.stringify(output).includes('start_timing'), false);
  assert.equal(JSON.stringify(output).includes('national_win_rate'), false);
  assert.equal(JSON.stringify(output).includes('source_observed'), false);
});

test('absent or contradictory final six places never produce history candidates', () => {
  assert.equal(inspectSixFinishCandidate(record(), row, settled, 100_000).failureCode,
    'RESULT_CHECK_BEFORE_DEADLINE');
  const wrongDay = record();
  wrongDay.result.date = '2026-11-06';
  assert.equal(inspectSixFinishCandidate(wrongDay, row, settled, 130_000).failureCode,
    'RESULT_SIX_IDENTITY_MISMATCH');
  const missing = record();
  delete missing.result.racers['3'];
  assert.equal(inspectSixFinishCandidate(missing, row, settled, 130_000).failureCode,
    'RESULT_SIX_RACERS_MISSING');
  const swapped = record();
  swapped.result.racers['4'].number = 888;
  assert.equal(inspectSixFinishCandidate(swapped, row, settled, 130_000).failureCode,
    'RESULT_SIX_PLAYER_MISMATCH');
  const tie = record();
  tie.result.racers['3'].place_number = 6;
  assert.equal(inspectSixFinishCandidate(tie, row, settled, 130_000).failureCode,
    'RESULT_SIX_FINISH_ORDER_INVALID');
  const nonSettled = inspectSixFinishCandidate(null, row, { status: 'POSTPONED' }, 130_000);
  assert.deepEqual(nonSettled, { status: 'NON_SETTLED', failureCode: null, candidate: null });
});
