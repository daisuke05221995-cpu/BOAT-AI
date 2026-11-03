"""Download recent public-preview Actions artifacts and audit them automatically.

Runs inside GitHub Actions with the official `gh` CLI and the workflow-scoped
GH_TOKEN. Artifact contents are NOT predictions and never contain race results.
Only the fixed BOAT-AI repository's main-branch public exhibition artifacts
are accepted. No browser, signed-in betting site, or video capture is used.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from exhibition_vision.rollup import rollup


ARTIFACT_PATTERN = re.compile(r"public-exhibition-preview-(\d+)")
MAX_PAGES = 100
MAX_ZIP_BYTES = 2 * 1024 * 1024
MAX_DOWNLOADS = 1500


class ArtifactFetchError(ValueError):
    pass


def _gh(endpoint: str, *, runner=subprocess.run) -> bytes:
    """Invoke the trusted GitHub CLI with argument-array commands only."""
    try:
        completed = runner(["gh", "api", endpoint], check=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        # Do not emit environment secrets or token-bearing headers.
        raise ArtifactFetchError(f"GitHub API request failed: {endpoint.split('?')[0]}") from exc
    return completed.stdout


def select_artifacts(repo: str, *, now: datetime, days: int = 3, runner=subprocess.run) -> list[dict]:
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", repo):
        raise ArtifactFetchError("invalid GitHub repository")
    if now.tzinfo is None or not 1 <= days <= 7:
        raise ArtifactFetchError("expected timezone-aware time and 1-7 day lookback")
    cutoff = now.astimezone(timezone.utc) - timedelta(days=days)
    found = []
    for page in range(1, MAX_PAGES + 1):
        endpoint = f"repos/{repo}/actions/artifacts?per_page=100&page={page}"
        try:
            payload = json.loads(_gh(endpoint, runner=runner).decode("utf-8"))
        except (ValueError, UnicodeError) as exc:
            raise ArtifactFetchError("malformed artifact listing") from exc
        rows = payload.get("artifacts")
        if not isinstance(rows, list):
            raise ArtifactFetchError("GitHub artifact list missing")
        for artifact in rows:
            name = artifact.get("name", "")
            match = ARTIFACT_PATTERN.fullmatch(name) if isinstance(name, str) else None
            run = artifact.get("workflow_run") or {}
            if not match or artifact.get("expired") is not False:
                continue
            if (run.get("head_branch") not in (None, "main")
                    or (run.get("id") is not None and str(run["id"]) != match.group(1))):
                continue
            try:
                captured = datetime.fromisoformat(artifact["created_at"].replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError) as exc:
                raise ArtifactFetchError("invalid artifact timestamp") from exc
            if captured.tzinfo is None:
                raise ArtifactFetchError("artifact timestamp missing timezone")
            if captured < cutoff:
                continue
            size = artifact.get("size_in_bytes")
            if not isinstance(size, int) or size < 0 or size > MAX_ZIP_BYTES:
                raise ArtifactFetchError("oversized or invalid artifact")
            if type(artifact.get("id")) is not int:
                raise ArtifactFetchError("invalid artifact ID")
            found.append({"id": artifact["id"], "name": name})
        if not rows or page * 100 >= payload.get("total_count", 0):
            break
    else:
        raise ArtifactFetchError("artifact pagination limit exceeded")
    if len(found) > MAX_DOWNLOADS or len({a["id"] for a in found}) != len(found):
        raise ArtifactFetchError("too many or repeated artifacts")
    return sorted(found, key=lambda x: x["id"])


def collect(repo: str, output_dir: Path, *, days: int = 3,
            now: datetime | None = None, runner=subprocess.run) -> dict:
    now = now or datetime.now(timezone.utc)
    artifacts = select_artifacts(repo, now=now, days=days, runner=runner)
    with TemporaryDirectory(prefix="boat-ai-qa-") as directory:
        input_dir = Path(directory)
        for artifact in artifacts:
            raw = _gh(f"repos/{repo}/actions/artifacts/{artifact['id']}/zip", runner=runner)
            if len(raw) > MAX_ZIP_BYTES or not raw.startswith(b"PK"):
                raise ArtifactFetchError("GitHub returned an invalid artifact ZIP")
            (input_dir / f"{artifact['name']}.zip").write_bytes(raw)
        report = rollup(input_dir, output_dir)
    report.update({
        "source": "github_actions_preview_artifacts",
        "artifact_count": len(artifacts),
        "lookback_days": days,
        "audited_at_utc": now.astimezone(timezone.utc).isoformat(),
        "artifact_source_complete": True,
    })
    (output_dir / "rollup-summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--days", type=int, default=3)
    args = parser.parse_args()
    repo = os.getenv("GITHUB_REPOSITORY", "")
    if repo != "daisuke05221995-cpu/BOAT-AI":
        parser.error("this collection tool is restricted to the BOAT-AI repository")
    if not os.getenv("GH_TOKEN"):
        parser.error("GH_TOKEN is required")
    print(json.dumps(collect(repo, args.output_dir, days=args.days)))


if __name__ == "__main__":
    main()
