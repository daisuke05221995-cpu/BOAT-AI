// Dormant, hash-checked D1 history checkpoint store. No cron, public API or
// forecast path calls this until licensed, complete source data is available.
import { encodeModelAHistoryAsset, decodeModelAHistoryAsset,
  verifyModelAHistoryAsset } from './model-a-history-codec.mjs';

export const HISTORY_CHUNK_BYTES = 512 * 1024;
export const HISTORY_SQL_LITERAL_CHARS = 64 * 1024;
export const FROZEN_ANDROID_HISTORY_BASE = Object.freeze({
  bytes: 4_222_646,
  sha256: 'a180aa722ad0520b5d86705bac742ff588309e72a49bed373eabf102f257acc3',
  throughDay: 739_882,
  updateRaces: 141_542,
  chunkCount: 9,
});
const HEX64 = /^[0-9a-f]{64}$/;
const fail = code => { throw new Error(`MODEL_A_CHECKPOINT_${code}`); };
const digest = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
  value => value.toString(16).padStart(2, '0')).join('');

function toBase64(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  }
  return btoa(binary);
}

function fromBase64(value) {
  if (typeof value !== 'string' || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) {
    fail('INVALID_CHUNK');
  }
  const decoded = atob(value);
  const bytes = new Uint8Array(decoded.length);
  for (let i = 0; i < decoded.length; i++) bytes[i] = decoded.charCodeAt(i);
  return bytes;
}

async function seal(bytes, { kind, previousSha256, audit }) {
  const state = decodeModelAHistoryAsset(bytes);
  if (!audit || !Number.isInteger(state.lastDay) ||
      (kind === 'RECONCILED_DAY' &&
        (audit.status !== 'VALIDATED_AGAINST_SUPPLIED_MANIFEST' ||
         audit.historyLastDay !== state.lastDay || audit.committedRaces < 0 ||
         !Number.isInteger(audit.committedRaces) || !HEX64.test(previousSha256 ?? ''))) ||
      (kind === 'FROZEN_BASE' &&
        (audit.status !== 'VERIFIED_ANDROID_BASE' || previousSha256 !== null))) fail('INVALID_AUDIT');
  const chunks = [];
  for (let i = 0; i < bytes.length; i += HISTORY_CHUNK_BYTES) {
    const part = bytes.slice(i, i + HISTORY_CHUNK_BYTES);
    chunks.push({ index: chunks.length, sha256: await digest(part), base64: toBase64(part) });
  }
  return {
    sha256: await digest(bytes), previousSha256, kind, throughDay: state.lastDay,
    updateRaces: state.updateRaces, byteLength: bytes.length, chunks, audit,
    auditSha256: await digest(new TextEncoder().encode(JSON.stringify(audit))),
  };
}

export async function sealAndroidHistoryBase(bytes, expectedManifest) {
  const state = await verifyModelAHistoryAsset(bytes, expectedManifest);
  const checkpoint = await seal(bytes, { kind: 'FROZEN_BASE', previousSha256: null,
    audit: { status: 'VERIFIED_ANDROID_BASE', historyLastDay: state.lastDay,
      sourceAssetSha256: expectedManifest.sha256 } });
  if (checkpoint.sha256 !== expectedManifest.sha256) fail('BASE_DIGEST_MISMATCH');
  return checkpoint;
}

