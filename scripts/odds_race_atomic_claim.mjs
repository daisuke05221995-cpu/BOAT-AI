import { createHash } from 'node:crypto';
import { mkdir, readFile, link, open } from 'node:fs/promises';
import { join } from 'node:path';
// Offline research only. Claiming a race is never authorization to BUY/SKIP or wager.
const hash = value => createHash('sha256').update(value).digest('hex');
const valid = value => typeof value === 'string' && /^[A-Za-z0-9_-]{8,128}$/.test(value);
export async function claimQuarantinedRace(directory, receiptId, raceKey) {
  if (!valid(receiptId) || !valid(raceKey)) return { status: 'UNAVAILABLE', reason: 'INVALID_ID' };
  const receiptFile = join(directory, hash(receiptId) + '.json');
  let raw, record;
  try {
    raw = await readFile(receiptFile, 'utf8');
    record = JSON.parse(raw);
  } catch { return { status: 'UNAVAILABLE', reason: 'RECEIPT_UNREADABLE' }; }
  if (!record || Array.isArray(record) || typeof record !== 'object' ||
      Object.keys(record).sort().join(',') !== 'digest,raceKey,receiptId,status' ||
      record.receiptId !== receiptId || record.raceKey !== raceKey ||
      record.status !== 'QUARANTINED' || typeof record.digest !== 'string' ||
      !/^[a-f0-9]{64}$/.test(record.digest))
    return { status: 'UNAVAILABLE', reason: 'RECEIPT_INVALID' };
  const indexDir = join(directory, '.race-index');
  const target = join(indexDir, hash(raceKey) + '.json');
  try { await mkdir(indexDir, { recursive: true }); }
  catch { return { status: 'UNAVAILABLE', reason: 'INDEX_UNAVAILABLE' }; }
  try {
    // Same-filesystem hardlink is an atomic, no-overwrite race claim.
    await link(receiptFile, target);
    let handle;
    try { handle = await open(indexDir, 'r'); await handle.sync(); }
    catch { return { status: 'UNAVAILABLE', reason: 'INDEX_SYNC_FAILED' }; }
    finally { await handle?.close().catch(() => {}); }
    return { status: 'QUARANTINED', reason: 'RACE_CLAIMED' };
  } catch (err) {
    if (err.code !== 'EEXIST') return { status: 'UNAVAILABLE', reason: 'INDEX_LINK_FAILED' };
    let existing;
    try { existing = JSON.parse(await readFile(target, 'utf8')); }
    catch { return { status: 'UNAVAILABLE', reason: 'INDEX_UNREADABLE' }; }
    if (!existing || Array.isArray(existing) || typeof existing !== 'object' ||
        Object.keys(existing).sort().join(',') !== 'digest,raceKey,receiptId,status' ||
        existing.raceKey !== raceKey || existing.status !== 'QUARANTINED' ||
        typeof existing.receiptId !== 'string' || !valid(existing.receiptId) ||
        !/^[a-f0-9]{64}$/.test(existing.digest))
      return { status: 'UNAVAILABLE', reason: 'INDEX_INVALID' };
    if (existing.receiptId !== receiptId) return { status: 'UNAVAILABLE', reason: 'RACE_ALREADY_CLAIMED' };
    if (existing.digest !== record.digest) return { status: 'UNAVAILABLE', reason: 'INDEX_DIGEST_CONFLICT' };
    return { status: 'QUARANTINED', reason: 'RACE_ALREADY_CLAIMED_BY_SAME_RECEIPT' };
  }
}
