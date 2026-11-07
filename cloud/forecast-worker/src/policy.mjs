export const EIGHT_MIN = 8 * 60_000;
export const FIVE_MIN = 5 * 60_000;
export const SCHEDULE_REFRESH_MS = 60 * 60_000;

export function japanDate(nowMs) {
  return new Date(nowMs).toLocaleDateString('sv-SE', { timeZone: 'Asia/Tokyo' });
}

export function parseJstDeadline(value) {
  if (typeof value !== 'string') return null;
  const matched = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?$/.exec(value);
  if (!matched) return null;
  const [, y, mo, d, h, mi, s] = matched.map(String);
  const ms = Date.parse(`${y}-${mo}-${d}T${h}:${mi}:${s}+09:00`);
  if (!Number.isFinite(ms)) return null;
  const roundtrip = new Date(ms).toLocaleString('sv-SE', { timeZone: 'Asia/Tokyo', hour12: false });
  return roundtrip.replace(' ', 'T') === `${y}-${mo}-${d}T${h}:${mi}:${s}` ? ms : null;
}

export function raceId(date, stadium, race) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isInteger(stadium) || stadium < 1 || stadium > 24 || !Number.isInteger(race) || race < 1 || race > 12) return null;
  return `${date}-${String(stadium).padStart(2, '0')}-${race}`;
}

// 0: no attempt, 1: initial attempt made, 2: one final attempt made.
// Never return an action at or after the official deadline.
export function nextCaptureStage({ capture_stage: stage, deadline_ms: deadline }, nowMs) {
  if (!Number.isFinite(deadline) || nowMs >= deadline || nowMs < deadline - EIGHT_MIN) return null;
  if (stage === 0) return nowMs >= deadline - FIVE_MIN ? 2 : 1;
  if (stage === 1 && nowMs >= deadline - FIVE_MIN) return 2;
  return null;
}

export function isValidDate(date) {
  if (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return false;
  return !Number.isNaN(Date.parse(`${date}T00:00:00Z`)) && new Date(`${date}T00:00:00Z`).toISOString().slice(0, 10) === date;
}

export function extractSchedule(json, date) {
  const stadiums = json?.programs?.stadiums;
  if (!stadiums || typeof stadiums !== 'object') return [];
  const races = [];
  for (const [stadiumRaw, venue] of Object.entries(stadiums)) {
    const stadium = Number(stadiumRaw);
    for (const [raceRaw, entry] of Object.entries(venue?.races ?? {})) {
      const race = Number(raceRaw);
      const id = raceId(date, stadium, race);
      const deadline = parseJstDeadline(entry?.closed_at);
      if (id && deadline != null && entry?.date === date) {
        races.push({ race_id: id, race_date: date, stadium_number: stadium, race_number: race, deadline_ms: deadline });
      }
    }
  }
  return races;
}

export function validOdds(snapshot) {
  const odds = snapshot?.odds;
  if (!odds || typeof odds !== 'object' || Array.isArray(odds)) return false;
  const keys = Object.keys(odds);
  // Model A/value selection needs every three-way combination. Never treat a
  // partial 100–119-way book as complete, even if its selected picks are present.
  if (keys.length !== 120) return false;
  return keys.every(k => {
    if (!/^[1-6]-[1-6]-[1-6]$/.test(k)) return false;
    const [a, b, c] = k.split('-');
    return a !== b && b !== c && a !== c && typeof odds[k] === 'number' && Number.isFinite(odds[k]) && odds[k] > 0;
  });
}
