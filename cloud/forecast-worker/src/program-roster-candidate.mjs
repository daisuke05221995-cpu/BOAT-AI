// The low-frequency program feed is useful for *shape/coverage research*, but
// is NOT a certified pre-close input source. Nothing from this module may be
// passed to Model A until a separate source/time/identity audit is implemented.
const numeric = value => typeof value === 'number' && Number.isFinite(value) ? value : null;

function unavailable(code) {
  return { status: 'UNAVAILABLE', failureCode: code, candidate: null };
}

export function inspectProgramRosterCandidate(raw, row, checkedMs) {
  if (!Number.isFinite(checkedMs) || !Number.isFinite(row?.deadline_ms) ||
      checkedMs >= row.deadline_ms) return unavailable('PROGRAM_CHECKED_AFTER_DEADLINE');
  if (!raw || raw.date !== row.race_date || raw.stadium_number !== row.stadium_number ||
      raw.race_number !== row.race_number) return unavailable('PROGRAM_IDENTITY_MISMATCH');

  const racers = raw.racers;
  if (!racers || typeof racers !== 'object' || Array.isArray(racers) ||
      Object.keys(racers).length !== 6) return unavailable('PROGRAM_SIX_RACERS_MISSING');

  const seen = new Set();
  const normalized = [];
  for (let lane = 1; lane <= 6; lane++) {
    const racer = racers[String(lane)];
    if (!racer || racer.entry_number !== lane ||
        !Number.isInteger(racer.number) || racer.number <= 0 || seen.has(racer.number)) {
      return unavailable('PROGRAM_RACER_ID_INVALID');
    }
    const nationalWinRate = numeric(racer.national_win_rate);
    if (nationalWinRate === null) return unavailable('PROGRAM_NATIONAL_WIN_RATE_MISSING');
    seen.add(racer.number);
    normalized.push({
      lane, registrationNumber: racer.number,
      classNumber: Number.isInteger(racer.rank_number) && racer.rank_number >= 1 && racer.rank_number <= 4
        ? racer.rank_number : null,
      nationalWinRate,
      nationalTop2: numeric(racer.national_top_2_percent),
      nationalTop3: numeric(racer.national_top_3_percent),
      localWinRate: numeric(racer.local_win_rate),
      localTop2: numeric(racer.local_top_2_percent),
      localTop3: numeric(racer.local_top_3_percent),
      motorTop2: numeric(racer.motor_top_2_percent),
      motorTop3: numeric(racer.motor_top_3_percent),
      boatTop2: numeric(racer.boat_top_2_percent),
      boatTop3: numeric(racer.boat_top_3_percent),
      averageStart: numeric(racer.average_start_timing),
      flyingCount: numeric(racer.flying_count),
      lateCount: numeric(racer.late_count),
      age: numeric(racer.age), weight: numeric(racer.weight),
    });
  }

  // Do not include raw.preview, raw.result, inferred start/course, weather,
  // a fabricated source observation timestamp, or synthetic missing values.
  return {
    status: 'SHAPE_ONLY_UNVERIFIED', failureCode: null,
    candidate: { date: row.race_date, stadiumNumber: row.stadium_number,
      raceNumber: row.race_number, racers: normalized },
  };
}
