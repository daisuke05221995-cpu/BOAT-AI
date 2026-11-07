import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectProgramRosterCandidate } from '../src/program-roster-candidate.mjs';

const row = {
  race_id: '2026-11-07-01-1', race_date: '2026-11-07',
  stadium_number: 1, race_number: 1, deadline_ms: 100_000,
};
function record() {
  return {
    date: '2026-11-07', stadium_number: 1, race_number: 1,
    racers: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i + 1), {
      entry_number: i + 1, number: i + 3001, rank_number: 2,
      national_win_rate: 5.4, national_top_2_percent: 33,
      motor_top_2_percent: null, weight: 52,
    }])),
    preview: { racers: { '1': { start_timing: 0.12 } } },
    result: { trifecta: '1-2-3', racers: {} },
  };
}

test('six program entrants become shape-only candidate; never copy preview, results or invent unknown stats', () => {
  const audit = inspectProgramRosterCandidate(record(), row, 90_000);
  assert.equal(audit.status, 'SHAPE_ONLY_UNVERIFIED');
  assert.equal(audit.failureCode, null);
  assert.equal(audit.candidate.racers.length, 6);
  assert.equal(audit.candidate.racers[0].registrationNumber, 3001);
  assert.equal(audit.candidate.racers[0].nationalTop2, 33);
  assert.equal(audit.candidate.racers[0].motorTop2, null);
  assert.equal(audit.candidate.racers[0].localWinRate, null);
  assert.equal(JSON.stringify(audit).includes('start_timing'), false);
  assert.equal(JSON.stringify(audit).includes('trifecta'), false);
  assert.equal(JSON.stringify(audit).includes('observed_at'), false);
});

test('after deadline, wrong race, roster gaps and duplicate IDs are rejected without a candidate', () => {
  assert.deepEqual(inspectProgramRosterCandidate(record(), row, 100_000), {
    status: 'UNAVAILABLE', failureCode: 'PROGRAM_CHECKED_AFTER_DEADLINE', candidate: null,
  });
  const wrong = record();
  wrong.stadium_number = 2;
  assert.equal(inspectProgramRosterCandidate(wrong, row, 90_000).failureCode, 'PROGRAM_IDENTITY_MISMATCH');
  const missing = record();
  delete missing.racers['4'];
  assert.equal(inspectProgramRosterCandidate(missing, row, 90_000).failureCode, 'PROGRAM_SIX_RACERS_MISSING');
  const duplicate = record();
  duplicate.racers['4'].number = duplicate.racers['1'].number;
  assert.equal(inspectProgramRosterCandidate(duplicate, row, 90_000).failureCode, 'PROGRAM_RACER_ID_INVALID');
  const badRate = record();
  badRate.racers['5'].national_win_rate = '5.4';
  assert.equal(inspectProgramRosterCandidate(badRate, row, 90_000).failureCode, 'PROGRAM_NATIONAL_WIN_RATE_MISSING');
});
