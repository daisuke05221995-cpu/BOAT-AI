import { createHash } from 'node:crypto';
import { mkdir, readFile, open, link, unlink } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { join } from 'node:path';
// Offline research-only: never authorizes BUY, SKIP, or actual purchase.
const hash = s => createHash('sha256').update(s).digest('hex');
const canonical = v => Array.isArray(v) ? '[' + v.map(canonical).join(',') + ']' : v && typeof v === 'object' ? '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}' : JSON.stringify(v);

// Reject non-JSON, cyclic, oversized or sensitive inputs before hashing; never persist raw payload.
function safePayload(value) {
  const seen = new WeakSet();
  let nodes = 0;
  const forbidden = /^(?:password|passwd|token|secret|authorization|cookie|session|account|member_?id|receipt_?number|purchase_?history|credential|api_?key)$/i;
  function visit(v, depth) {
    if (++nodes > 5000 || depth > 12) return false;
    if (v === null || typeof v === 'boolean' || typeof v === 'string') return typeof v !== 'string' || v.length <= 4096;
    if (typeof v === 'number') return Number.isFinite(v);
    if (!v || typeof v !== 'object' || seen.has(v)) return false;
    if (!Array.isArray(v) && Object.getPrototypeOf(v) !== Object.prototype && Object.getPrototypeOf(v) !== null) return false;
    seen.add(v);
    const descriptors = Object.getOwnPropertyDescriptors(v);
    for (const [k, d] of Object.entries(descriptors)) {
      if (!('value' in d) || forbidden.test(k) || !visit(d.value, depth + 1)) return false;
    }
    if (Array.isArray(v) && (Object.keys(v).length !== v.length || v.length > 1000)) return false;
    seen.delete(v);
    return true;
  }
  try { return visit(value, 0) && Buffer.byteLength(JSON.stringify(value)) <= 65536; }
  catch { return false; }
}
export async function quarantineReceipt(directory, receipt) {
  if (!receipt || typeof receipt !== 'object' || Array.isArray(receipt)) return { status: 'UNAVAILABLE', reason: 'INVALID_RECEIPT' };
  const { receiptId, raceKey, payload } = receipt;
  if (typeof receiptId !== 'string' || !/^[A-Za-z0-9_-]{8,128}$/.test(receiptId) ||
      typeof raceKey !== 'string' || !/^[A-Za-z0-9_-]{8,128}$/.test(raceKey) ||
      !payload || typeof payload !== 'object' || Array.isArray(payload) || !safePayload(payload))
    return { status: 'UNAVAILABLE', reason: 'INVALID_RECEIPT' };
  const digest = hash(canonical({ raceKey, payload }));
  const file = join(directory, hash(receiptId) + '.json');
  await mkdir(directory, { recursive: true });
  // Write a complete, synced temporary record before atomically publishing via hard link.
  // A crash before link leaves no visible receipt; a crash after link leaves a complete one.
  const temp = join(directory, '.' + randomUUID() + '.tmp');
  let handle;
  try {
    handle = await open(temp, 'wx', 0o600);
    await handle.writeFile(JSON.stringify({ receiptId, raceKey, digest, status: 'QUARANTINED' }));
    await handle.sync();
    await handle.close();
    handle = undefined;
    await link(temp, file); // atomic no-overwrite across processes on the same filesystem
    return { status: 'QUARANTINED', reason: 'NEW_RECEIPT', digest };
  } catch (err) {
    if (err.code !== 'EEXIST') throw err;
    let previous;
    try { previous = JSON.parse(await readFile(file, 'utf8')); }
    catch { return { status: 'UNAVAILABLE', reason: 'LEDGER_UNREADABLE' }; }
    if (previous.receiptId !== receiptId || previous.raceKey !== raceKey || previous.status !== 'QUARANTINED')
      return { status: 'UNAVAILABLE', reason: 'LEDGER_CONFLICT' };
    return previous.digest === digest
      ? { status: 'QUARANTINED', reason: 'DUPLICATE_RECEIPT', digest }
      : { status: 'UNAVAILABLE', reason: 'RECEIPT_ID_CONFLICT' };
  } finally {
    if (handle) await handle.close().catch(() => {});
    await unlink(temp).catch(err => { if (err.code !== 'ENOENT') throw err; });
  }
}
