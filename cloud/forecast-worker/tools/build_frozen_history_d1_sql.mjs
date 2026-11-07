#!/usr/bin/env node
// Writes only the Android-shipped, hash-verified BAH1 base; never a rolling
// research history or a synthetic current-day checkpoint.
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { sealAndroidHistoryBase, FROZEN_ANDROID_HISTORY_BASE,
  renderFrozenHistoryBaseSql } from '../src/model-a-history-store.mjs';

const destination = process.argv[2];
if (!destination || process.argv.length !== 3 || !destination.endsWith('.sql')) {
  throw new Error('Usage: node tools/build_frozen_history_d1_sql.mjs <temporary-output.sql>');
}
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../../app/src/main/assets');
const manifest = JSON.parse(readFileSync(resolve(root, 'model_a_deployment.json'), 'utf8')).assets['model_a_history.bin'];
if (manifest.bytes !== FROZEN_ANDROID_HISTORY_BASE.bytes ||
    manifest.sha256 !== FROZEN_ANDROID_HISTORY_BASE.sha256) throw new Error('HISTORY_BASE_MANIFEST_CHANGED');
const base = await sealAndroidHistoryBase(readFileSync(resolve(root, 'model_a_history.bin')), manifest);
writeFileSync(destination, renderFrozenHistoryBaseSql(base), { flag: 'wx', mode: 0o600 });
process.stdout.write(JSON.stringify({ sha256: base.sha256, chunks: base.chunks.length,
  throughDay: base.throughDay, updateRaces: base.updateRaces,
  historyStatus: 'FROZEN_BASE_STAGED_NOT_ACTIVE', output: 'temporary-sql-file' }) + '\n');
