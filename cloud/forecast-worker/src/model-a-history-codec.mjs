// Reads Android's lossless ModelAHistoryStateCodec BAH1 format. Inputs must be
// immutable deployment assets verified with the SHA-256 from deployment.json.
// A decoded history is not by itself proof that the preceding day is complete.

const MAX_STRING_BYTES = 1_000_000;
const MAX_ENTRIES = 1_000_000;
const MAX_APPEARANCES = 30_000_000;
const utf8 = new TextDecoder('utf-8', { fatal: true });
const encoder = new TextEncoder();

class ByteWriter {
  constructor() { this.bytes = new Uint8Array(1024); this.size = 0; }
  reserve(size) {
    if (this.size + size <= this.bytes.length) return;
    let capacity = this.bytes.length;
    while (capacity < this.size + size) capacity *= 2;
    const grown = new Uint8Array(capacity);
    grown.set(this.bytes);
    this.bytes = grown;
  }
  raw(bytes) { this.reserve(bytes.length); this.bytes.set(bytes, this.size); this.size += bytes.length; }
  byte(value) { this.reserve(1); this.bytes[this.size++] = value; }
  int(value) { this.reserve(4); new DataView(this.bytes.buffer).setInt32(this.size, value, false); this.size += 4; }
  double(value) { this.reserve(8); new DataView(this.bytes.buffer).setFloat64(this.size, value, false); this.size += 8; }
  varint(input) {
    if (!Number.isSafeInteger(input) || input < 0 || input > 0x7fffffff) {
      throw new Error('MODEL_A_HISTORY_BAD_VARINT');
    }
    let value = input;
    while (value >= 128) { this.byte((value & 0x7f) | 0x80); value = Math.floor(value / 128); }
    this.byte(value);
  }
  string(value) {
    if (typeof value !== 'string') throw new Error('MODEL_A_HISTORY_INVALID_KEY');
    const bytes = encoder.encode(value);
    if (bytes.length > MAX_STRING_BYTES) throw new Error('MODEL_A_HISTORY_STRING_TOO_LARGE');
    this.varint(bytes.length);
    this.raw(bytes);
  }
  finish() { return this.bytes.slice(0, this.size); }
}

// Android ModelAHistoryStateCodec BAH1 writer: sorted stats/player keys,
// BE doubles, unsigned delta varints and finish-flag bytes. Never replace the
// immutable base asset in place. Seal a new generation with a digest first.
export function encodeModelAHistoryAsset(state) {
  if (!state || !Number.isInteger(state.lastDay) || state.lastDay < 0 ||
      !Number.isInteger(state.updateRaces) || state.updateRaces < 0 ||
      !state.stats || !state.recent ||
      typeof state.stats !== 'object' || typeof state.recent !== 'object') {
    throw new Error('MODEL_A_HISTORY_INVALID_STATE');
  }
  const stats = Object.keys(state.stats).sort();
  const players = Object.keys(state.recent).sort();
  if (stats.length > MAX_ENTRIES || players.length > MAX_ENTRIES) {
    throw new Error('MODEL_A_HISTORY_BAD_ENTRY_COUNT');
  }
  const writer = new ByteWriter();
  writer.raw(Uint8Array.from([66, 65, 72, 49]));
  writer.int(1);
  writer.int(state.lastDay);
  writer.int(state.updateRaces);
  writer.int(stats.length);
  for (const key of stats) {
    const row = state.stats[key];
    if (!Array.isArray(row) || row.length !== 8 ||
        row.some(value => typeof value !== 'number' || !Number.isFinite(value)) ||
        !Number.isSafeInteger(row[0]) || row[0] < 0 ||
        row.slice(1, 4).some(value => value < 0 || value > row[0])) {
      throw new Error('MODEL_A_HISTORY_INVALID_STAT');
    }
    writer.string(key);
    for (const value of row) writer.double(value);
  }
  writer.int(players.length);
  let appearances = 0;
  for (const player of players) {
    const recent = state.recent[player];
    if (!Array.isArray(recent?.days) || !Array.isArray(recent.cumulative) ||
        recent.cumulative.length !== recent.days.length + 1 ||
        !Array.isArray(recent.cumulative[0]) ||
        recent.cumulative[0].length !== 3 ||
        recent.cumulative[0].some(value => value !== 0)) {
      throw new Error('MODEL_A_HISTORY_INVALID_RECENT');
    }
    appearances += recent.days.length;
    if (appearances > MAX_APPEARANCES) throw new Error('MODEL_A_HISTORY_TOO_MANY_APPEARANCES');
    writer.string(player);
    writer.varint(recent.days.length);
    let previousDay = 0, previous = [0, 0, 0];
    for (let i = 0; i < recent.days.length; i++) {
      const day = recent.days[i], current = recent.cumulative[i + 1];
      if (!Number.isInteger(day) || day < previousDay || day > state.lastDay ||
          !Array.isArray(current) || current.length !== 3) {
        throw new Error('MODEL_A_HISTORY_INVALID_RECENT');
      }
      const increments = current.map((value, index) => value - previous[index]);
      if (!increments.every(value => value === 0 || value === 1) ||
          increments[0] > increments[1] || increments[1] > increments[2]) {
        throw new Error('MODEL_A_HISTORY_INVALID_OUTCOME_FLAGS');
      }
      writer.varint(day - previousDay);
      writer.byte(increments[0] | (increments[1] << 1) | (increments[2] << 2));
      previousDay = day;
      previous = current;
    }
  }
  if (appearances !== state.updateRaces * 6) {
    throw new Error('MODEL_A_HISTORY_APPEARANCE_MISMATCH');
  }
  return writer.finish();
}

