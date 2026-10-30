"""Freeze research-only feature semantics before Model B outcome evaluation."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from exhibition_vision.features import UnusablePreview, build_features, run
from exhibition_vision.public_feed import process_day
from exhibition_vision.test_public_feed import AFTER, BEFORE, DAY, original_csv, stt_csv, tkz_csv


def sample_record():
    return process_day({"original_exhibition": original_csv(), "stt": stt_csv(), "tkz": tkz_csv()}, DAY, BEFORE)[0]


class PublicFeatureTest(unittest.TestCase):
    def test_six_boat_time_deltas_only_research(self):
        result = build_features(sample_record())
        self.assertEqual(6, len(result["boats"]))
        self.assertEqual("published_exhibition_numerics_only", result["data_kind"])
        self.assertFalse(result["model_trained"])
        self.assertFalse(result["forecast_input_allowed"])
        self.assertFalse(result["purchase_decision_allowed"])
        straight = [b["relative"]["straight_time_s"] for b in result["boats"]]
        self.assertAlmostEqual(0.0, sum(straight))
        self.assertLess(straight[0], straight[5])
        self.assertTrue(all(b["present"]["turn_time_s"] for b in result["boats"]))

    def test_archive_and_tampered_capture_rejected(self):
        record = process_day({"original_exhibition": original_csv()}, DAY, AFTER)[0]
        with self.assertRaises(UnusablePreview):
            build_features(record)
        record = sample_record()
        record["source_captured_at"]["original_exhibition"] = "2026-10-29T15:31:00+09:00"
        with self.assertRaises(UnusablePreview):
            build_features(record)

    def test_missing_source_stays_missing_not_zero(self):
        record = process_day({"stt": stt_csv()}, DAY, BEFORE)[0]
        result = build_features(record)
        self.assertTrue(all(b["relative"]["straight_time_s"] is None for b in result["boats"]))
        self.assertTrue(all(b["present"]["straight_time_s"] is False for b in result["boats"]))

    def test_result_and_odds_fields_do_not_pass_through(self):
        record = sample_record()
        record["race_result"] = "1-2-3"
        record["odds"] = {"1-2-3": 25.0}
        result = build_features(record)
        encoded = json.dumps(result)
        self.assertNotIn("race_result", encoded)
        self.assertNotIn("odds", encoded)

    def test_duplicate_display_courses_rejected(self):
        record = sample_record()
        record["boats"][1]["course"] = 1
        with self.assertRaises(UnusablePreview):
            build_features(record)

    def test_empty_preclose_evidence_rejected(self):
        record = sample_record()
        record["source_captured_at"] = {}
        with self.assertRaises(UnusablePreview):
            build_features(record)

    def test_runner_exports_only_valid_preclose_files(self):
        valid = sample_record()
        invalid = deepcopy(valid)
        invalid["status"] = "ARCHIVE_ONLY"
        with TemporaryDirectory() as src, TemporaryDirectory() as out:
            Path(src, "valid.json").write_text(json.dumps(valid), encoding="utf-8")
            Path(src, "invalid.json").write_text(json.dumps(invalid), encoding="utf-8")
            report = run(Path(src), Path(out))
            self.assertEqual(1, report["eligible"])
            self.assertEqual(1, report["rejected"])
            self.assertEqual(["valid.json"], [p.name for p in Path(out).glob("*.json")])


if __name__ == "__main__":
    unittest.main()
