"""Restore the public official snapshot evidence without a new network fetch."""
import argparse
import base64
import gzip
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,default=Path.cwd()/'odds_drift_work')
parser.add_argument('--archive',type=Path,default=Path(__file__).resolve().parents[2]/'data/odds_drift_full_raw_20261014.json.gz')
args=parser.parse_args()
cache=args.root/'cache'
cache.mkdir(parents=True,exist_ok=True)
(args.root/'output').mkdir(parents=True,exist_ok=True)
archive=json.loads(gzip.decompress(args.archive.read_bytes()))
for record in archive['files']:
    name=record['name']
    if Path(name).name!=name or not name.startswith(('final_','official_')):
        raise SystemExit('Unsafe archive filename')
    data=base64.b64decode(record['contentBase64'],validate=True)
    if hashlib.sha256(data).hexdigest()!=record['sha256']:
        raise SystemExit('Checksum mismatch: '+name)
    target=cache/name
    target.write_bytes(data)
    timestamp=datetime.fromisoformat(record['retrievedAt']).timestamp()
    os.utime(target,(timestamp,timestamp))
print(f"Restored and verified {len(archive['files'])} public official evidence files")
