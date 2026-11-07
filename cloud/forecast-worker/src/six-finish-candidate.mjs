// Result-only research metadata. Program/result identities must agree on all
// six entrants and final places. This is not a certified nationwide manifest
// and is NEVER a pre-close feature or an active Model A history update.
const unavailable = code => ({ status: 'UNAVAILABLE', failureCode: code, candidate: null });

export function inspectSixFinishCandidate(raw, row, settlement, checkedMs) {
  if (!settlement || !Number.isFinite(checkedMs) ||
      !Number.isFinite(row?.deadline_ms) || checkedMs <= row.deadline_ms) {
    return unavailable('RESULT_CHECK_BEFORE_DEADLINE');
  }
  if (settlement.status !== 'SETTLED') {
    return { status: 'NON_SETTLED', failureCode: null, candidate: null };
  }
  if (!raw || raw.date !== row.race_date || raw.stadium_number !== row.stadium_number ||
      raw.race_number !== row.race_number ||
      raw.result?.date !== row.race_date ||
      raw.result?.stadium_number !== row.stadium_number ||
      raw.result?.race_number !== row.race_number) {
    return unavailable('RESULT_SIX_IDENTITY_MISMATCH');
  }
  const program = raw.racers, finish = raw.result.racers;
  if (!program || !finish || typeof program !== 'object' || Array.isArray(program) ||
      typeof finish !== 'object' || Array.isArray(finish) ||
      Object.keys(program).length !== 6 || Object.keys(finish).length !== 6) {
    return unavailable('RESULT_SIX_RACERS_MISSING');
  }
  const seenPlayers = new Set(), seenPlaces = new Set();
  const numbersByLane = [], finishingLanes = new Array(6);
  for (let lane = 1; lane <= 6; lane++) {
    const p = program[String(lane)], r = finish[String(lane)];
    if (!p || !r || p.entry_number !== lane || r.entry_number !== lane ||
        !Number.isInteger(p.number) || p.number <= 0 || seenPlayers.has(p.number) ||
        r.number !== p.number) return unavailable('RESULT_SIX_PLAYER_MISMATCH');
    if (!Number.isInteger(r.place_number) || r.place_number < 1 || r.place_number > 6 ||
        seenPlaces.has(r.place_number)) return unavailable('RESULT_SIX_FINISH_ORDER_INVALID');
    seenPlayers.add(p.number);
    seenPlaces.add(r.place_number);
    numbersByLane.push(p.number);
    finishingLanes[r.place_number - 1] = lane;
  }
  return { status: 'SHAPE_ONLY_UNVERIFIED', failureCode: null,
    candidate: { date: row.race_date, stadiumNumber: row.stadium_number,
      raceNumber: row.race_number, registrationNumbersByLane: numbersByLane,
      finishOrder: finishingLanes } };
}
