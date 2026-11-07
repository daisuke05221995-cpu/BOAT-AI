// Offline/read-only research comparison against the *same unverified* public
// date feed that the Worker already uses for schedule/results. This cannot
// certify national coverage or reconstruct pre-close Model A history.
import { isValidDate, extractSchedule, raceId } from './policy.mjs';
import { normalizePublishedResult } from './result.mjs';
import { inspectSixFinishCandidate } from './six-finish-candidate.mjs';

const fail = code => { throw new Error(`HISTORY_GAP_DIAGNOSTIC_${code}`); };
const increment = (obj, key) => { obj[key] = (obj[key] ?? 0) + 1; };

function candidateAppearances(state, ordinal) {
  if (!Number.isInteger(state?.lastDay) || state.lastDay < ordinal ||
      !state.recent || typeof state.recent !== 'object') fail('CANDIDATE_NOT_UPDATED');
  const counts = new Map();
  for (const [player, item] of Object.entries(state.recent)) {
    if (!Array.isArray(item?.days)) fail('INVALID_CANDIDATE');
    const n = item.days.filter(day => day === ordinal).length;
    if (n) counts.set(player, n);
  }
  const appearances = [...counts.values()].reduce((sum, n) => sum + n, 0);
  if (appearances % 6 !== 0 || appearances > 6 * 288) fail('INVALID_APPEARANCE_COUNT');
  return { counts, appearances };
}

export function compareHistoryGapForResearch(feed, date, state, checkedMs) {
  if (!isValidDate(date) || !Number.isFinite(checkedMs) ||
      checkedMs < Date.parse(`${date}T15:00:00Z`)) fail('DAY_NOT_CLOSED');
  const ordinal = Math.trunc(Date.parse(`${date}T00:00:00Z`) / 86_400_000) + 719_163;
  const candidate = candidateAppearances(state, ordinal);
  const stadiums = feed?.programs?.stadiums;
  if (!stadiums || typeof stadiums !== 'object' || Array.isArray(stadiums)) fail('PROGRAM_MISSING');
  let publishedRows = 0;
  const ids = new Set();
  for (const [stadiumKey, venue] of Object.entries(stadiums)) {
    for (const [raceKey] of Object.entries(venue?.races ?? {})) {
      const id = raceId(date, Number(stadiumKey), Number(raceKey));
      if (!id || ids.has(id)) fail('PROGRAM_IDENTITY_INVALID_OR_DUPLICATE');
      ids.add(id);
      publishedRows++;
    }
  }
  if (publishedRows === 0 || publishedRows > 288) fail('PROGRAM_COUNT_INVALID');
  const scheduled = extractSchedule(feed, date);
  const classified = { settled: 0, non_settled: {}, result_unavailable: 0,
    full_six: 0, full_six_unavailable: {}, schedule_unparsed: publishedRows - scheduled.length };
  const expectedAppearances = new Map();
  const completeRaces = [];
  for (const row of scheduled) {
    const venue = stadiums[String(row.stadium_number)] ??
      stadiums[String(row.stadium_number).padStart(2, '0')];
    const raw = venue?.races?.[String(row.race_number)] ??
      venue?.races?.[String(row.race_number).padStart(2, '0')];
    const result = normalizePublishedResult(raw, row);
    if (!result) { classified.result_unavailable++; continue; }
    if (result.status !== 'SETTLED') {
      increment(classified.non_settled, result.status);
      continue;
    }
    classified.settled++;
    const six = inspectSixFinishCandidate(raw, row, result, checkedMs);
    if (six.status !== 'SHAPE_ONLY_UNVERIFIED') {
      increment(classified.full_six_unavailable, six.failureCode ?? 'UNKNOWN');
      continue;
    }
    classified.full_six++;
    const players = six.candidate.registrationNumbersByLane.map(String);
    completeRaces.push({ raceId: row.race_id, players });
    for (const player of players) expectedAppearances.set(player,
      (expectedAppearances.get(player) ?? 0) + 1);
  }
  const deficits = new Map(), surpluses = new Map();
  for (const player of new Set([...expectedAppearances.keys(), ...candidate.counts.keys()])) {
    const delta = (expectedAppearances.get(player) ?? 0) - (candidate.counts.get(player) ?? 0);
    if (delta > 0) deficits.set(player, delta);
    if (delta < 0) surpluses.set(player, -delta);
  }
  // An entrant can race twice in one day. These are only *suspect* races;
  // the BAH1 file has no race IDs, so never label them proved missing.
  const suspect = completeRaces.filter(race => race.players.some(player => deficits.has(player)))
    .map(race => ({ race_id: race.raceId,
      deficient_player_count: race.players.filter(player => deficits.has(player)).length }));
  suspect.sort((a, b) => b.deficient_player_count - a.deficient_player_count ||
    a.race_id.localeCompare(b.race_id));
  return {
    date, status: 'RESEARCH_SOURCE_AND_HISTORY_UNCERTIFIED',
    published_program_rows: publishedRows,
    scheduled_rows_parsed: scheduled.length,
    ...classified,
    candidate_history_races: candidate.appearances / 6,
    candidate_player_appearances: candidate.appearances,
    settled_minus_candidate: classified.settled - candidate.appearances / 6,
    verified_six_minus_candidate: classified.full_six - candidate.appearances / 6,
    deficient_player_appearances: [...deficits.values()].reduce((s, n) => s + n, 0),
    surplus_player_appearances: [...surpluses.values()].reduce((s, n) => s + n, 0),
    suspect_races_not_proven_missing: suspect,
    limitations: ['Public program feed is not an independent nationwide manifest',
      'Candidate BAH1 contains player/day appearances but no race IDs',
      'No original pre-close preview/odds timestamps or license certification',
      'Read-only comparison: never activate or backfill Model A history'],
  };
}
