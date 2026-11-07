#!/usr/bin/env node
// Local/GitHub Action bootstrap. No network, credentials, purchases or Q4
// history access. Emits a temporary SQL file; never commits model bytes.
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
import { sealFrozenModelABundle, renderFrozenModelABundleSql } from '../src/model-a-model-store.mjs';

const destination = process.argv[2];
if (!destination || process.argv.length !== 3 || !destination.endsWith('.sql')) {
  throw new Error('Usage: node tools/build_frozen_model_d1_sql.mjs <temporary-output.sql>');
}
const scriptDir = dirname(fileURLToPath(import.meta.url));
const paths = Array.from({ length: 3 }, (_, index) =>
  resolve(scriptDir, `../../../app/src/main/assets/model_a_stage${index}.txt`));
const bundle = await sealFrozenModelABundle(paths.map(path => readFileSync(path)));
writeFileSync(destination, renderFrozenModelABundleSql(bundle), { flag: 'wx', mode: 0o600 });
process.stdout.write(JSON.stringify({
  bundleSha256: bundle.bundleSha256, chunks: bundle.chunks.length,
  stages: bundle.manifest.map(({ bytes, sha256, featureCount }) => ({ bytes, sha256, featureCount })),
  output: 'temporary-sql-file',
}) + '\n');
