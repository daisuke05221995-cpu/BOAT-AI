"""Synthetic-color-video regression tests. They do NOT validate actual race footage."""

from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from exhibition_vision.video_tracker import (
    VideoTrackingError, analyze_video, homography_from_anchors, project_point,
    track_frames,
)
from exhibition_vision.kinematics import measurements_from_tracks
from exhibition_vision.scoring import evaluate_race


WIDTH = 640
HEIGHT = 200
FPS = 8
COLORS = [(240, 30, 35), (30, 40, 245), (245, 220, 25),
          (35, 220, 60), (220, 45, 210), (40, 215, 230)]


def camera_config():
    anchors = [
        ([0, 0], [0, 0]),
        ([WIDTH, 0], [WIDTH * 0.2, 0]),
        ([WIDTH, HEIGHT], [WIDTH * 0.2, HEIGHT * 0.2]),
        ([0, HEIGHT], [0, HEIGHT * 0.2]),
        ([100, 100], [20, 20]),
        ([500, 150], [100, 30]),
    ]
    return {
        "width": WIDTH, "height": HEIGHT, "fps": FPS, "duration_s": 8,
        "calibration": {
            "id": "synthetic-homography-v1",
            "anchors": [{"pixel": p, "meters": m} for p, m in anchors],
            "turn_marker_pixel": [320, 100],
        },
        "phase_windows": [
            {"phase": p, "start_s": i * 2, "end_s": (i + 1) * 2}
            for i, p in enumerate(("runup", "straight", "turn", "exit"))
        ],
        "boats": [
            {
                "lane": lane, "rgb": list(COLORS[lane - 1]),
                "start_px": [30 + 2 * lane, lane * 25],
                "radius_px": 24, "tolerance": 40, "min_pixels": 5,
            }
            for lane in range(1, 7)
        ],
    }


def synthetic_frames(missing_lane: int | None = None):
    for index in range(FPS * 8):
        t = index / FPS
        image = bytearray(WIDTH * HEIGHT * 3)
        for lane, color in enumerate(COLORS, 1):
            if lane == missing_lane:
                continue
            x = round(30 + 2 * lane + 40 * t + 1.5 * t * t)
            y = 25 * lane
            for yy in range(y - 2, y + 3):
                for xx in range(x - 2, x + 3):
                    offset = (yy * WIDTH + xx) * 3
                    image[offset:offset + 3] = bytes(color)
        yield t, bytes(image)


def synthetic_turn_frames():
    for index in range(FPS * 12):
        t = index / FPS
        image = bytearray(WIDTH * HEIGHT * 3)
        for lane, color in enumerate(COLORS, 1):
            if t < 5:
                x, y = 30 + 5 * t, 20 * lane
            elif t < 9:
                angle = math.pi / 2 * (t - 5) / 4
                x, y = 55 + 40 * math.sin(angle), 20 * lane + 40 * (1 - math.cos(angle))
            else:
                x, y = 95, 20 * lane + 40 + 8 * (t - 9)
            for yy in range(round(y) - 2, round(y) + 3):
                for xx in range(round(x) - 2, round(x) + 3):
                    offset = (yy * WIDTH + xx) * 3
                    image[offset:offset + 3] = bytes(color)
        yield t, bytes(image)


class CalibrationTest(unittest.TestCase):
    def test_independent_holdout_error_is_small(self):
        h, error = homography_from_anchors(camera_config()["calibration"])
        self.assertLess(error, 1e-6)
        self.assertAlmostEqual(10.0, project_point(h, (50.0, 10.0))[0])

    def test_wrong_holdout_does_not_pass_as_zero_error(self):
        config = camera_config()
        config["calibration"]["anchors"][4]["meters"] = [42, 60]
        with self.assertRaisesRegex(VideoTrackingError, "holdout calibration error"):
            homography_from_anchors(config["calibration"])

    def test_degenerate_camera_cannot_produce_meter_speeds(self):
        config = camera_config()
        config["calibration"]["anchors"][3]["pixel"] = [0, 0]
        with self.assertRaises(VideoTrackingError):
            homography_from_anchors(config["calibration"])


