"""Synthetic-color-video regression tests. They do NOT validate actual race footage."""

from datetime import datetime, timedelta, timezone
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


if __name__ == "__main__":
    unittest.main()
