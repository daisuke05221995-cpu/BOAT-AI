import math
import unittest

from exhibition_vision.phase_detection import (
    PhaseDetectionError, apply_detected_phases, detect_six_boat_turn
)


def _six_tracks(with_turn: bool = True, missing_samples: bool = False):
    boats = []
    for lane in range(1, 7):
        points = []
        for index in range(96):
            if missing_samples and index % 23 == lane:
                continue
            t = index / 8
            y0 = 5.0 * lane
            if not with_turn or t < 5:
                x, y = 10 * t, y0
            elif t < 9:
                angle = 0.4 * (t - 5)
                x, y = 50 + 25 * math.sin(angle), y0 + 25 * (1 - math.cos(angle))
            else:
                x = 50 + 25 * math.sin(1.6) + 10 * (t - 9) * math.cos(1.6)
                y = y0 + 25 * (1 - math.cos(1.6)) + 10 * (t - 9) * math.sin(1.6)
            points.append({"t": t, "x_m": x, "y_m": y})
        boats.append({"lane": lane, "points": points})
    return boats


class AutomaticPhaseSegmentationTest(unittest.TestCase):
    def test_one_visible_collective_turn_produces_all_four_phases(self):
        boats = _six_tracks()
        diagnostic = apply_detected_phases(boats)
        self.assertEqual("collective_heading_change_v1_unvalidated", diagnostic["method"])
        self.assertTrue(diagnostic["runup_split_is_heuristic"])
        self.assertTrue(75 < diagnostic["total_turn_angle_degrees"] < 110)
        phases = {"runup", "straight", "turn", "exit"}
        for boat in boats:
            self.assertEqual(phases, {p["phase"] for p in boat["points"]})
            self.assertTrue(all(
                len([p for p in boat["points"] if p["phase"] == phase]) >= 4
                for phase in phases
            ))

    def test_missing_few_frames_still_segments_without_inventing_points(self):
        boats = _six_tracks(missing_samples=True)
        before = sum(len(b["points"]) for b in boats)
        apply_detected_phases(boats)
        after = sum(len(b["points"]) for b in boats)
        self.assertLessEqual(after, before)
        self.assertGreater(after, before * 0.95)

    def test_straight_video_does_not_fabricate_a_turn(self):
        with self.assertRaisesRegex(PhaseDetectionError, "no sustained common turn"):
            detect_six_boat_turn(_six_tracks(with_turn=False))

    def test_missing_boat_fails_closed(self):
        with self.assertRaisesRegex(PhaseDetectionError, "six identifiable"):
            detect_six_boat_turn(_six_tracks()[:5])

    def test_two_turns_in_one_clip_are_rejected_not_cherry_picked(self):
        boats = []
        for lane in range(1, 7):
            points = []
            y0 = 5.0 * lane
            for index in range(160):
                t = index / 8
                if t < 4:
                    x, y = 10 * t, y0
                elif t < 8:
                    angle = math.pi / 2 * (t - 4) / 4
                    x, y = 40 + 20 * math.sin(angle), y0 + 20 * (1 - math.cos(angle))
                elif t < 12:
                    x, y = 60, y0 + 20 + 10 * (t - 8)
                elif t < 16:
                    angle = math.pi / 2 * (t - 12) / 4
                    x, y = 60 - 20 * (1 - math.cos(angle)), y0 + 60 + 20 * math.sin(angle)
                else:
                    x, y = 40 - 10 * (t - 16), y0 + 80
                points.append({"t": t, "x_m": x, "y_m": y})
            boats.append({"lane": lane, "points": points})
        with self.assertRaisesRegex(PhaseDetectionError, "multiple significant turns"):
            detect_six_boat_turn(boats)


if __name__ == "__main__":
    unittest.main()