function asBytes(input) {
  if (input instanceof Uint8Array) return input;
  if (input instanceof ArrayBuffer) return new Uint8Array(input);
  throw new Error('MODEL_A_HISTORY_NOT_BINARY');
}

export function decodeModelAHistoryAsset(input) {
  const bytes = asBytes(input);
  if (bytes.byteLength < 24) throw new Error('MODEL_A_HISTORY_TRUNCATED');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 0;
  const take = size => {
    if (!Number.isInteger(size) || size < 0 || size > bytes.byteLength - offset) {
      throw new Error('MODEL_A_HISTORY_TRUNCATED');
    }
    const start = offset;
    offset += size;
    return start;
  };
  const int32 = () => view.getInt32(take(4), false);
  const float64 = () => {
    const number = view.getFloat64(take(8), false);
    if (!Number.isFinite(number)) throw new Error('MODEL_A_HISTORY_INVALID_STAT');
    return number;
  };
  const unsignedVarint = () => {
    let result = 0;
    for (let index = 0; index < 5; index++) {
      const value = view.getUint8(take(1));
      if (index === 4 && value > 7) throw new Error('MODEL_A_HISTORY_BAD_VARINT');
      result += (value & 0x7f) * (2 ** (7 * index));
      if (!(value & 0x80)) return result;
    }
    throw new Error('MODEL_A_HISTORY_BAD_VARINT');
  };
  const string = () => {
    const size = unsignedVarint();
    if (size > MAX_STRING_BYTES) throw new Error('MODEL_A_HISTORY_STRING_TOO_LARGE');
    const start = take(size);
    return utf8.decode(bytes.subarray(start, start + size));
  };
  const count = () => {
    const value = int32();
    if (value < 0 || value > MAX_ENTRIES) throw new Error('MODEL_A_HISTORY_BAD_ENTRY_COUNT');
    return value;
  };

  if (String.fromCharCode(...bytes.subarray(0, 4)) !== 'BAH1') {
    throw new Error('MODEL_A_HISTORY_BAD_MAGIC');
  }
  take(4);
  if (int32() !== 1) throw new Error('MODEL_A_HISTORY_UNSUPPORTED_VERSION');
  const lastDay = int32(), updateRaces = int32();
  if (lastDay < 0 || updateRaces < 0) throw new Error('MODEL_A_HISTORY_INVALID_DAY');

  const stats = Object.create(null);
  const statCount = count();
  for (let i = 0; i < statCount; i++) {
    const key = string();
    if (Object.hasOwn(stats, key)) throw new Error('MODEL_A_HISTORY_DUPLICATE_STAT');
    const row = Array.from({ length: 8 }, float64);
    if (!Number.isInteger(row[0]) || row[0] < 0 ||
        row.slice(1, 4).some(v => v < 0 || v > row[0])) throw new Error('MODEL_A_HISTORY_INVALID_STAT');
    stats[key] = row;
  }
  const recent = Object.create(null);
  const playerCount = count();
  let appearances = 0;
  for (let i = 0; i < playerCount; i++) {
    const player = string();
    if (Object.hasOwn(recent, player)) throw new Error('MODEL_A_HISTORY_DUPLICATE_PLAYER');
    const size = unsignedVarint();
    appearances += size;
    if (appearances > MAX_APPEARANCES) throw new Error('MODEL_A_HISTORY_TOO_MANY_APPEARANCES');
    const days = [];
    const cumulative = [[0, 0, 0]];
    let day = 0;
    for (let j = 0; j < size; j++) {
      day += unsignedVarint();
      if (day > lastDay) throw new Error('MODEL_A_HISTORY_FUTURE_APPEARANCE');
      days.push(day);
      const flags = view.getUint8(take(1));
      if (![0, 4, 6, 7].includes(flags)) throw new Error('MODEL_A_HISTORY_BAD_OUTCOME_FLAGS');
      const prior = cumulative.at(-1);
      cumulative.push([prior[0] + (flags & 1), prior[1] + ((flags >> 1) & 1),
        prior[2] + ((flags >> 2) & 1)]);
    }
    recent[player] = { days, cumulative };
  }
  if (offset !== bytes.byteLength) throw new Error('MODEL_A_HISTORY_TRAILING_BYTES');
  if (appearances !== updateRaces * 6) throw new Error('MODEL_A_HISTORY_APPEARANCE_MISMATCH');
  return { stats, recent, lastDay, updateRaces };
}

export async function verifyModelAHistoryAsset(input, manifest) {
  const bytes = asBytes(input);
  if (!manifest || !Number.isInteger(manifest.bytes) || bytes.byteLength !== manifest.bytes ||
      typeof manifest.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(manifest.sha256)) {
    throw new Error('MODEL_A_HISTORY_ASSET_MANIFEST_MISMATCH');
  }
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const actual = Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('');
  if (actual !== manifest.sha256) throw new Error('MODEL_A_HISTORY_ASSET_SHA256_MISMATCH');
  return decodeModelAHistoryAsset(bytes);
}
