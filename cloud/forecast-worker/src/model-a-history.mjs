// Frozen Model A player history port of Android ModelAPlayerHistory and
// scripts/v016_r4_player_history.py. Snapshots are strictly pre-day; outcomes
// must be committed for a complete calendar day after all snapshots.

const PRIOR_COUNT = 20;
const MIN_SD = 0.02;
const WINDOWS = [30, 60, 90, 180];
const emptyStats = () => [0, 0, 0, 0, 0, 0, 0, 0];
const average = (a, b) => a.map((value, index) => (value + b[index]) / 2);

function rates(stats, prior) {
  return Array.from({ length: 3 }, (_, index) =>
    (stats[index + 1] + PRIOR_COUNT * prior[index]) / (stats[0] + PRIOR_COUNT));
}

function moments(stats, prior) {
  const n = stats[0];
  const out = [];
  for (let target = 0, offset = 4; offset <= 6; target += 2, offset += 2) {
    const priorMean = prior[target];
    const priorSd = prior[target + 1];
    const mean = (stats[offset] + PRIOR_COUNT * priorMean) / (n + PRIOR_COUNT);
    const variance = (stats[offset + 1] + PRIOR_COUNT * (priorSd * priorSd + priorMean * priorMean)) /
      (n + PRIOR_COUNT) - mean * mean;
    out.push(mean, Math.max(Math.sqrt(Math.max(variance, 0)), MIN_SD));
  }
  return out;
}

function lowerBound(sorted, target) {
  let low = 0;
  let high = sorted.length;
  while (low < high) {
    const mid = (low + high) >>> 1;
    if (sorted[mid] < target) low = mid + 1;
    else high = mid;
  }
  return low;
}

function checkSnapshotArgs({ player, course, exhibitionTime, previewStartTiming, day }, lastDay) {
  if (!Number.isInteger(player) || player <= 0 ||
      !Number.isInteger(course) || course < 1 || course > 6 ||
      !Number.isInteger(day) || day <= lastDay ||
      !Number.isFinite(exhibitionTime) || !Number.isFinite(previewStartTiming)) {
    throw new Error('MODEL_A_INVALID_HISTORY_SNAPSHOT');
  }
}

export class ModelAPlayerHistory {
  constructor(state = null) {
    this.state = state ?? { stats: Object.create(null), recent: Object.create(null), lastDay: 0, updateRaces: 0 };
    if (!this.state.stats || !this.state.recent || !Number.isInteger(this.state.lastDay) ||
        !Number.isInteger(this.state.updateRaces)) throw new Error('MODEL_A_INVALID_HISTORY_STATE');
  }

  get lastDay() { return this.state.lastDay; }
  get updateRaces() { return this.state.updateRaces; }
  get registeredPlayers() { return Object.keys(this.state.recent).length; }
  exportState() { return this.state; }

  get(key) { return this.state.stats[key] ?? emptyStats(); }

