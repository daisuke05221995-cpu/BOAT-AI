// Reads Android's lossless ModelAHistoryStateCodec BAH1 format. Inputs must be
// immutable deployment assets verified with the SHA-256 from deployment.json.
// A decoded history is not by itself proof that the preceding day is complete.

const MAX_STRING_BYTES = 1_000_000;
const MAX_ENTRIES = 1_000_000;
const MAX_APPEARANCES = 30_000_000;
const utf8 = new TextDecoder('utf-8', { fatal: true });

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
