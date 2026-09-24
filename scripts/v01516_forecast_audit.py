#!/usr/bin/env python3
"""Audit Android v0.15.16 pure-AI forecast without tuning.

The audit is fenced to the r4 July-August 2025 development cache. September and
2025 Q4 are refused. Official odds are optional and used only for an external market
benchmark; they never affect the v0.15.16 forecast probabilities or ordering.
"""
from __future__ import annotations

import argparse
import itertools
import json
from datetime import date
from pathlib import Path

import numpy as np

COMBOS = np.asarray(list(itertools.permutations(range(6), 3)), dtype=np.int16)
COMBO_TEXT = np.asarray(["-".join(str(x + 1) for x in row) for row in COMBOS])
SCORE_TEMPERATURE = 14.0
COURSE_PRIOR = np.asarray([8.0, 4.0, 2.0, 0.0, -1.5, -3.0], dtype=np.float64)
TOP_K = (1, 2, 4, 8)


def nvl(x: np.ndarray, value: float = 0.0) -> np.ndarray:
    return np.where(np.isfinite(x), x, value)


def form_score(boat: np.ndarray) -> np.ndarray:
    national = nvl(boat[:, :, 0]) * 5.2
    local = nvl(boat[:, :, 1]) * 2.6
    motor = nvl(boat[:, :, 6]) * 0.22
    assigned_boat = nvl(boat[:, :, 8]) * 0.08
    avg_start = boat[:, :, 10]
    start = np.where(np.isfinite(avg_start), np.maximum(0.0, (0.22 - avg_start) * 58.0), 0.0)
    exhibition = boat[:, :, 15]
    exhibition_score = np.where(np.isfinite(exhibition), np.maximum(-5.0, (6.95 - exhibition) * 18.0), 0.0)
    preview_start = boat[:, :, 16]
    preview_start_score = np.where(np.isfinite(preview_start), np.maximum(-4.0, (0.18 - preview_start) * 32.0), 0.0)
    return national + local + motor + assigned_boat + start + exhibition_score + preview_start_score