  snapshot({ player, course, racerClass, exhibitionTime, previewStartTiming, courseChanged, day }) {
    checkSnapshotArgs({ player, course, exhibitionTime, previewStartTiming, day }, this.lastDay);
    const p = String(player), c = String(course);
    const globalRate = rates(this.get('global'), [1 / 6, 1 / 3, 1 / 2]);
    const courseRate = rates(this.get(`c:${c}`), globalRate);
    const classRate = rates(this.get(`class:${racerClass}`), globalRate);
    const playerStats = this.get(`p:${p}`);
    const playerCourseStats = this.get(`pc:${p}:${c}`);
    const playerRate = rates(playerStats, average(courseRate, classRate));
    const playerCourseRate = rates(playerCourseStats, average(playerRate, courseRate));

    const globalMoments = moments(this.get('global'), [6.8, 0.15, 0.17, 0.08]);
    const courseMoments = moments(this.get(`c:${c}`), globalMoments);
    const playerMoments = moments(playerStats, globalMoments);
    const playerCourseMoments = moments(playerCourseStats, average(playerMoments, courseMoments));

    const history = [playerStats[0], ...playerRate, playerCourseStats[0], ...playerCourseRate,
      ...playerMoments, ...playerCourseMoments];
    const recent = this.state.recent[p] ?? { days: [], cumulative: [[0, 0, 0]] };
    for (const window of WINDOWS) {
      const left = lowerBound(recent.days, day - window);
      const count = recent.days.length - left;
      const total = recent.cumulative.at(-1);
      const before = recent.cumulative[left];
      const windowRates = Array.from({ length: 3 }, (_, index) =>
        (total[index] - before[index] + PRIOR_COUNT * playerRate[index]) / (count + PRIOR_COUNT));
      history.push(count, ...windowRates);
    }

    const fast = this.get(`fast:${p}:${c}`);
    const good = this.get(`good:${p}:${c}`);
    const changed = this.get(`changed:${p}`);
    const reaction = [
      exhibitionTime - playerMoments[0],
      (exhibitionTime - playerMoments[0]) / playerMoments[1],
      previewStartTiming - playerMoments[2],
      (previewStartTiming - playerMoments[2]) / playerMoments[3],
      exhibitionTime - playerCourseMoments[0],
      (exhibitionTime - playerCourseMoments[0]) / playerCourseMoments[1],
      previewStartTiming - playerCourseMoments[2],
      (previewStartTiming - playerCourseMoments[2]) / playerCourseMoments[3],
      fast[0], ...rates(fast, playerCourseRate),
      good[0], ...rates(good, playerCourseRate),
      changed[0], ...rates(changed, playerRate),
    ];
    if (history.length !== 32 || reaction.length !== 20) throw new Error('MODEL_A_HISTORY_WIDTH_MISMATCH');
    return {
      history: history.map(Math.fround), reaction: reaction.map(Math.fround),
      flags: {
        fastExhibition: exhibitionTime < playerMoments[0],
        goodPreviewStart: previewStartTiming < playerMoments[2],
        courseChanged: Boolean(courseChanged),
      },
    };
  }

  commitDay(day, updates) {
    if (!Number.isInteger(day) || day <= this.lastDay || !Array.isArray(updates) || updates.length % 6 !== 0) {
      throw new Error('MODEL_A_HISTORY_DAY_NOT_COMPLETE_OR_ORDERED');
    }
    // Validate all updates before mutating the state. A failed update must not
    // create a partially committed date, which would poison future features.
    for (const update of updates) {
      const { player, course, exhibitionTime, previewStartTiming, win, top2, top3, flags } = update ?? {};
      if (!Number.isInteger(player) || player <= 0 ||
          !Number.isInteger(course) || course < 1 || course > 6 ||
          !Number.isFinite(exhibitionTime) || !Number.isFinite(previewStartTiming) ||
          (win && !top2) || (top2 && !top3) ||
          !flags || typeof flags.fastExhibition !== 'boolean' ||
          typeof flags.goodPreviewStart !== 'boolean' || typeof flags.courseChanged !== 'boolean') {
        throw new Error('MODEL_A_INVALID_HISTORY_OUTCOME');
      }
    }
    for (const update of updates) {
      const { player, course, racerClass, exhibitionTime, previewStartTiming, flags } = update;
      const p = String(player), c = String(course);
      const keys = ['global', `c:${c}`, `class:${racerClass}`, `p:${p}`, `pc:${p}:${c}`];
      if (flags.fastExhibition) keys.push(`fast:${p}:${c}`);
      if (flags.goodPreviewStart) keys.push(`good:${p}:${c}`);
      if (flags.courseChanged) keys.push(`changed:${p}`);
      const y = [Number(Boolean(update.win)), Number(Boolean(update.top2)), Number(Boolean(update.top3))];
      for (const key of keys) {
        const stats = this.state.stats[key] ?? (this.state.stats[key] = emptyStats());
        stats[0]++;
        for (let index = 0; index < 3; index++) stats[index + 1] += y[index];
        stats[4] += exhibitionTime;
        stats[5] += exhibitionTime * exhibitionTime;
        stats[6] += previewStartTiming;
        stats[7] += previewStartTiming * previewStartTiming;
      }
      const recent = this.state.recent[p] ?? (this.state.recent[p] = { days: [], cumulative: [[0, 0, 0]] });
      recent.days.push(day);
      const previous = recent.cumulative.at(-1);
      recent.cumulative.push(previous.map((value, index) => value + y[index]));
    }
    this.state.lastDay = day;
    this.state.updateRaces += updates.length / 6;
  }
}
