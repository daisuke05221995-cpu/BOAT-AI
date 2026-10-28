#!/usr/bin/env python3
"""Research-only BUY/ROI failure diagnostics for a PRIVATE Android backup.

The frozen live-money evaluator owns inclusion, audit, accounting and
de-duplication. This script adds descriptive groupings only; it never searches
BUY thresholds, changes the Android app, or uploads individual records.

Usage:
    python scripts/roi_recovery_diagnostic.py PRIVATE_BACKUP.json \
        --as-of 2026-10-28 --output PRIVATE_ROI_DIAGNOSTIC.json
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import re

from v016_live_money_eval import (
    JST, accounted, audit, candidate, evaluate, normalize_prediction,
    parse_date, statistics,
)


FROZEN_END = "2026-10-14"
NEW_POLICY_START = "2026-10-15"
NEW_POLICY_VERSION = (0, 18, 15)
FROZEN_REFERENCE = {
    "asOfJst": FROZEN_END,
    "auditedBuys": 343,
    "hits": 101,
    "stakeYen": 764700,
    "payoutYen": 593480,
    "profitYen": -171220,
    "roiPercent": 77.61,
    "source": "data/FORMAL_LIVE_EVAL_20261014_343.md",
    "rawPrivateBackupAvailableInRepository": False,
}


def production_version(value):
    """Only a row's own three-part version proves the prospective regime."""
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        return None
    return tuple(map(int, value.split(".")))


def source_class(row):
    source = row.get("liveOddsSource") or "UNKNOWN"
    if "BoatraceCSV" in source:
        return "BoatraceCSV/fallback"
    if "公式PC" in source:
        return "official-PC"
    if "公式スマホ" in source:
        return "official-mobile"
    return "other/unknown"


def compact_stats(rows):
    result = statistics(rows)
    result.pop("cumulativeProfitCurve")
    return result


def top_payout_sensitivity(rows):
    """Descriptive robustness, excluding entire races (not individual picks)."""
    amounts = sorted((accounted(row) for row in rows), key=lambda pair: pair[1], reverse=True)
    total_stake = sum(stake for stake, _ in amounts)
    total_payout = sum(payout for _, payout in amounts)
    output = {}
    for removed in (1, 3, 5):
        taken = amounts[:removed]
        stake = total_stake - sum(x for x, _ in taken)
        payout = total_payout - sum(x for _, x in taken)
        output[f"withoutTop{removed}PayoutRaces"] = {
            "remainingRaces": max(0, len(rows) - removed),
            "roiPercent": round(100 * payout / stake, 2) if stake else None,
            "profitYen": payout - stake,
        }
    output["largestPayoutSharePercent"] = (
        round(100 * amounts[0][1] / total_payout, 2)
        if amounts and total_payout else None
    )
    return output


def cohort_stats(rows):
    money = compact_stats(rows)
    return {
        "auditedBuys": len(rows),
        "activeDays": len({row["date"] for row in rows}),
        "money": money,
        "payoutConcentration": top_payout_sensitivity(rows),
    }


def breakdown(rows, dimension):
    groups = defaultdict(list)
    for row in rows:
        groups[dimension(row)].append(row)
    return [
        {"label": str(label), **cohort_stats(group),
         "researchOnly": True}
        for label, group in sorted(groups.items(), key=lambda item: str(item[0]))
    ]


def analyze(payload, as_of):
    # Mandatory first step: reuse the unchanged frozen evaluator for validation,
    # duplicate detection and exact auditable-money reconciliation.
    frozen = evaluate(payload, as_of)
    anchor = parse_date(as_of)
    predictions = payload.get("predictions", [])
    candidates = [normalize_prediction(original) for original in predictions]
    candidates = [row for row in candidates if candidate(row) and parse_date(row["date"]) <= anchor]
    audited = [row for row in candidates if not audit(row)]
    assert len(audited) == frozen["performance"]["all"]["audit"]["auditedBuyCount"]
    assert compact_stats(audited) == {
        key: value for key, value in frozen["performance"]["all"]["money"].items()
        if key != "cumulativeProfitCurve"
    }

    old = [r for r in audited if r["date"] <= FROZEN_END]
    new = [r for r in audited if r["date"] >= NEW_POLICY_START
           and (production_version(r.get("sourceAppVersion")) or (0,)) >= NEW_POLICY_VERSION]
    unattributed = [r for r in audited if r["date"] >= NEW_POLICY_START and r not in new]
    new_candidates = [r for r in candidates if r["date"] >= NEW_POLICY_START
                      and (production_version(r.get("sourceAppVersion")) or (0,)) >= NEW_POLICY_VERSION]
    failure_counts = Counter(reason for row in new_candidates for reason in audit(row))

    return {
        "reportVersion": "roi-recovery-diagnostic-1",
        "asOfJst": as_of,
        "basedOnFrozenEvaluator": frozen["protocolVersion"],
        "researchOnly": True,
        "productionPromotionAllowed": False,
        "frozen343Reference": FROZEN_REFERENCE,
        "oldDateAudited": cohort_stats(old),
        "prospectiveNewPolicy": {
            **cohort_stats(new),
            "settledCandidateBuys": len(new_candidates),
            "incompleteAudits": len(new_candidates) - len(new),
            "auditFailureCounts": dict(sorted(failure_counts.items())),
            "breakdowns": {
                "selectedPointCount": breakdown(new, lambda r: len(r["combinations"])),
                "firstLane": breakdown(new, lambda r: r.get("firstLane") or "UNKNOWN"),
                "liveOddsSource": breakdown(new, source_class),
                "sourceAppVersion": breakdown(new, lambda r: r.get("sourceAppVersion")),
            },
            "validationStatus": (
                "INSUFFICIENT_NEW_PROSPECTIVE_SAMPLE"
                if len(new) < 360 or len({r["date"] for r in new}) < 20
                else "REQUIRES_SEPARATE_PREREGISTERED_EVALUATION"
            ),
        },
        "unattributedPostCutoff": cohort_stats(unattributed),
        "allAuditedMoneyMatchesFrozenEvaluator": True,
        "limitations": [
            "Old 343 BUYs are a frozen reference, not a fresh independent test.",
            "Only date >= 2026-10-15 AND row-level sourceAppVersion >= 0.18.15 is prospective.",
            "Missing version rows are quarantined, never inferred from the backup envelope.",
            "No calibration of estimated ROI is possible without per-decision structured expected ROI.",
            "No single slice, payout concentration or same-sample threshold is a promotion criterion.",
            "No 2025 Q4 holdout or historical final-like odds are used.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Private BOAT-AI-backup.json")
    parser.add_argument("--as-of", default=datetime.now(JST).date().isoformat())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.input.resolve() == args.output.resolve():
        parser.error("--output must not overwrite the private backup")
    report = analyze(json.loads(args.input.read_text(encoding="utf-8")), args.as_of)
    result = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
