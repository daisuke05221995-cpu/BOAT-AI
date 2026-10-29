import copy
import unittest

from exhibition_vision.scoring import evaluate_race
from exhibition_vision.worker import ProviderError, process_manifest, validate_url
from exhibition_vision.kinematics import InvalidTrack, measurements_from_tracks
from tempfile import TemporaryDirectory
from pathlib import Path


def sample_evidence():
    boats = []
    for lane in range(1, 7):
        factor = (7 - lane) / 6
        boats.append({
            "lane": lane,
            "quality": {"track_coverage": 0.98, "detector_confidence": 0.97, "calibration_error_m": 0.25},
            "measurements": {
                "exit_acceleration_mps2": 0.8 + factor,
                "runup_acceleration_mps2": 0.7 + factor,
                "straight_speed_mps": 19 + factor,
                "turn_speed_mps": 12 + factor,
                "turn_time_s": 6.4 - factor,
                "turn_min_speed_retention": 0.63 + factor * 0.2,
                "turn_marker_clearance_m": 2.0 - factor,
            },
        })
    return {
        "schema_version": 1,
        "race": {"date": "2026-10-29", "venue": 23, "number": 9, "deadline": "2026-10-29T15:30:00+09:00"},
        "capture": {
            "source_id": "approved-example", "permission_reference": "contract-123",
            "video_sha256": "a" * 64, "detector_version": "pilot-v1", "calibration_version": "venue23-v1",
            "captured_at": "2026-10-29T15:20:00+09:00",
            "analyzed_at": "2026-10-29T15:23:00+09:00",
        },
        "boats": boats,
    }


class ScoreTest(unittest.TestCase):
    def test_all_five_traits_ranked_but_not_promoted(self):
        result = evaluate_race(sample_evidence())
        self.assertEqual("SHADOW_READY", result["status"])
        self.assertEqual([1, 2, 3, 4, 5, 6], [x["overall_rank"] for x in result["boats"]])
        self.assertEqual(5, len(result["boats"][0]["scores"]))
        self.assertEqual(5, len(result["boats"][0]["ranks"]))
        self.assertFalse(result["forecast_input_allowed"])
        self.assertFalse(result["purchase_decision_allowed"])

    def test_missing_boat_is_not_ranked(self):
        sample = sample_evidence()
        sample["boats"].pop()
        result = evaluate_race(sample)
        self.assertEqual("UNUSABLE", result["status"])
        self.assertEqual([], result["boats"])

    def test_weak_video_quality_is_not_ranked(self):
        sample = sample_evidence()
        sample["boats"][2]["quality"]["track_coverage"] = 0.25
        self.assertEqual("UNUSABLE", evaluate_race(sample)["status"])

    def test_after_deadline_capture_rejected_as_leak(self):
        sample = sample_evidence()
        sample["capture"]["captured_at"] = "2026-10-29T15:31:00+09:00"
        sample["capture"]["analyzed_at"] = "2026-10-29T15:32:00+09:00"
        self.assertEqual("UNUSABLE", evaluate_race(sample)["status"])

    def test_late_analysis_is_research_only(self):
        sample = sample_evidence()
        sample["capture"]["analyzed_at"] = "2026-10-29T15:31:00+09:00"
        self.assertEqual("RESEARCH_ONLY_LATE", evaluate_race(sample)["status"])

    def test_missing_permission_or_calibration_rejected(self):
        for key in ("permission_reference", "calibration_version", "video_sha256"):
            with self.subTest(key=key):
                sample = sample_evidence()
                sample["capture"].pop(key)
                self.assertEqual("UNUSABLE", evaluate_race(sample)["status"])

    def test_invalid_measurement_rejected(self):
        for value in (float("nan"), True, None):
            sample = sample_evidence()
            sample["boats"][0]["measurements"]["straight_speed_mps"] = value
            self.assertEqual("UNUSABLE", evaluate_race(sample)["status"])

    def test_exact_equal_scores_share_rank(self):
        sample = sample_evidence()
        sample["boats"] = [copy.deepcopy(sample["boats"][0]) for _ in range(6)]
        for i, boat in enumerate(sample["boats"], 1):
            boat["lane"] = i
        result = evaluate_race(sample)
        self.assertEqual([1] * 6, [b["overall_rank"] for b in result["boats"]])
        self.assertEqual([50] * 6, [b["scores"]["nobiashi"] for b in result["boats"]])


class WorkerTest(unittest.TestCase):
    def test_unapproved_or_redirect_style_url_rejected(self):
        for url in ("http://approved.example/a", "https://not-approved.example/a", "https://approved.example:8443/a", "https://user:pass@approved.example/a"):
            with self.subTest(url=url):
                with self.assertRaises(ProviderError):
                    validate_url(url, {"approved.example"})

    def test_approved_measurement_ingestion(self):
        manifest = {"schema_version": 1, "source_id": "approved-example", "permission_reference": "contract-123",
                    "entries": [{"date": "2026-10-29", "venue": 23, "number": 9,
                                 "measurement_url": "https://approved.example/evidence.json"}]}
        with TemporaryDirectory() as directory:
            report = process_manifest(manifest, {"approved.example"}, Path(directory), get_json=lambda *_: sample_evidence())
            self.assertEqual(1, report["shadow_ready"])
            self.assertEqual(1, len(list(Path(directory).glob("*.json"))))

    def test_provider_identity_mismatch_rejected(self):
        manifest = {"schema_version": 1, "source_id": "wrong-source", "permission_reference": "contract-123",
                    "entries": [{"date": "2026-10-29", "venue": 23, "number": 9,
                                 "measurement_url": "https://approved.example/evidence.json"}]}
        with TemporaryDirectory() as directory:
            with self.assertRaises(ProviderError):
                process_manifest(manifest, {"approved.example"}, Path(directory), get_json=lambda *_: sample_evidence())

    def test_manifest_race_mismatch_rejected(self):
        manifest = {"schema_version": 1, "source_id": "approved-example", "permission_reference": "contract-123",
                    "entries": [{"date": "2026-10-29", "venue": 23, "number": 10,
                                 "measurement_url": "https://approved.example/evidence.json"}]}
        with TemporaryDirectory() as directory:
            with self.assertRaises(ProviderError):
                process_manifest(manifest, {"approved.example"}, Path(directory), get_json=lambda *_: sample_evidence())


class KinematicsTest(unittest.TestCase):
    def test_calibrated_tracks_generate_seven_raw_measurements(self):
        tracks = {"turn_marker_m": {"x_m": 50, "y_m": 2}, "boats": []}
        for lane in range(1, 7):
            points = []
            for phase, offset in (("runup", 0), ("straight", 10), ("turn", 20), ("exit", 30)):
                for frame in range(5):
                    x = offset + frame * (2.0 + 0.1 * frame if phase in ("runup", "exit") else 2.0)
                    points.append({"phase": phase, "t": offset + frame * 0.5,
                                   "x_m": x + lane, "y_m": 2.0})
            tracks["boats"].append({"lane": lane, "quality": sample_evidence()["boats"][0]["quality"], "points": points})
        measurements = measurements_from_tracks(tracks)
        self.assertEqual(6, len(measurements))
        self.assertEqual(7, len(measurements[0]["measurements"]))
        self.assertGreater(measurements[0]["measurements"]["exit_acceleration_mps2"], 0)

    def test_pixels_are_not_accepted_as_meters(self):
        with self.assertRaises(InvalidTrack):
            measurements_from_tracks({"turn_marker_m": {"x": 20, "y": 30}, "boats": []})

if __name__ == "__main__":
    unittest.main()
