"""Poll an approved measurement provider and store shadow-only race rankings.

This adapter deliberately does NOT scrape BOATCAST or download its video.
An authorized provider must supply a detector's calibrated measurements. Video
capture, frame extraction, and boat detection are separate unimplemented stages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .scoring import evaluate_race

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_ENTRIES_PER_POLL = 32


class ProviderError(ValueError):
    pass


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise ProviderError("redirect blocked; provider URL must be explicit")


def validate_url(url: str, allowed_hosts: set[str]) -> None:
    if not isinstance(url, str):
        raise ProviderError("missing provider URL")
    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.hostname.lower() not in allowed_hosts
            or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment):
        raise ProviderError("unapproved HTTPS provider URL")


def fetch_json(url: str, allowed_hosts: set[str]) -> dict:
    validate_url(url, allowed_hosts)
    opener = build_opener(_RejectRedirect())
    with opener.open(Request(url, headers={"User-Agent": "BOAT-AI-exhibition-research/1.0", "Accept": "application/json"}), timeout=15) as response:
        content = response.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise ProviderError("provider payload too large")
    try:
        obj = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError("provider did not return JSON") from exc
    if not isinstance(obj, dict):
        raise ProviderError("expected JSON object")
    return obj


def process_manifest(manifest: dict, allowed_hosts: set[str], output_dir: Path, get_json=fetch_json) -> dict:
    """Fetch authorized detector evidence and evaluate it, never live BUY/SKIP."""
    if manifest.get("schema_version") != 1:
        raise ProviderError("unsupported manifest")
    source_id = manifest.get("source_id")
    permission_reference = manifest.get("permission_reference")
    if not isinstance(source_id, str) or not source_id.strip() or not isinstance(permission_reference, str) or not permission_reference.strip():
        raise ProviderError("permission/reference must be verified out of band")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES_PER_POLL:
        raise ProviderError("invalid number of entries")
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {"fetched": 0, "shadow_ready": 0, "research_only_late": 0, "unusable": 0, "already_saved": 0}
    seen_races: set[tuple[str, int, int]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ProviderError("invalid manifest entry")
        race_key = (entry.get("date"), entry.get("venue"), entry.get("number"))
        if (not isinstance(race_key[0], str) or not isinstance(race_key[1], int)
                or not isinstance(race_key[2], int) or not 1 <= race_key[1] <= 24
                or not 1 <= race_key[2] <= 12 or len(race_key[0]) != 10
                or not all(c.isdigit() or c == "-" for c in race_key[0])):
            raise ProviderError("invalid manifest race identity")
        if race_key in seen_races:
            raise ProviderError("duplicate race in manifest")
        seen_races.add(race_key)
        url = entry.get("measurement_url")
        validate_url(url, allowed_hosts)
        evidence = get_json(url, allowed_hosts)
        capture = evidence.get("capture", {})
        if (not isinstance(capture, dict) or capture.get("source_id") != source_id
                or capture.get("permission_reference") != permission_reference):
            raise ProviderError("detector provenance does not match approved manifest")
        result = evaluate_race(evidence)
        race = result.get("race")
        if (not isinstance(race, dict) or
                (race.get("date"), race.get("venue"), race.get("number")) != race_key):
            raise ProviderError("detector race identity does not match manifest")
        identity = f"{race_key[0]}_{race_key[1]:02d}_{race_key[2]:02d}"
        # Only artifact JSON is saved; raw video and proprietary detector inputs
        # are never written to the Git repository.
        result["evidence_sha256"] = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        path = output_dir / f"{identity}.json"
        payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == payload:
            summary["already_saved"] += 1
        else:
            path.write_text(payload, encoding="utf-8")
        summary["fetched"] += 1
        field = {"SHADOW_READY": "shadow_ready", "RESEARCH_ONLY_LATE": "research_only_late", "UNUSABLE": "unusable"}[result["status"]]
        summary[field] += 1
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-url", default=os.environ.get("EXHIBITION_AI_FEED_URL"))
    parser.add_argument("--allowed-hosts", default=os.environ.get("EXHIBITION_AI_ALLOWED_HOSTS", ""))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.manifest_url:
        print(json.dumps({"status": "SKIPPED_NO_APPROVED_PROVIDER"}))
        return
    allowed_hosts = {host.strip().lower() for host in args.allowed_hosts.split(",") if host.strip()}
    if not allowed_hosts:
        raise SystemExit("A separately approved EXHIBITION_AI_ALLOWED_HOSTS list is required")
    manifest = fetch_json(args.manifest_url, allowed_hosts)
    print(json.dumps(process_manifest(manifest, allowed_hosts, args.output_dir)))


if __name__ == "__main__":
    main()
