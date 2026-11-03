"""No-network contract tests for daily research artifact collection."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from zipfile import ZipFile

from exhibition_vision.artifact_fetch import ArtifactFetchError, collect, select_artifacts
from exhibition_vision.test_features import sample_record


NOW = datetime(2026, 11, 4, 4, 0, tzinfo=timezone.utc)
REPO = "daisuke05221995-cpu/BOAT-AI"


def artifact(artifact_id=101, run_id=200, *, hours_ago=3, expired=False, branch="main"):
    return {
        "id": artifact_id,
        "name": f"public-exhibition-preview-{run_id}",
        "expired": expired,
        "created_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
        "size_in_bytes": 1500,
        "workflow_run": {"id": run_id, "head_branch": branch},
    }


class FakeGh:
    def __init__(self, artifacts, content=b""):
        self.artifacts = artifacts
        self.content = content
        self.calls = []

    def __call__(self, args, **_kwargs):
        self.calls.append(args)
        endpoint = args[2]
        if endpoint.endswith("?per_page=100&page=1"):
            payload = {"total_count": len(self.artifacts), "artifacts": self.artifacts}
            return SimpleNamespace(stdout=json.dumps(payload).encode())
        if endpoint.endswith("/zip"):
            return SimpleNamespace(stdout=self.content)
        raise AssertionError(f"unexpected GitHub request {endpoint}")


def preview_zip():
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("2026-10-29_23_09.json", json.dumps(sample_record()))
    return buffer.getvalue()


class ArtifactFetchTest(unittest.TestCase):
    def test_filters_to_recent_main_preview_artifacts_only(self):
        fake = FakeGh([
            artifact(),
            artifact(102, 201, expired=True),
            artifact(103, 202, branch="experimental"),
            artifact(104, 203, hours_ago=96),
            {**artifact(105, 204), "name": "public-exhibition-features-204"},
        ])
        selected = select_artifacts(REPO, now=NOW, runner=fake)
        self.assertEqual([{"id": 101, "name": "public-exhibition-preview-200"}], selected)
        self.assertEqual(1, len(fake.calls))

    def test_download_and_deduplicate_without_results(self):
        fake = FakeGh([artifact()], content=preview_zip())
        with TemporaryDirectory() as dest:
            report = collect(REPO, Path(dest), now=NOW, runner=fake)
            self.assertEqual(1, report["artifact_count"])
            self.assertEqual(1, report["distinct_races"])
            self.assertTrue(report["artifact_source_complete"])
            self.assertFalse(report["forecast_input_allowed"])
            self.assertEqual(2, len(fake.calls))
            self.assertTrue(Path(dest, "rollup-summary.json").exists())

    def test_rejects_invalid_zip_without_claiming_success(self):
        fake = FakeGh([artifact()], content=b"this is not an artifact zip")
        with TemporaryDirectory() as dest:
            with self.assertRaises(ArtifactFetchError):
                collect(REPO, Path(dest), now=NOW, runner=fake)

    def test_bad_repository_and_duplicate_ids_fail_closed(self):
        fake = FakeGh([artifact(), artifact(101, 200)])
        with self.assertRaises(ArtifactFetchError):
            select_artifacts("../other", now=NOW, runner=fake)
        with self.assertRaises(ArtifactFetchError):
            select_artifacts(REPO, now=NOW, runner=fake)

    def test_no_recent_artifacts_emits_empty_not_fabricated_sample(self):
        fake = FakeGh([artifact(101, 200, hours_ago=97)])
        with TemporaryDirectory() as dest:
            report = collect(REPO, Path(dest), now=NOW, runner=fake)
            self.assertEqual(0, report["distinct_races"])
            self.assertEqual(0, report["artifact_count"])
            self.assertIsNone(report["median_retrieval_lead_seconds"])


if __name__ == "__main__":
    unittest.main()
