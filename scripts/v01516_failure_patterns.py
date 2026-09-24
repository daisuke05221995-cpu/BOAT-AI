#!/usr/bin/env python3
"""Diagnose v0.15.16 pure-AI failure patterns without tuning.

Uses only the already-open 2025-07..08 development cache. September/Q4 are refused.
This script is descriptive: it does not search coefficients, thresholds, or policies.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np

from v01516_forecast_audit import COMBOS, COMBO_TEXT, COURSE_PRIOR, SCORE_TEMPERATURE, form_score


def safe_mean(x: np.ndarray) -> float | None:
    y = np.asarray(x, dtype=np.float64)
    y = y[np.isfinite(y)]
    return round(float(y.mean()), 6) if len(y) else None


def pct(num: int, den: int) -> float | None:
    return round(100.0 * num / den, 3) if den else None


def labels_from_edges(edges: list[float]) -> list[str]:
    return [f"[{edges[i]:g},{edges[i+1]:g})" for i in range(len(edges) - 1)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--protocol", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    rules = protocol["rules"]
    assert rules["tuningPerformed"] is False
    assert rules["changeProductionFormula"] is False
    assert rules["searchThresholds"] is False
    assert rules["selectWinningSubgroupAsPolicy"] is False
    assert rules["openSeptember"] is False
    assert rules["openFinalHoldout"] is False

    with np.load(args.cache, allow_pickle=False) as z:
        need = ["day_ordinal", "month", "actual_index", "current", "global_features", "usable", "combos"]
        missing = [k for k in need if k not in z.files]
        if missing:
            raise SystemExit(f"cache missing: {missing}")
        c = {k: z[k] for k in z.files}

    dates = np.asarray([date.fromordinal(int(x)) for x in c["day_ordinal"]], dtype=object)
    if len(dates) == 0:
        raise SystemExit("empty cache")
    if min(dates) < date(2025, 7, 1) or max(dates) > date(2025, 8, 31):
        raise SystemExit(f"date fence violated: {min(dates)}..{max(dates)}")
    if set(int(x) for x in c["month"]) != {7, 8}:
        raise SystemExit("July-August only")
    if not np.array_equal(c["combos"], COMBO_TEXT):
        raise SystemExit("combination order mismatch")

    boat = c["current"].astype(np.float64)
    glob = c["global_features"].astype(np.float64)
    actual = c["actual_index"].astype(int)
    usable = c["usable"].astype(bool) & (actual >= 0) & (actual < len(COMBOS))
    if int(usable.sum()) < 5000:
        raise SystemExit("too few usable races")

    score = form_score(boat)
    preview_course = boat[:, :, 17]
    lane_fallback = np.broadcast_to(np.arange(1, 7, dtype=np.float64), preview_course.shape)
    effective_course = np.where(np.isfinite(preview_course), preview_course, lane_fallback)
    course_idx = np.clip(effective_course.astype(int) - 1, 0, 5)
    raw = score + COURSE_PRIOR[course_idx]
    raw_max = raw.max(axis=1, keepdims=True)
    weights = np.exp((raw - raw_max) / SCORE_TEMPERATURE)
    total = weights.sum(axis=1)
    first_prob = weights / total[:, None]

    f, s, t = COMBOS[:, 0], COMBOS[:, 1], COMBOS[:, 2]
    wf, ws, wt = weights[:, f], weights[:, s], weights[:, t]
    d2 = total[:, None] - wf
    d3 = d2 - ws
    tri_prob = (wf / total[:, None]) * (ws / d2) * (wt / d3)
    tri_prob /= tri_prob.sum(axis=1, keepdims=True)
    tri_order = np.argsort(-tri_prob, axis=1, kind="stable")
    top4_hit = np.any(tri_order[:, :4] == actual[:, None], axis=1)

    first_order = np.argsort(-first_prob, axis=1, kind="stable")
    pred_first = first_order[:, 0] + 1
    actual_first = COMBOS[actual, 0] + 1
    top1_prob = first_prob[np.arange(len(first_prob)), first_order[:, 0]]
    top2_prob = first_prob[np.arange(len(first_prob)), first_order[:, 1]]
    margin = top1_prob - top2_prob
    lane1_adv = first_prob[:, 0] - np.max(first_prob[:, 1:], axis=1)

    changed = np.any(np.isfinite(preview_course) & (preview_course != lane_fallback), axis=1)
    wind = glob[:, 0] if glob.ndim == 2 and glob.shape[1] > 0 else np.full(len(usable), np.nan)
    wave = glob[:, 1] if glob.ndim == 2 and glob.shape[1] > 1 else np.full(len(usable), np.nan)

    lane1_raw_adv = raw[:, 0] - np.max(raw[:, 1:], axis=1)
    exhibition = boat[:, :, 15]
    preview_start = boat[:, :, 16]
    national = boat[:, :, 0]
    lane1_ex_delta = exhibition[:, 0] - np.nanmin(exhibition[:, 1:], axis=1)
    lane1_st_delta = preview_start[:, 0] - np.nanmin(preview_start[:, 1:], axis=1)
    lane1_nat_delta = national[:, 0] - np.nanmax(national[:, 1:], axis=1)

    def group(mask: np.ndarray) -> dict:
        m = usable & mask
        n = int(m.sum())
        correct = int(np.count_nonzero(m & (pred_first == actual_first)))
        return {
            "races": n,
            "share": pct(n, int(usable.sum())),
            "firstAccuracy": pct(correct, n),
            "trifectaTop4HitRate": pct(int(np.count_nonzero(m & top4_hit)), n),
            "meanTop1FirstProbability": safe_mean(top1_prob[m]),
            "meanTop1VsTop2Margin": safe_mean(margin[m]),
            "meanLane1Probability": safe_mean(first_prob[m, 0]),
            "meanLane1RawScoreAdvantage": safe_mean(lane1_raw_adv[m]),
            "meanLane1ExhibitionTimeDeltaToBestOther": safe_mean(lane1_ex_delta[m]),
            "meanLane1PreviewStartDeltaToBestOther": safe_mean(lane1_st_delta[m]),
            "meanLane1NationalWinRateDeltaToBestOther": safe_mean(lane1_nat_delta[m]),
        }

    classes = {
        "lane1_correct": (pred_first == 1) & (actual_first == 1),
        "lane1_false_positive": (pred_first == 1) & (actual_first != 1),
        "lane1_missed": (pred_first != 1) & (actual_first == 1),
        "outside_correct": (pred_first != 1) & (pred_first == actual_first),
        "outside_wrong": (pred_first != 1) & (actual_first != 1) & (pred_first != actual_first),
    }
    class_metrics = {name: group(mask) for name, mask in classes.items()}

    pred_lane = {str(lane): group(pred_first == lane) for lane in range(1, 7)}

    def binned(values: np.ndarray, edges: list[float]) -> dict:
        out = {}
        labels = labels_from_edges(edges)
        for i, label in enumerate(labels):
            lo, hi = edges[i], edges[i + 1]
            m = np.isfinite(values) & (values >= lo) & (values < hi)
            out[label] = group(m)
        return out

    fixed = protocol["fixedBins"]
    margin_bins = binned(margin, [float(x) for x in fixed["top1FirstProbabilityMargin"]])
    lane1_adv_bins = binned(lane1_adv, [float(x) for x in fixed["lane1ProbabilityAdvantage"]])
    wind_bins = binned(wind, [float(x) for x in fixed["windSpeed"]])
    wave_bins = binned(wave, [float(x) for x in fixed["waveHeight"]])
    course_change = {"unchanged": group(~changed), "changed": group(changed)}

    market = None
    if "odds" in c and "odds_usable" in c:
        odds = c["odds"].astype(np.float64)
        market_usable = usable & c["odds_usable"].astype(bool)
        market_usable &= np.isfinite(odds).all(axis=1) & (odds > 1.0).all(axis=1)
        inv = np.where(np.isfinite(odds) & (odds > 0), 1.0 / odds, 0.0)
        market_tri = inv / np.where(inv.sum(axis=1, keepdims=True) > 0, inv.sum(axis=1, keepdims=True), 1.0)
        market_first_prob = np.column_stack([market_tri[:, f == lane].sum(axis=1) for lane in range(6)])
        market_first = market_first_prob.argmax(axis=1) + 1
        agree = market_usable & (pred_first == market_first)
        disagree = market_usable & (pred_first != market_first)
        market_correct = int(np.count_nonzero(market_usable & (market_first == actual_first)))
        market = {
            "population": int(market_usable.sum()),
            "marketFirstAccuracy": pct(market_correct, int(market_usable.sum())),
            "aiMarketAgreementRate": pct(int(agree.sum()), int(market_usable.sum())),
            "agreement": group(agree),
            "disagreement": group(disagree),
            "note": "benchmark only; odds never affect the v0.15.16 forecast"
        }

    result = {
        "schemaVersion": 1,
        "strategy": "Android v0.15.16 pure AI failure-pattern diagnostic",
        "period": "2025-07-01..2025-08-31",
        "protocol": args.protocol.name,
        "holdoutOpened": False,
        "septemberOpened": False,
        "tuningPerformed": False,
        "productionChanged": False,
        "population": {"cacheRaces": int(len(usable)), "usableRaces": int(usable.sum())},
        "failureClasses": class_metrics,
        "predictedFirstLane": pred_lane,
        "top1MarginBins": margin_bins,
        "lane1ProbabilityAdvantageBins": lane1_adv_bins,
        "previewCourseChange": course_change,
        "windSpeedBins": wind_bins,
        "waveHeightBins": wave_bins,
        "marketBenchmark": market,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    total_u = int(usable.sum())
    lines = [
        "# v0.15.16 純AI 失敗パターン診断",
        "",
        "2025-07〜08開発期間のみ。9月/Q4未開封。係数・閾値・本番ロジック変更なし。",
        "",
        f"対象: {total_u:,}レース",
        "",
        "## 外し方の内訳",
        "",
        "|分類|件数|全体比|1着的中率|3連単Top4|Top1確率|Top1-Top2差|",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    jp = {
        "lane1_correct": "1号艇本命→1号艇勝ち",
        "lane1_false_positive": "1号艇本命→他艇勝ち",
        "lane1_missed": "他艇本命→1号艇勝ち",
        "outside_correct": "2〜6号艇本命→その艇勝ち",
        "outside_wrong": "2〜6号艇本命→別の2〜6号艇勝ち",
    }
    for key in classes:
        x = class_metrics[key]
        lines.append(f"|{jp[key]}|{x['races']:,}|{x['share']}%|{x['firstAccuracy']}%|{x['trifectaTop4HitRate']}%|{x['meanTop1FirstProbability']}|{x['meanTop1VsTop2Margin']}|")

    lines += ["", "## 進入変化", ""]
    for key in ("unchanged", "changed"):
        x = course_change[key]
        lines.append(f"- {key}: {x['races']:,}レース / 1着 {x['firstAccuracy']}% / Top4 {x['trifectaTop4HitRate']}% / 平均本命差 {x['meanTop1VsTop2Margin']}")

    lines += ["", "## 固定した自信差ビン", ""]
    for label, x in margin_bins.items():
        lines.append(f"- {label}: {x['races']:,}レース / 1着 {x['firstAccuracy']}% / Top4 {x['trifectaTop4HitRate']}%")

    if market:
        lines += [
            "",
            "## 市場との比較（ベンチマークのみ）",
            "",
            f"- 市場1着Top1: {market['marketFirstAccuracy']}%",
            f"- AIと市場の1着本命一致率: {market['aiMarketAgreementRate']}%",
            f"- 一致時AI 1着率: {market['agreement']['firstAccuracy']}%",
            f"- 不一致時AI 1着率: {market['disagreement']['firstAccuracy']}%",
        ]

    lines += [
        "",
        "この結果から勝っている区分だけを購入条件へ採用しない。次のモデル変更を行う場合は別protocolで新仮説として事前登録する。",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