// Authenticated Wrangler bootstrap for the exact frozen Android BAH1 history
// only. No active pointer, cron registration, history-day promotion or forecast
// mutation. D1 SQL text is limited to 100KB per statement. Repeated partial
// imports are safe: each append requires the expected existing string length.
export function renderFrozenHistoryBaseSql(checkpoint, stagedMs = Date.now()) {
  const fixed = FROZEN_ANDROID_HISTORY_BASE;
  if (checkpoint?.sha256 !== fixed.sha256 || checkpoint?.kind !== 'FROZEN_BASE' ||
      checkpoint.previousSha256 !== null || checkpoint.throughDay !== fixed.throughDay ||
      checkpoint.updateRaces !== fixed.updateRaces || checkpoint.byteLength !== fixed.bytes ||
      checkpoint.chunks?.length !== fixed.chunkCount ||
      checkpoint.audit?.status !== 'VERIFIED_ANDROID_BASE' ||
      checkpoint.audit?.sourceAssetSha256 !== fixed.sha256 ||
      checkpoint.audit?.historyLastDay !== fixed.throughDay ||
      !HEX64.test(checkpoint.auditSha256 ?? '') ||
      !Number.isSafeInteger(stagedMs) || stagedMs < 0) fail('INVALID_SQL_EXPORT');
  const quote = value => `'${String(value).replaceAll("'", "''")}'`;
  const statements = [
    `INSERT OR IGNORE INTO model_a_history_generation (sha256, previous_sha256, kind, through_day, update_races, byte_length, chunk_count, audit_json, audit_sha256, staged_ms) VALUES (${quote(checkpoint.sha256)}, NULL, 'FROZEN_BASE', ${fixed.throughDay}, ${fixed.updateRaces}, ${fixed.bytes}, ${fixed.chunkCount}, ${quote(JSON.stringify(checkpoint.audit))}, ${quote(checkpoint.auditSha256)}, ${stagedMs});`,
  ];
  for (let index = 0; index < fixed.chunkCount; index++) {
    const part = checkpoint.chunks[index];
    if (part?.index !== index || !HEX64.test(part.sha256 ?? '') ||
        typeof part.base64 !== 'string' ||
        !/^[A-Za-z0-9+/]+={0,2}$/.test(part.base64)) fail('INVALID_SQL_EXPORT');
    statements.push(`INSERT OR IGNORE INTO model_a_history_chunk (sha256, chunk_index, chunk_sha256, base64_data) VALUES (${quote(fixed.sha256)}, ${index}, ${quote(part.sha256)}, '');`);
    for (let offset = 0; offset < part.base64.length; offset += HISTORY_SQL_LITERAL_CHARS) {
      const value = part.base64.slice(offset, offset + HISTORY_SQL_LITERAL_CHARS);
      statements.push(`UPDATE model_a_history_chunk SET base64_data=base64_data || ${quote(value)} WHERE sha256=${quote(fixed.sha256)} AND chunk_index=${index} AND length(base64_data)=${offset};`);
    }
  }
  if (statements.some(statement => new TextEncoder().encode(statement).length > 100_000)) {
    fail('SQL_STATEMENT_TOO_LARGE');
  }
  return `${statements.join('\n')}\n`;
}

export async function sealReconciledHistoryDay({ state, audit }, previousSha256) {
  return seal(encodeModelAHistoryAsset(state),
    { kind: 'RECONCILED_DAY', previousSha256, audit });
}

