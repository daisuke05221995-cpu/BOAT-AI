// Research-only deterministic replay guard for quarantined Android odds receipts.
// No network, storage, wagering or forecast side effects. Caller persists returned ledger.
const deny = reason => ({ status: 'UNAVAILABLE', reason, eligible_for_buy: false, eligible_for_skip: false });
const integer = x => Number.isSafeInteger(x) && x >= 0;
const allowed = new Set(['receipt_id','race_date','stadium_number','race_number','received_ms','payload_digest','classification']);
const classes = new Set(['FULL_120_DEVICE_CLAIM','SELECTED_PICKS_ONLY','BOATRACECSV_ESTIMATE']);
const digest = x => typeof x === 'string' && /^[a-f0-9]{64}$/.test(x);
const id = x => typeof x === 'string' && /^[a-zA-Z0-9_-]{8,96}$/.test(x);
const race = x => typeof x === 'string' && /^20\d\d-(0[1-9]|1[0-2])-([0-2]\d|3[01])$/.test(x);
const key = x => `${x.race_date}/${x.stadium_number}/${x.race_number}`;
export function quarantineOddsReceipt(receipt, ledger, serverNowMs) {
  if (!Array.isArray(ledger) || !integer(serverNowMs) || !receipt || typeof receipt !== 'object' || Array.isArray(receipt)) return deny('INVALID_INPUT');
  if (Object.keys(receipt).some(k => !allowed.has(k))) return deny('FORBIDDEN_FIELD');
  if (!id(receipt.receipt_id) || !race(receipt.race_date) || !integer(receipt.stadium_number) || receipt.stadium_number < 1 || receipt.stadium_number > 24 ||
      !integer(receipt.race_number) || receipt.race_number < 1 || receipt.race_number > 12 || !integer(receipt.received_ms) ||
      !digest(receipt.payload_digest) || !classes.has(receipt.classification)) return deny('INVALID_RECEIPT');
  if (receipt.received_ms > serverNowMs + 60_000 || serverNowMs - receipt.received_ms > 180_000) return deny('RECEIPT_CLOCK_OUT_OF_RANGE');
  if (ledger.length > 10000 || ledger.some(x => !x || !id(x.receipt_id) || !digest(x.payload_digest) || !race(x.race_date) ||
      !integer(x.stadium_number) || !integer(x.race_number) || !integer(x.received_ms) || !classes.has(x.classification))) return deny('INVALID_LEDGER');
  const previous = ledger.find(x => x.receipt_id === receipt.receipt_id);
  if (previous) return deny(previous.payload_digest === receipt.payload_digest && key(previous) === key(receipt) &&
    previous.classification === receipt.classification ? 'DUPLICATE_RECEIPT' : 'REPLAY_ID_CONFLICT');
  if (ledger.some(x => key(x) === key(receipt) && x.payload_digest === receipt.payload_digest)) return deny('DUPLICATE_PAYLOAD');
  // Caller must persist the returned ledger atomically (compare-and-swap).
  return { status: 'QUARANTINED', reason: 'SOURCE_TIME_AND_RIGHTS_UNVERIFIED',
    eligible_for_buy: false, eligible_for_skip: false,
    ledger: [...ledger, { ...receipt }] };
}
