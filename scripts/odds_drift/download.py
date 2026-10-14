import argparse
import csv
import hashlib
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

parser = argparse.ArgumentParser(description="Download pinned public source CSVs with checksums")
parser.add_argument('--root', type=Path, default=Path.cwd() / 'odds_drift_work')
parser.add_argument('--inventory', type=Path, default=Path(__file__).resolve().parents[2] / 'data/odds_drift_source_inventory_20261014.json')
args = parser.parse_args()
ROOT = args.root
(ROOT / 'cache').mkdir(parents=True, exist_ok=True)
(ROOT / 'output').mkdir(parents=True, exist_ok=True)
REF = '31b03b22989700a9f3a94152ae88edcaa1642124'
BASE = f'https://raw.githubusercontent.com/BoatraceCSV/boatracecsv.github.io/{REF}/'
entries = json.loads(args.inventory.read_text())
tasks = []
for entry in entries:
    for kind in ['od3', 'payouts']:
        path = entry['path'] if kind == 'od3' else entry['path'].replace('previews/od3', 'results/payouts')
        parts = path.split('/')
        day = '-'.join([parts[-3], parts[-2], parts[-1][:-4]])
        tasks.append((kind, day, path, entry['sha'] if kind == 'od3' else None))

def fetch(task):
    kind, day, path, expected_blob = task
    target = ROOT / 'cache' / f'{kind}_{day}.csv'
    error = None
    for attempt in range(3):
        try:
            if target.exists():
                data = target.read_bytes()
            else:
                req = urllib.request.Request(BASE + path, headers={'User-Agent': 'BOAT-AI-Odds-Drift-Research/1.0'})
                with urllib.request.urlopen(req, timeout=35) as response:
                    data = response.read()
            blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if expected_blob and blob != expected_blob:
                raise ValueError(f'blob hash mismatch: {path}')
            text = data.decode('utf-8-sig')
            if not text.startswith('レースコード,'):
                raise ValueError('Unexpected CSV header')
            target.write_bytes(data)
            return {'kind': kind, 'date': day, 'path': path, 'url': BASE + path, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'blob_sha': blob, 'rows': sum(1 for _ in csv.DictReader(text.splitlines())), 'status': 'ok'}
        except urllib.error.HTTPError as exc:
            error = str(exc)
            if exc.code == 404:
                return {'kind': kind, 'date': day, 'path': path, 'status': 'missing', 'error': error}
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
        time.sleep(0.5 * (attempt + 1))
    return {'kind': kind, 'date': day, 'path': path, 'status': 'error', 'error': error}

results = []
started = time.monotonic()
with ThreadPoolExecutor(max_workers=12) as pool:
    futures = [pool.submit(fetch, task) for task in tasks]
    for future in as_completed(futures):
        result = future.result()
        results.append(result)
        if result['status'] != 'ok':
            print(json.dumps(result, ensure_ascii=False), flush=True)
        if len(results) % 20 == 0:
            print(f'Downloaded {len(results)}/{len(tasks)}, elapsed {time.monotonic()-started:.1f}s', flush=True)
results.sort(key=lambda r: (r['date'], r['kind']))
(ROOT / 'output' / 'odds_drift_source_manifest_20261014.json').write_text(json.dumps({'sourceRef': REF, 'files': results}, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'files': len(results), 'failures': [r for r in results if r['status'] != 'ok'], 'seconds': round(time.monotonic()-started,1)}, ensure_ascii=False), flush=True)
if any(r['status'] != 'ok' for r in results):
    raise SystemExit(1)