// Transactional staging: an unverified or partially written generation cannot
// replace the active pointer. Every chunk and the manifest commit together.
export async function stageHistoryCheckpoint(db, checkpoint, stagedMs = Date.now()) {
  if (!HEX64.test(checkpoint?.sha256 ?? '') || !Number.isFinite(stagedMs) ||
      !Array.isArray(checkpoint.chunks) || checkpoint.chunks.length === 0 ||
      !Number.isInteger(checkpoint.byteLength) || checkpoint.byteLength <= 0) fail('INVALID_STAGE');
  const insertGeneration = db.prepare(`INSERT INTO model_a_history_generation
    (sha256, previous_sha256, kind, through_day, update_races, byte_length, chunk_count,
      audit_json, audit_sha256, staged_ms)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(checkpoint.sha256, checkpoint.previousSha256, checkpoint.kind,
      checkpoint.throughDay, checkpoint.updateRaces, checkpoint.byteLength,
      checkpoint.chunks.length, JSON.stringify(checkpoint.audit), checkpoint.auditSha256, stagedMs);
  const insertChunk = db.prepare(`INSERT INTO model_a_history_chunk
    (sha256, chunk_index, chunk_sha256, base64_data) VALUES (?, ?, ?, ?)`);
  await db.batch([insertGeneration, ...checkpoint.chunks.map(chunk => insertChunk.bind(
    checkpoint.sha256, chunk.index, chunk.sha256, chunk.base64))]);
}

export async function loadVerifiedHistoryCheckpoint(db, sha256) {
  if (!HEX64.test(sha256 ?? '')) fail('INVALID_ID');
  const meta = await db.prepare('SELECT * FROM model_a_history_generation WHERE sha256=?').bind(sha256).first();
  if (!meta) fail('NOT_FOUND');
  const { results: rows } = await db.prepare(`SELECT chunk_index, chunk_sha256, base64_data
    FROM model_a_history_chunk WHERE sha256=? ORDER BY chunk_index`).bind(sha256).all();
  if (!rows || rows.length !== meta.chunk_count || rows.length === 0) fail('CHUNK_MISSING');
  const parts = [];
  let length = 0;
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].chunk_index !== i) fail('CHUNK_SEQUENCE');
    const part = fromBase64(rows[i].base64_data);
    if (!part.length || part.length > HISTORY_CHUNK_BYTES ||
        await digest(part) !== rows[i].chunk_sha256) fail('CHUNK_CORRUPT');
    parts.push(part);
    length += part.length;
  }
  if (length !== meta.byte_length) fail('LENGTH_MISMATCH');
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const part of parts) { bytes.set(part, offset); offset += part.length; }
  if (await digest(bytes) !== meta.sha256) fail('DIGEST_MISMATCH');
  const state = decodeModelAHistoryAsset(bytes);
  if (state.lastDay !== meta.through_day || state.updateRaces !== meta.update_races) fail('STATE_MISMATCH');
  let audit;
  if (await digest(new TextEncoder().encode(meta.audit_json)) !== meta.audit_sha256) fail('AUDIT_CORRUPT');
  try { audit = JSON.parse(meta.audit_json); } catch { fail('INVALID_AUDIT'); }
  if (!audit || audit.historyLastDay !== state.lastDay ||
      !['VERIFIED_ANDROID_BASE', 'VALIDATED_AGAINST_SUPPLIED_MANIFEST'].includes(audit.status)) fail('INVALID_AUDIT');
  return { state, bytes, audit, sha256: meta.sha256, previousSha256: meta.previous_sha256,
    kind: meta.kind, throughDay: state.lastDay, updateRaces: state.updateRaces };
}

// Optimistic compare-and-swap prevents racing cron invocations from overriding
// a newer or different history generation. Never auto-prune old generations.
export async function activateVerifiedHistoryCheckpoint(db, sha256, activatedMs = Date.now()) {
  if (!Number.isFinite(activatedMs)) fail('INVALID_CLOCK');
  const candidate = await loadVerifiedHistoryCheckpoint(db, sha256);
  const current = await db.prepare('SELECT * FROM model_a_history_active WHERE singleton=1').first();
  let result;
  if (!current) {
    if (candidate.kind !== 'FROZEN_BASE' || candidate.previousSha256 !== null) fail('NO_BASE');
    result = await db.prepare(`INSERT INTO model_a_history_active (singleton, sha256, through_day, activated_ms)
      SELECT 1, ?, ?, ? WHERE NOT EXISTS (SELECT 1 FROM model_a_history_active WHERE singleton=1)`)
      .bind(sha256, candidate.throughDay, activatedMs).run();
  } else {
    if (candidate.kind !== 'RECONCILED_DAY' || candidate.previousSha256 !== current.sha256 ||
        candidate.throughDay !== current.through_day + 1) fail('NONCONSECUTIVE');
    result = await db.prepare(`UPDATE model_a_history_active SET sha256=?, through_day=?, activated_ms=?
      WHERE singleton=1 AND sha256=? AND through_day=?`)
      .bind(sha256, candidate.throughDay, activatedMs, current.sha256, current.through_day).run();
  }
  if (result.meta?.changes !== 1) fail('CONCURRENT_UPDATE');
  return { sha256, throughDay: candidate.throughDay };
}