class ColorTrackingTest(unittest.TestCase):
    def test_six_boats_can_be_tracked_and_measured(self):
        tracks = track_frames(camera_config(), synthetic_frames())
        self.assertEqual(6, len(tracks["boats"]))
        self.assertTrue(all(len(b["points"]) == 64 for b in tracks["boats"]))
        self.assertTrue(all(b["quality"]["track_coverage"] == 1.0 for b in tracks["boats"]))
        self.assertTrue(all(b["quality"]["detector_confidence"] >= 0.9 for b in tracks["boats"]))
        measurements = measurements_from_tracks(tracks)
        self.assertEqual(6, len(measurements))
        self.assertTrue(all(7 < b["measurements"]["straight_speed_mps"] < 30 for b in measurements))

    def test_a_missing_sixth_boat_must_not_generate_an_overconfident_ranking(self):
        tracks = track_frames(camera_config(), synthetic_frames(missing_lane=6))
        self.assertEqual(0.0, tracks["boats"][5]["quality"]["track_coverage"])
        # There is no valid 4-phase track for lane six; no fabricated values are permitted.
        with self.assertRaises(Exception):
            measurements_from_tracks(tracks)

    def test_bad_frame_size_fails(self):
        with self.assertRaisesRegex(VideoTrackingError, "corrupt RGB"):
            track_frames(camera_config(), [(0.0, b"x")])

    def test_ambiguous_color_templates_are_rejected(self):
        config = camera_config()
        config["boats"][1]["rgb"] = config["boats"][0]["rgb"]
        with self.assertRaisesRegex(VideoTrackingError, "ambiguous"):
            track_frames(config, synthetic_frames())

    def test_camera_cut_invalidates_single_view_calibration(self):
        def frames_with_cut():
            for index, (t, pixels) in enumerate(synthetic_frames()):
                yield t, bytes([255]) * len(pixels) if index == 20 else pixels
        with self.assertRaisesRegex(VideoTrackingError, "scene change"):
            track_frames(camera_config(), frames_with_cut())

    def test_full_six_boat_turn_can_be_autolabeled_before_scoring(self):
        config = camera_config()
        config["phase_mode"] = "auto_turn_v1"
        config.pop("phase_windows")
        config["boats"] = [
            dict(boat, start_px=[30, 20 * boat["lane"]]) for boat in config["boats"]
        ]
        tracks = track_frames(config, synthetic_turn_frames())
        self.assertTrue(70 < tracks["phase_detection"]["total_turn_angle_degrees"] < 110)
        measurements = measurements_from_tracks(tracks)
        self.assertEqual(6, len(measurements))
        self.assertEqual(7, len(measurements[0]["measurements"]))

    def test_straight_only_clip_cannot_fabricate_automatic_turn_scores(self):
        config = camera_config()
        config["phase_mode"] = "auto_turn_v1"
        config.pop("phase_windows")
        with self.assertRaisesRegex(VideoTrackingError, "automatic phase detection rejected"):
            track_frames(config, synthetic_frames())


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for video E2E")
class VideoEndToEndTest(unittest.TestCase):
    def test_offline_video_decoding_to_shadow_ranks(self):
        with TemporaryDirectory() as temp:
            video_path = Path(temp) / "synthetic.mkv"
            command = [
                "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS),
                "-i", "pipe:0", "-c:v", "ffv1", str(video_path),
            ]
            frames = b"".join(frame for _, frame in synthetic_frames())
            subprocess.run(command, input=frames, check=True, capture_output=True, timeout=30)
            now = datetime.now(timezone.utc)
            jst = timezone(timedelta(hours=9))
            deadline = now + timedelta(minutes=4)
            config = {
                "race": {
                    "date": deadline.astimezone(jst).date().isoformat(),
                    "venue": 1, "number": 1,
                    "deadline": deadline.isoformat(),
                },
                "video": {
                    "source_id": "synthetic-test-only",
                    "permission_reference": "synthetic-pixels-owned-by-test",
                    "recording_completed_at": now.isoformat(),
                },
                "tracking": camera_config(),
            }
            result = analyze_video(video_path, config)
            self.assertEqual("SHADOW_READY", result["status"], result.get("reason"))
            self.assertEqual(6, len(result["boats"]))
            self.assertEqual(5, len(result["boats"][0]["scores"]))
            self.assertFalse(result["forecast_input_allowed"])
            self.assertFalse(result["purchase_decision_allowed"])
            self.assertTrue(result["video_metadata_only"])
            self.assertNotIn("frames", result)

    def test_decoded_turn_video_can_auto_detect_phases(self):
        with TemporaryDirectory() as temp:
            video_path = Path(temp) / "turn.mkv"
            command = [
                "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS),
                "-i", "pipe:0", "-c:v", "ffv1", str(video_path),
            ]
            subprocess.run(
                command, input=b"".join(frame for _, frame in synthetic_turn_frames()),
                check=True, capture_output=True, timeout=30,
            )
            now = datetime.now(timezone.utc)
            deadline = now + timedelta(minutes=4)
            tracking = camera_config()
            tracking["duration_s"] = 12
            tracking["phase_mode"] = "auto_turn_v1"
            tracking.pop("phase_windows")
            tracking["boats"] = [dict(b, start_px=[30, 20 * b["lane"]]) for b in tracking["boats"]]
            config = {
                "race": {"date": deadline.astimezone(timezone(timedelta(hours=9))).date().isoformat(),
                         "venue": 1, "number": 1, "deadline": deadline.isoformat()},
                "video": {"source_id": "synthetic-turn-only",
                          "permission_reference": "owned-synthetic-pixels",
                          "recording_completed_at": now.isoformat()},
                "tracking": tracking,
            }
            result = analyze_video(video_path, config)
            self.assertEqual("SHADOW_READY", result["status"], result.get("reason"))
            self.assertEqual(6, len(result["boats"]))
            self.assertEqual("collective_heading_change_v1_unvalidated", result["phase_detection"]["method"])
            self.assertFalse(result["forecast_input_allowed"])


if __name__ == "__main__":
    unittest.main()
