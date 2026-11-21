import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
const digest = s => createHash('sha256').update(s).digest('hex');
// Offline-only audit. No raw odds, BUY/SKIP, network or purchase operations.
export async function auditRaceLedger(directory) {
  let names;
  try { names = (await readdir(directory)).filter(n => /^[a-f0-9]{64}\.json$/.test(n)); }
  catch { return { status: 'UNAVAILABLE', reason: 'LEDGER_DIRECTORY_UNREADABLE' }; }
  const byRace = new Map();
  for (const name of names.sort()) {
    let record;
    try { record = JSON.parse(await readFile(join(directory, name), 'utf8')); }
    catch { return { status: 'UNAVAILABLE', reason: 'LEDGER_RECORD_UNREADABLE' }; }
    if (!record || Array.isArray(record) || typeof record !== 'object' ||
        Object.keys(record).sort().join(',') !== 'digest,raceKey,receiptId,status' ||
        typeof record.receiptId !== 'string' || !/^[A-Za-z0-9_-]{8,128}$/.test(record.receiptId) ||
        typeof record.raceKey !== 'string' || !/^[A-Za-z0-9_-]{8,128}$/.test(record.raceKey) ||
        !/^[a-f0-9]{64}$/.test(record.digest) || record.status !== 'QUARANTINED' ||
        digest(record.receiptId) + '.json' !== name)
      return { status: 'UNAVAILABLE', reason: 'LEDGER_RECORD_INVALID' };
    const prior = byRace.get(record.raceKey);
    if (prior && (prior.receiptId !== record.receiptId || prior.digest !== record.digest))
      return { status: 'UNAVAILABLE', reason: 'RACE_RECEIPT_CONFLICT', raceKey: record.raceKey };
    byRace.set(record.raceKey, { receiptId: record.receiptId, digest: record.digest });
  }
  return { status: 'QUARANTINED', reason: 'AUDIT_ONLY', receiptCount: names.length, raceCount: byRace.size };
}
