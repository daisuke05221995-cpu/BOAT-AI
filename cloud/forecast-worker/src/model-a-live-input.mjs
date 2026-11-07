// Strict, side-effect-free boundary for assembling *future* licensed race
// inputs. No network, D1, BUY/SKIP, model activation or live Worker wiring.
// An explicit operator-reviewed allowlist is mandatory; a provider's claimed
// `source: licensed` text alone does not establish legal permission.
import { verifiedPreviewPayload, verifiedOddsPayload, sourceTime } from './preclose.mjs';
import { inspectProgramRosterCandidate } from './program-roster-candidate.mjs';

const fail = code => { throw new Error(`MODEL_A_LIVE_INPUT_${code}`); };
const num = value => typeof value === 'number' && Number.isFinite(value) ? value : null;

function requireApproved(approvals, kind, source) {
  const approved = approvals?.[kind];
  if (!Array.isArray(approved) || !approved.length ||
      !approved.every(value => typeof value === 'string' && value.length > 0 && value.length <= 100) ||
      !approved.includes(source)) fail(`${kind.toUpperCase()}_SOURCE_NOT_APPROVED`);
}

export function assembleAuthorizedModelARace(row, rosterSnapshot, previewSnapshot,
  oddsSnapshot, nowMs, approvals = null) {
  if (!Number.isFinite(nowMs) || !Number.isFinite(row?.deadline_ms) ||
      nowMs >= row.deadline_ms) fail('CAPTURE_NOT_BEFORE_DEADLINE');
  if (!rosterSnapshot || rosterSnapshot.date !== row.race_date ||
      rosterSnapshot.stadium_number !== row.stadium_number ||
      rosterSnapshot.race_number !== row.race_number) fail('ROSTER_WRONG_RACE');
  requireApproved(approvals, 'roster', rosterSnapshot.source);
  requireApproved(approvals, 'preview', previewSnapshot?.source);
  requireApproved(approvals, 'weather', previewSnapshot?.preview?.weather_source);
  requireApproved(approvals, 'odds', oddsSnapshot?.source);

  const rosterObservedMs = sourceTime(rosterSnapshot.observed_at, nowMs,
    row.deadline_ms, 'ROSTER');
  const checked = inspectProgramRosterCandidate(rosterSnapshot.roster, row, nowMs);
  if (checked.status !== 'SHAPE_ONLY_UNVERIFIED') fail(checked.failureCode ?? 'ROSTER_NOT_COMPLETE');

  // Each observation is validated independently against the same canonical
  // date, venue, race and deadline, with source clocks <=2 minutes old.
  const exhibition = verifiedPreviewPayload(previewSnapshot, row, nowMs);
  const book = verifiedOddsPayload(oddsSnapshot, row, nowMs);
  const racers = checked.candidate.racers.map(racer => {
    const raw = exhibition.preview.racers[String(racer.lane)];
    // A separate exhibition provider must identify the exact registered
    // entrant; matching only lane or course can miss a late substitute.
    if (!Number.isInteger(raw.number) || raw.number !== racer.registrationNumber) {
      fail('PREVIEW_PLAYER_ID_MISMATCH');
    }
    return { ...racer, preview: {
      course: raw.course_number, exhibitionTime: raw.exhibition_time,
      startTiming: raw.start_timing, tilt: num(raw.tilt_adjustment),
      weightAdjustment: num(raw.weight_adjustment),
    } };
  });
  const preview = exhibition.preview;
  return {
    race: { date: row.race_date, stadiumNumber: row.stadium_number,
      raceNumber: row.race_number, racers,
      preview: { windSpeed: preview.wind_speed, waveHeight: preview.wave_height,
        airTemperature: preview.air_temperature, waterTemperature: preview.water_temperature,
        windDirectionNumber: preview.wind_direction_number } },
    odds: book.odds,
    provenance: { rosterSource: rosterSnapshot.source, rosterObservedMs,
      previewSource: exhibition.source, previewObservedMs: exhibition.observedMs,
      weatherSource: exhibition.weatherSource, weatherObservedMs: exhibition.weatherObservedMs,
      oddsSource: book.source, oddsObservedMs: book.observedMs,
      validatedAtMs: nowMs },
    inputContractVerified: true,
    forecastEnabled: false, // history and real Android parity still required.
  };
}
