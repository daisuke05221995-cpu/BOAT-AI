#!/usr/bin/env python3
"""Forward-only, research-only selected-BUY calibration from PRIVATE backups.

There is deliberately no optimizer, BUY/SKIP threshold search, app write, or
permission to promote a policy. This tool evaluates the exact stored decisions
from the instrumented Android release, not hypothetical historical bets.

Usage:
    python scripts/roi_forward_calibration.py PRIVATE_BACKUP.json \
        --as-of 2026-11-20 --output PRIVATE_FORWARD_REPORT.json
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
import math
from pathlib import Path

from roi_recovery_diagnostic import structured_evidence, top_payout_sensitivity
from v016_live_money_eval import (
    JST, accounted, audit, evaluate, normalize_prediction, parse_date,
)


PROTOCOL_VERSION = "forward-selected-buy-v1"
PROTOCOL_FILE = "data/roi_forward_calibration_protocol_20261028.json"
START_DATE = "2026-10-29"  # Whole first JST day after the v0.18.22 release.
INSTRUMENTED_VERSION = "0.18.22"
MIN_BUYS = 360
MIN_ACTIVE_DAYS = 20


def refuse_sealed_q4(payload):
    """Do not accidentally evaluate the locked 2025 Q4 final holdout."""
    for row in payload.get("predictions", []):
        date = row.get("date") if isinstance(row, dict) else None
        if isinstance(date, str) and "2025-10-01" <= date <= "2025-12-31":
            raise ValueError("2025 Q4 final holdout is sealed; refuse to inspect it")


def roi_band(roi):
    if roi < 120:
        return "<120%"
    if roi < 140:
        return "120-139%"
    if roi < 160:
        return "140-159%"
    if roi < 200:
        return "160-199%"
    return ">=200%"


def hit_mass_band(probability):
    if probability < 0.10:
        return "<10%"
    if probability < 0.20:
        return "10-19%"
    if probability < 0.30:
        return "20-29%"
    if probability < 0.40:
        return "30-39%"
    return ">=40%"


def summary(rows):
    """Rows are tuples (normalized prediction, (expectedROI, pick hit mass))."""
    n = len(rows)
    if not n:
        return {
            "auditedBuyRaces": 0, "activeDays": 0, "stakeYen": 0, "payoutYen": 0,
            "profitYen": 0, "realizedRoiPercent": None,
            "stakeWeightedExpectedRoiPercent": None, "actualHits": 0,
            "expectedHits": None, "actualHitRatePercent": None,
            "expectedHitRatePercent": None, "hitRateGapPercentagePoints": None,
            "brierScore": None, "logLoss": None,
        }
    budget = sum(accounted(row)[0] for row, _ in rows)
    payout = sum(accounted(row)[1] for row, _ in rows)
    expected_payout = sum(accounted(row)[0] * info[0] / 100 for row, info in rows)
    hits = [int(row.get("resultCombination") in row["combinations"]) for row, _ in rows]
    masses = [info[1] for _, info in rows]
    actual = sum(hits)
    expected = sum(masses)
    eps = 1e-12
    return {
        "auditedBuyRaces": n,
        "activeDays": len({row["date"] for row, _ in rows}),
        "stakeYen": budget,
        "payoutYen": payout,
        "profitYen": payout - budget,
        "realizedRoiPercent": round(100 * payout / budget, 2) if budget else None,
        "stakeWeightedExpectedRoiPercent": (
            round(100 * expected_payout / budget, 2) if budget else None
        ),
        "actualHits": actual,
        "expectedHits": round(expected, 4),
        "actualHitRatePercent": round(100 * actual / n, 2),
        "expectedHitRatePercent": round(100 * expected / n, 2),
        "hitRateGapPercentagePoints": round(100 * (actual - expected) / n, 2),
        "brierScore": round(sum((hit - p) ** 2 for hit, p in zip(hits, masses)) / n, 6),
        "logLoss": round(-sum(
            hit * math.log(max(eps, p)) + (1 - hit) * math.log(max(eps, 1 - p))
            for hit, p in zip(hits, masses)
        ) / n, 6),
    }


def breakdown(rows, key, labels=None):
    groups = defaultdict(list)
    for item in rows:
        groups[key(*item)].append(item)
    labels = labels if labels is not None else sorted(groups)
    return [{"label": str(label), **summary(groups[label])} for label in labels]


def analyze(payload, as_of):
    refuse_sealed_q4(payload)
    if parse_date(as_of) < parse_date(START_DATE):
        raise ValueError(f"as-of must be >= {START_DATE}, after instrumentation release")

    # Preserve the original frozen evaluator's validation and duplicate guards.
    frozen = evaluate(payload, as_of)
    anchor = parse_date(as_of)
    records = [normalize_prediction(row) for row in payload.get("predictions", [])]
    records = [row for row in records if parse_date(row["date"]) <= anchor]
    prospective = [row for row in records
                   if row["date"] >= START_DATE and row.get("sourceAppVersion") == INSTRUMENTED_VERSION
                   and row.get("strategyId") == "value-v1" and row.get("evaluationEligible") is True
                   and row.get("recommended") is True]
    pending = [row for row in prospective if not row.get("settled")]
    settled = [row for row in prospective if row.get("settled")]
    audited = [row for row in settled if not audit(row)]
    invalid_audits = Counter(reason for row in settled for reason in audit(row))

    valid = []
    missing = 0
    invalid = 0
    for row in audited:
        data = structured_evidence(row)
        if data is None:
            if any(name in row for name in ("liveExpectedRoiPercent", "livePickAiProbabilities")):
                invalid += 1
            else:
                missing += 1
            continue
        # Reject impossible evidence sequence instead of silently assuming cutoff correctness.
        if row["decisionCapturedAt"] < row["liveOddsFetchedAt"]:
            invalid += 1
            continue
        valid.append((row, data))

    overall = summary(valid)
    days = breakdown(valid, lambda row, _: row["date"])
    target_met = overall["auditedBuyRaces"] >= MIN_BUYS and overall["activeDays"] >= MIN_ACTIVE_DAYS
    return {
        "reportVersion": PROTOCOL_VERSION,
        "protocolFile": PROTOCOL_FILE,
        "asOfJst": as_of,
        "firstEligibleDayJst": START_DATE,
        "exactAllowedSourceAppVersion": INSTRUMENTED_VERSION,
        "frozenEvaluatorProtocol": frozen["protocolVersion"],
        "researchOnly": True,
        "productionPromotionAllowed": False,
        "coverage": {
            "eligibleBuyDecisions": len(prospective),
            "pendingUnsettled": len(pending),
            "settledBuyDecisions": len(settled),
            "auditedSettledBuyDecisions": len(audited),
            "incompleteAudits": len(settled) - len(audited),
            "auditFailureCounts": dict(sorted(invalid_audits.items())),
            "validNumericSnapshots": len(valid),
            "missingNumericSnapshots": missing,
            "invalidNumericSnapshots": invalid,
        },
        "observedCalibration": overall,
        "payoutConcentration": top_payout_sensitivity([row for row, _ in valid]),
        "daily": days,
        "predeclaredExploratoryBands": {
            "selectedHitMass": breakdown(valid, lambda _, info: hit_mass_band(info[1]),
                ("<10%", "10-19%", "20-29%", "30-39%", ">=40%")),
            "expectedRoi": breakdown(valid, lambda _, info: roi_band(info[0]),
                ("<120%", "120-139%", "140-159%", "160-199%", ">=200%")),
        },
        "sampleGoal": {
            "minimumAuditedBuys": MIN_BUYS,
            "minimumDistinctActiveDays": MIN_ACTIVE_DAYS,
            "remainingBuys": max(0, MIN_BUYS - overall["auditedBuyRaces"]),
            "remainingActiveDays": max(0, MIN_ACTIVE_DAYS - overall["activeDays"]),
            "status": "READY_FOR_SEPARATE_PROTOCOL_REVIEW_ONLY" if target_met else "COLLECT_FORWARD_DATA",
        },
        "limitations": [
            "Only selected-buy probability mass, not all 120 predicted outcomes, is calibrated.",
            "Stored decisionCapturedAt is not independently verified against official race cutoff time.",
            "Realized monetary ROI is heavy-tailed; no observed subgroup is a production gate.",
            "The exact app version is pinned to avoid unregistered policy mixing.",
            "No original frozen 343-BUY baseline, 2025 Q4 holdout, or skipped races are relabelled.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="PRIVATE Android backup, never commit")
    parser.add_argument("--as-of", default=datetime.now(JST).date().isoformat())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.input.resolve() == args.output.resolve():
        parser.error("--output must not overwrite the private backup")
    report = analyze(json.loads(args.input.read_text(encoding="utf-8")), args.as_of)
    output = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