def ece_top1(prob: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    confidence = prob.max(axis=1)
    prediction = prob.argmax(axis=1)
    correct = (prediction == actual).astype(np.float64)
    edges = np.linspace(0.0, 1.0, bins + 1)
    out = 0.0
    n = len(actual)
    for i in range(bins):
        if i == bins - 1:
            mask = (confidence >= edges[i]) & (confidence <= edges[i + 1])
        else:
            mask = (confidence >= edges[i]) & (confidence < edges[i + 1])
        count = int(mask.sum())
        if count:
            out += count / n * abs(float(correct[mask].mean()) - float(confidence[mask].mean()))
    return out


def metrics(prob: np.ndarray, actual: np.ndarray) -> dict:
    if len(actual) == 0:
        return {"races": 0}
    p_actual = prob[np.arange(len(actual)), actual]
    order = np.argsort(-prob, axis=1, kind="stable")
    onehot = np.zeros_like(prob)
    onehot[np.arange(len(actual)), actual] = 1.0
    out = {
        "races": int(len(actual)),
        "trifectaLogloss": round(float(-np.log(np.maximum(p_actual, 1e-15)).mean()), 6),
        "trifectaBrier": round(float(np.square(prob - onehot).sum(axis=1).mean()), 6),
        "topComboEce": round(float(ece_top1(prob, actual)), 6),
        "meanTopComboProbability": round(float(prob.max(axis=1).mean()), 6),
    }
    for k in TOP_K:
        hit = np.any(order[:, :k] == actual[:, None], axis=1)
        out[f"trifectaTop{k}HitRate"] = round(float(hit.mean() * 100.0), 3)
        out[f"trifectaTop{k}Hits"] = int(hit.sum())
    first_prob = np.column_stack([prob[:, COMBOS[:, 0] == lane].sum(axis=1) for lane in range(6)])
    actual_first = COMBOS[actual, 0]
    first_order = np.argsort(-first_prob, axis=1, kind="stable")
    top1 = first_order[:, 0]
    out["firstTop1Accuracy"] = round(float((top1 == actual_first).mean() * 100.0), 3)
    out["firstTop1Hits"] = int((top1 == actual_first).sum())
    out["firstTop2Coverage"] = round(float(np.any(first_order[:, :2] == actual_first[:, None], axis=1).mean() * 100.0), 3)
    out["firstTop2Hits"] = int(np.any(first_order[:, :2] == actual_first[:, None], axis=1).sum())
    return out


def segment_metrics(mask: np.ndarray, prob: np.ndarray, actual: np.ndarray) -> dict:
    idx = np.flatnonzero(mask)
    return metrics(prob[idx], actual[idx]) if len(idx) else {"races": 0}


def rate(num: int, den: int) -> float | None:
    return round(num * 100.0 / den, 3) if den else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    assert protocol["rules"]["tuningPerformed"] is False
    assert protocol["rules"]["openSeptember"] is False
    assert protocol["rules"]["openFinalHoldout"] is False

    with np.load(args.cache, allow_pickle=False) as z:
        required = ["day_ordinal", "month", "venue", "actual_index", "current", "usable", "combos"]
        missing = [k for k in required if k not in z.files]
        if missing:
            raise SystemExit(f"cache missing: {missing}")
        c = {k: z[k] for k in z.files}

    dates = np.asarray([date.fromordinal(int(x)) for x in c["day_ordinal"]], dtype=object)
    if not len(dates):
        raise SystemExit("empty cache")
    if min(dates) < date(2025, 7, 1) or max(dates) > date(2025, 8, 31):
        raise SystemExit(f"date fence violated: {min(dates)}..{max(dates)}")
    if set(int(x) for x in c["month"]) != {7, 8}:
        raise SystemExit("audit must contain July-August only")
    if not np.array_equal(c["combos"], COMBO_TEXT):
        raise SystemExit("combination order mismatch")

    boat = c["current"].astype(np.float64)
    if boat.ndim != 3 or boat.shape[1] != 6 or boat.shape[2] < 18:
        raise SystemExit(f"unexpected current feature shape: {boat.shape}")

    usable = c["usable"].astype(bool)
    actual = c["actual_index"].astype(int)
    usable &= (actual >= 0) & (actual < len(COMBOS))
    idx = np.flatnonzero(usable)
    if len(idx) < 5000:
        raise SystemExit(f"too few usable races: {len(idx)}")

    score = form_score(boat)
    preview_course = boat[:, :, 17]
    lane_fallback = np.broadcast_to(np.arange(1, 7, dtype=np.float64), preview_course.shape)
    effective_course = np.where(np.isfinite(preview_course), preview_course, lane_fallback)
    course_idx = np.clip(effective_course.astype(int) - 1, 0, 5)
    raw = score + COURSE_PRIOR[course_idx]
    raw_max = raw.max(axis=1, keepdims=True)
    weights = np.exp((raw - raw_max) / SCORE_TEMPERATURE)
    total = weights.sum(axis=1)

    f = COMBOS[:, 0]
    s = COMBOS[:, 1]
    t = COMBOS[:, 2]
    wf, ws, wt = weights[:, f], weights[:, s], weights[:, t]
    d2 = total[:, None] - wf
    d3 = d2 - ws
    prob = (wf / total[:, None]) * (ws / d2) * (wt / d3)
    prob /= prob.sum(axis=1, keepdims=True)

    prob_u = prob[idx]
    actual_u = actual[idx]
    overall = metrics(prob_u, actual_u)

    first_prob_all = weights / total[:, None]
    pred_first = first_prob_all.argmax(axis=1) + 1
    actual_first = COMBOS[actual, 0] + 1
    lane_dist = {}
    for lane in range(1, 7):
        m = usable & (pred_first == lane)
        count = int(m.sum())
        first_hits = int(np.count_nonzero(m & (actual_first == lane)))
        lane_dist[str(lane)] = {
            "predictions": count,
            "share": rate(count, int(usable.sum())),
            "firstAccuracyWhenPredicted": rate(first_hits, count),
            "trifectaTop4HitRate": segment_metrics(m, prob, actual).get("trifectaTop4HitRate"),
        }

    actual_lane_dist = {
        str(lane): {
            "wins": int(np.count_nonzero(usable & (actual_first == lane))),
            "share": rate(int(np.count_nonzero(usable & (actual_first == lane))), int(usable.sum())),
        }
        for lane in range(1, 7)
    }

    month_segments = {
        f"2025-{month:02d}": segment_metrics(usable & (c["month"].astype(int) == month), prob, actual)
        for month in (7, 8)
    }

    venue_segments = {}
    for venue in sorted(set(int(v) for v in c["venue"][usable])):
        m = usable & (c["venue"].astype(int) == venue)
        venue_segments[str(venue)] = segment_metrics(m, prob, actual)

    changed = np.any(np.isfinite(preview_course) & (preview_course != lane_fallback), axis=1)
    course_segments = {
        "unchanged": segment_metrics(usable & ~changed, prob, actual),
        "changed": segment_metrics(usable & changed, prob, actual),
        "changedRaceShare": rate(int(np.count_nonzero(usable & changed)), int(usable.sum())),
    }

    market = None
    if "odds" in c and "odds_usable" in c:
        odds = c["odds"].astype(np.float64)
        market_mask = usable & c["odds_usable"].astype(bool)
        market_mask &= np.isfinite(odds).all(axis=1) & (odds > 1.0).all(axis=1)
        midx = np.flatnonzero(market_mask)
        if len(midx):
            inv = 1.0 / odds[midx]
            market_prob = inv / inv.sum(axis=1, keepdims=True)
            market = {
                "population": int(len(midx)),
                "metrics": metrics(market_prob, actual[midx]),
                "note": "benchmark only; odds do not affect v0.15.16 forecast"
            }

    result = {
        "schemaVersion": 1,
        "strategy": "Android v0.15.16 pure AI exact-formula audit",
        "period": "2025-07-01..2025-08-31",
        "protocol": args.protocol.name,
        "holdoutOpened": False,
        "septemberOpened": False,
        "tuningPerformed": False,
        "population": {"cacheRaces": int(len(usable)), "usableRaces": int(usable.sum())},
        "overall": overall,
        "predictedFirstLane": lane_dist,
        "actualFirstLane": actual_lane_dist,
        "monthly": month_segments,
        "venue": venue_segments,
        "previewCourseChange": course_segments,
        "marketBenchmark": market,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# v0.15.16 純AI予想監査",
        "",
        "期間: 2025-07-01〜2025-08-31（9月/Q4未開封、調整なし）",
        "",
        f"- 対象: {overall['races']:,}レース",
        f"- 1着Top1的中率: {overall['firstTop1Accuracy']}%",
        f"- 1着Top2カバー率: {overall['firstTop2Coverage']}%",
        f"- 3連単Top1的中率: {overall['trifectaTop1HitRate']}%",
        f"- 3連単Top2的中率: {overall['trifectaTop2HitRate']}%",
        f"- 3連単Top4的中率: {overall['trifectaTop4HitRate']}%",
        f"- 3連単Top8的中率: {overall['trifectaTop8HitRate']}%",
        f"- Trifecta LogLoss: {overall['trifectaLogloss']}",
        f"- Trifecta Brier: {overall['trifectaBrier']}",
        f"- Top買い目 ECE: {overall['topComboEce']}",
        "",
        "## 1着本命の艇番分布",
        "",
        "|艇|予想数|予想比率|その艇を本命にした時の1着率|Top4 3連単的中率|",
        "|---:|---:|---:|---:|---:|",
    ]
    for lane in range(1, 7):
        x = lane_dist[str(lane)]
        lines.append(f"|{lane}|{x['predictions']:,}|{x['share']}%|{x['firstAccuracyWhenPredicted']}%|{x['trifectaTop4HitRate']}%|")
    lines += ["", "## 月別", "", "|月|レース|1着Top1|1着Top2|3連単Top4|3連単Top8|", "|---|---:|---:|---:|---:|---:|"]
    for key, x in month_segments.items():
        lines.append(f"|{key}|{x['races']:,}|{x['firstTop1Accuracy']}%|{x['firstTop2Coverage']}%|{x['trifectaTop4HitRate']}%|{x['trifectaTop8HitRate']}%|")
    lines += [
        "",
        "## 進入変化",
        "",
        f"- 進入変化あり比率: {course_segments['changedRaceShare']}%",
        f"- 変化なし: {course_segments['unchanged'].get('races',0):,}レース / 1着Top1 {course_segments['unchanged'].get('firstTop1Accuracy')}% / Top4 {course_segments['unchanged'].get('trifectaTop4HitRate')}%",
        f"- 変化あり: {course_segments['changed'].get('races',0):,}レース / 1着Top1 {course_segments['changed'].get('firstTop1Accuracy')}% / Top4 {course_segments['changed'].get('trifectaTop4HitRate')}%",
        "",
        "この監査は診断専用。結果を見て同じ7〜8月へ係数・閾値を再調整しない。市場オッズは比較ベンチマークにのみ使用し、v0.15.16予想には混ぜていない。",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
