"""Offline audit and frozen cutoff selection for GitHub preview artifacts."""

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from exhibition_vision.rollup import RollupError, rollup
from exhibition_vision.test_features import sample_record


JST = ZoneInfo("Asia/Tokyo")


class ArtifactRollupTest(unittest.TestCase):
    def _record(self, hour: int, minute: int):
        record = sample_record()
        record["retrieved_at"] = datetime(2026, 10, 29, hour, minute, tzinfo=JST).isoformat()
        return record

    def test_latest_eligible_snapshot_wins_independent_of_values(self):
        early = self._record(15, 20)
        late = self._record(15, 27)
        late["boats"][0]["original"]["turn_time_s"] = 1.23  # no cherry-picking based on speed
        with TemporaryDirectory() as src, TemporaryDirectory() as dest:
            with ZipFile(Path(src, "public-exhibition-preview-100.zip"), "w") as z:
                z.writestr("race.json", json.dumps(early))
            with ZipFile(Path(src, "public-exhibition-preview-101.zip"), "w") as z:
                z.writestr("race.json", json.dumps(late))
            report = rollup(Path(src), Path(dest))
            self.assertEqual(1, report["distinct_races"])
            self.assertEqual(1, report["duplicate_observations"])
            self.assertEqual(1, report["races_with_two_or_more_original_items"])
            self.assertEqual(180, report["median_retrieval_lead_seconds"])
            self.assertFalse(report["phase_1_readiness"])
            result = json.loads(Path(dest, "202610292309.json").read_text())
            self.assertEqual(late["retrieved_at"], result["retrieved_at"])
            self.assertFalse(result["forecast_input_allowed"])

    def test_too_late_rejected_and_no_claim_of_qualified_races(self):
        just_before = self._record(15, 29)
        archive = deepcopy(just_before)
        archive["status"] = "ARCHIVE_ONLY"
        with TemporaryDirectory() as src, TemporaryDirectory() as dest:
            Path(src, "late.json").write_text(json.dumps(just_before))
            Path(src, "archive.json").write_text(json.dumps(archive))
            report = rollup(Path(src), Path(dest))
            self.assertEqual(0, report["distinct_races"])
            self.assertEqual(1, report["too_close_to_deadline"])
            self.assertEqual(1, report["invalid_or_ineligible"])

    def test_conflicting_same_time_snapshots_fail_closed(self):
        first = self._record(15, 20)
        second = deepcopy(first)
        second["boats"][0]["original"]["turn_time_s"] = 9.99
        with TemporaryDirectory() as src, TemporaryDirectory() as dest:
            Path(src, "a.json").write_text(json.dumps(first))
            Path(src, "b.json").write_text(json.dumps(second))
            with self.assertRaises(RollupError):
                rollup(Path(src), Path(dest))

    def test_unsafe_zip_path_refused_without_extracting(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dest:
            with ZipFile(Path(src, "bad.zip"), "w") as z:
                z.writestr("../escape.json", json.dumps(self._record(15, 20)))
            with self.assertRaises(RollupError):
                rollup(Path(src), Path(dest))

    def test_proscribed_lead_adjustment_rejected(self):
        with TemporaryDirectory() as src, TemporaryDirectory() as dest:
            with self.assertRaises(RollupError):
                rollup(Path(src), Path(dest), min_lead_seconds=0)


if __name__ == "__main__":
    unittest.main()
