"""Offline, fail-closed video tracking PoC for six BOAT AI exhibition boats.

Uses FFmpeg's decoder and deterministic color-component tracking. A venue camera
calibration and six one-time color/position seeds are mandatory; this is NOT a
trained boat detector and is not reliable on uncalibrated broadcast footage.
No video is downloaded, uploaded or incorporated into Android BUY decisions.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Iterable, Iterator

from .kinematics import InvalidTrack, measurements_from_tracks
from .scoring import evaluate_race


class VideoTrackingError(ValueError):
    pass


PHASES = ("runup", "straight", "turn", "exit")


def _point(value: Any) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise VideoTrackingError("calibration point must be [x, y]")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise VideoTrackingError("non-finite calibration point")
    return float(value[0]), float(value[1])


def _solve_linear(matrix: list[list[float]], targets: list[float]) -> list[float]:
    """Small, pivoted 8x8 system; no OpenCV/scientific runtime dependency."""
    n = len(targets)
    rows = [list(matrix[i]) + [targets[i]] for i in range(n)]
    if n != 8 or any(len(row) != 9 for row in rows):
        raise VideoTrackingError("homography requires exactly four fit points")
    for col in range(n):
        best = max(range(col, n), key=lambda row: abs(rows[row][col]))
        if abs(rows[best][col]) < 1e-10:
            raise VideoTrackingError("degenerate homography anchors")
        rows[col], rows[best] = rows[best], rows[col]
        pivot = rows[col][col]
        for j in range(col, n + 1):
            rows[col][j] /= pivot
        for i in range(n):
            if i == col:
                continue
            factor = rows[i][col]
            for j in range(col, n + 1):
                rows[i][j] -= factor * rows[col][j]
    return [rows[i][-1] for i in range(n)]


def homography_from_anchors(calibration: dict[str, Any]) -> tuple[list[float], float]:
    """Fit four points, check at least two independent calibration points in meters."""
    anchors = calibration.get("anchors")
    if not isinstance(anchors, list) or len(anchors) < 6:
        raise VideoTrackingError("four fit and at least two holdout anchors required")
    controls = []
    for item in anchors:
        if not isinstance(item, dict):
            raise VideoTrackingError("invalid calibration anchor")
        controls.append((_point(item.get("pixel")), _point(item.get("meters"))))
    matrix: list[list[float]] = []
    targets: list[float] = []
    for (x, y), (u, v) in controls[:4]:
        matrix.extend([[x, y, 1.0, 0, 0, 0, -x * u, -y * u],
                       [0, 0, 0, x, y, 1.0, -x * v, -y * v]])
        targets.extend([u, v])
    h = _solve_linear(matrix, targets)
    errors = []
    for pixel, meters in controls[4:]:
        actual = project_point(h, pixel)
        errors.append(math.dist(actual, meters))
    rms = math.sqrt(sum(x * x for x in errors) / len(errors))
    if not math.isfinite(rms) or rms > 1.0:
        raise VideoTrackingError(f"holdout calibration error {rms:.3f}m exceeds 1.0m")
    return h, rms


def project_point(h: list[float], pixel: tuple[float, float]) -> tuple[float, float]:
    x, y = pixel
    divisor = h[6] * x + h[7] * y + 1
    if abs(divisor) < 1e-9:
        raise VideoTrackingError("unprojectable point")
    return ((h[0] * x + h[1] * y + h[2]) / divisor,
            (h[3] * x + h[4] * y + h[5]) / divisor)


def _component_center(
    rgb_frame: bytes, width: int, height: int, center: tuple[float, float],
    target: tuple[int, int, int], radius: int, tolerance: int, min_pixels: int
) -> tuple[tuple[float, float], float] | None:
    """Largest contiguous color blob near previous position, never whole-frame guessing."""
    cx, cy = center
    x0, x1 = max(0, int(cx) - radius), min(width, int(cx) + radius + 1)
    y0, y1 = max(0, int(cy) - radius), min(height, int(cy) + radius + 1)
    matches: dict[tuple[int, int], int] = {}
    tolerance_sq = tolerance * tolerance
    for y in range(y0, y1):
        for x in range(x0, x1):
            if (x - cx) ** 2 + (y - cy) ** 2 > radius * radius:
                continue
            p = (y * width + x) * 3
            distance_sq = sum((rgb_frame[p + c] - target[c]) ** 2 for c in range(3))
            if distance_sq <= tolerance_sq:
                matches[x, y] = distance_sq
    components = []
    while matches:
        seed = next(iter(matches))
        stack = [seed]
        pixels = []
        while stack:
            point = stack.pop()
            distance = matches.pop(point, None)
            if distance is None:
                continue
            pixels.append((point, distance))
            x, y = point
            stack.extend([(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)])
        if len(pixels) >= min_pixels:
            x_avg = sum(p[0][0] for p in pixels) / len(pixels)
            y_avg = sum(p[0][1] for p in pixels) / len(pixels)
            mean_distance = sum(d for _, d in pixels) / len(pixels)
            components.append((len(pixels), math.dist((x_avg, y_avg), center),
                               (x_avg, y_avg), mean_distance))
    if not components:
        return None
    # Prefer a large connected color region, then the nearest to predicted location.
    component = max(components, key=lambda x: (x[0], -x[1]))
    confidence = 1.0 - math.sqrt(component[3]) / max(tolerance, 1)
    return component[2], max(0.0, min(1.0, confidence))


def _phases(config: dict[str, Any]) -> list[tuple[str, float, float]]:
    windows = config.get("phase_windows")
    if not isinstance(windows, list) or len(windows) != 4:
        raise VideoTrackingError("four phase windows required; no guessed video phase labels")
    result = []
    for window in windows:
        if not isinstance(window, dict):
            raise VideoTrackingError("invalid phase window")
        name, start, end = window.get("phase"), window.get("start_s"), window.get("end_s")
        if name not in PHASES or not isinstance(start, (float, int)) or not isinstance(end, (float, int)):
            raise VideoTrackingError("invalid phase timing")
        if isinstance(start, bool) or isinstance(end, bool) or not (0 <= start < end <= 180):
            raise VideoTrackingError("phase times outside safe clip range")
        result.append((name, float(start), float(end)))
    if tuple(x[0] for x in result) != PHASES or any(a[2] > b[1] for a, b in zip(result, result[1:])):
        raise VideoTrackingError("phase windows must be ordered and nonoverlapping")
    return result


def track_frames(
    config: dict[str, Any], frames: Iterable[tuple[float, bytes]]
) -> dict[str, Any]:
    """Track colored boats in calibrated raw RGB frames.

    Each boat requires a one-time seed and distinct color in this PoC.
    Failing any quality gate rejects the whole race downstream.
    """
    width, height = int(config["width"]), int(config["height"])
    if not (64 <= width <= 1920 and 64 <= height <= 1080):
        raise VideoTrackingError("unsupported frame size")
    h, calibration_error = homography_from_anchors(config["calibration"])
    marker = project_point(h, _point(config["calibration"]["turn_marker_pixel"]))
    windows = _phases(config)
    entries = config.get("boats")
    if not isinstance(entries, list) or len(entries) != 6 or {b.get("lane") for b in entries if isinstance(b, dict)} != set(range(1, 7)):
        raise VideoTrackingError("six seeded boat colors/positions required")
    boats = {}
    target_colors: list[tuple[tuple[int, int, int], int]] = []
    for item in entries:
        color = item.get("rgb")
        if not isinstance(color, list) or len(color) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in color):
            raise VideoTrackingError("invalid RGB target")
        radius, tolerance, min_pixels = (item.get("radius_px", 24), item.get("tolerance", 40),
                                         item.get("min_pixels", 5))
        if any(type(v) is not int for v in (radius, tolerance, min_pixels)) or not (3 <= radius <= 100 and 1 <= tolerance <= 100 and 2 <= min_pixels <= 250):
            raise VideoTrackingError("invalid tracking thresholds")
        if any(math.dist(color, known_color) <= tolerance + known_tolerance
               for known_color, known_tolerance in target_colors):
            raise VideoTrackingError("boat colors overlap; lane identity is ambiguous")
        target_colors.append((tuple(color), tolerance))
        boats[item["lane"]] = {
            "seed": _point(item.get("start_px")), "rgb": tuple(color),
            "radius": radius, "tolerance": tolerance, "min_pixels": min_pixels,
            "points": [], "confidence": [], "expected": 0, "detected": 0,
        }
    last_t = -1.0
    for t, frame in frames:
        if not math.isfinite(t) or t <= last_t:
            raise VideoTrackingError("video timestamps not increasing")
        last_t = t
        if len(frame) != width * height * 3:
            raise VideoTrackingError("corrupt RGB frame size")
        phase = next((p for p, start, end in windows if start <= t < end), None)
        if phase is None:
            continue
        for data in boats.values():
            data["expected"] += 1
            hit = _component_center(
                frame, width, height, data["seed"], data["rgb"],
                data["radius"], data["tolerance"], data["min_pixels"]
            )
            if hit is None:
                continue
            center, confidence = hit
            data["seed"] = center
            data["detected"] += 1
            data["confidence"].append(confidence)
            x_m, y_m = project_point(h, center)
            data["points"].append({"phase": phase, "t": round(t, 4),
                                   "x_m": round(x_m, 5), "y_m": round(y_m, 5)})
    return {
        "turn_marker_m": {"x_m": round(marker[0], 5), "y_m": round(marker[1], 5)},
        "tracking_method": "seeded_color_components_v1_not_a_trained_detector",
        "boats": [
            {
                "lane": lane,
                "quality": {
                    "track_coverage": round(data["detected"] / max(data["expected"], 1), 5),
                    "detector_confidence": round(
                        sum(data["confidence"]) / max(len(data["confidence"]), 1), 5
                    ),
                    "calibration_error_m": round(calibration_error, 5),
                },
                "points": data["points"],
            } for lane, data in sorted(boats.items())
        ],
    }


def decode_video(path: Path, width: int, height: int, fps: int, duration: int) -> Iterator[tuple[float, bytes]]:
    """Stream frames from a local MP4 through FFmpeg, never saving extracted frames."""
    if fps < 2 or fps > 30 or duration < 1 or duration > 180:
        raise VideoTrackingError("unsafe decode rate or duration")
    if not path.is_file():
        raise VideoTrackingError("local video file not found")
    process = subprocess.Popen(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path),
         "-t", str(duration), "-vf", f"fps={fps},scale={width}:{height}",
         "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    frame_size = width * height * 3
    try:
        index = 0
        while True:
            chunk = process.stdout.read(frame_size)  # type: ignore[union-attr]
            if not chunk:
                break
            if len(chunk) != frame_size:
                raise VideoTrackingError("truncated decoded frame")
            yield index / fps, chunk
            index += 1
        if process.wait(timeout=15) != 0:
            error = process.stderr.read(500).decode("utf-8", errors="replace")  # type: ignore[union-attr]
            raise VideoTrackingError(f"FFmpeg decoder failed: {error}")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()  # type: ignore[union-attr]
        process.stderr.close()  # type: ignore[union-attr]


def analyze_video(path: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Real video pixels -> calibrated tracks -> 7 measurements -> 5 shadow indices."""
    video = config.get("video")
    if not isinstance(video, dict):
        raise VideoTrackingError("video source provenance missing")
    size = path.stat().st_size
    if size <= 0 or size > 500 * 1024 * 1024:
        raise VideoTrackingError("video size exceeds local processing guard")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    tracking_config = config.get("tracking")
    if not isinstance(tracking_config, dict):
        raise VideoTrackingError("tracking calibration missing")
    try:
        tracks = track_frames(
            tracking_config,
            decode_video(
                path, int(tracking_config["width"]), int(tracking_config["height"]),
                int(tracking_config.get("fps", 10)), int(tracking_config.get("duration_s", 120))
            )
        )
        boats = measurements_from_tracks(tracks)
        for boat in boats:
            m = boat["measurements"]
            if (m["straight_speed_mps"] > 40 or m["turn_speed_mps"] > 40 or
                    abs(m["runup_acceleration_mps2"]) > 15 or
                    abs(m["exit_acceleration_mps2"]) > 15):
                raise VideoTrackingError("implausible speed/acceleration from video calibration")
    except (InvalidTrack, VideoTrackingError) as exc:
        return {
            "schema_version": 1, "status": "UNUSABLE", "reason": str(exc),
            "forecast_input_allowed": False, "purchase_decision_allowed": False,
        }
    evidence = {
        "schema_version": 1,
        "race": config.get("race"),
        "capture": {
            "source_id": video.get("source_id"),
            "permission_reference": video.get("permission_reference"),
            "video_sha256": digest.hexdigest(),
            "detector_version": tracks["tracking_method"],
            "calibration_version": tracking_config.get("calibration", {}).get("id"),
            # Must refer to the LAST frame, not the beginning of the recording.
            "captured_at": video.get("recording_completed_at"),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        },
        "boats": boats,
    }
    score = evaluate_race(evidence)
    score["video_analysis_method"] = tracks["tracking_method"]
    score["video_metadata_only"] = True
    return score


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path, help="existing locally held MP4; no auto download")
    parser.add_argument("--config", required=True, type=Path, help="camera anchors, six color seeds, phase windows")
    parser.add_argument("--output", required=True, type=Path, help="metadata-only research result JSON")
    args = parser.parse_args()
    result = analyze_video(args.video, json.loads(args.config.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "reason": result.get("reason"),
                      "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
