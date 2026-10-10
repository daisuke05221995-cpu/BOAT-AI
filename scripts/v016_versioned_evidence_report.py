#!/usr/bin/env python3
"""Summarize row-versioned prediction evidence using the unchanged frozen evaluator.

Usage: python scripts/v016_versioned_evidence_report.py PRIVATE_BACKUP.json \
    --as-of YYYY-MM-DD --output PRIVATE_REPORT.json
No private backup is bundled, fetched, uploaded, or modified by this helper.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path

from v016_live_money_eval import JST, PROTOCOL, evaluate, parse_date


MONEY_FIELDS = (
    "buyRaces", "hitCount", "hitRatePercent", "stakeYen", "payoutYen",
    "profitYen", "roiPercent", "averageStakeYen",
)
ADDITIVE_MONEY_FIELDS = ("buyRaces", "hitCount", "stakeYen", "payoutYen", "profitYen")
ADDITIVE_AUDIT_FIELDS = ("liveBuyCount", "auditedBuyCount", "incompleteCount")
COUNT_FIELDS = ("predictionCount", "exportedPredictionCount", "excludedFuturePredictionCount")


def source_version(row):
    """Only the row's own nonblank string establishes version provenance."""
    value = row.get("sourceAppVersion")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("sourceAppVersion must be a string or null")
    return value if value.strip() else None


def summarize(rows, evaluation, anchor):
    # Race date is already a JST calendar date. Never derive it from createdAt.
    dates = [parse_date(row.get("date")) for row in rows]
    represented = [day for day in dates if day <= anchor]
    performance = evaluation["performance"]["all"]
    return {
        "predictionCount": len(represented),
        "exportedPredictionCount": len(rows),
        "excludedFuturePredictionCount": len(dates) - len(represented),
        "firstRaceDateJst": min(represented).isoformat() if represented else None,
        "lastRaceDateJst": max(represented).isoformat() if represented else None,
        "audit": performance["audit"],
        "auditedMoney": {field: performance["money"][field] for field in MONEY_FIELDS},
    }


def reconcile(overall, buckets):
    """Check additive totals and date extrema; percentages are never added."""
    totals = {field: sum(bucket[field] for bucket in buckets) for field in COUNT_FIELDS}
    totals["audit"] = {
        field: sum(bucket["audit"][field] for bucket in buckets)
        for field in ADDITIVE_AUDIT_FIELDS
    }
    totals["auditedMoney"] = {
        field: sum(bucket["auditedMoney"][field] for bucket in buckets)
        for field in ADDITIVE_MONEY_FIELDS
    }
    failures = Counter()
    for bucket in buckets:
        failures.update(bucket["audit"]["failureCounts"])
    totals["audit"]["failureCounts"] = dict(sorted(failures.items()))
    firsts = [bucket["firstRaceDateJst"] for bucket in buckets if bucket["firstRaceDateJst"]]
    lasts = [bucket["lastRaceDateJst"] for bucket in buckets if bucket["lastRaceDateJst"]]
    totals["firstRaceDateJst"] = min(firsts) if firsts else None
    totals["lastRaceDateJst"] = max(lasts) if lasts else None
    for field in (*COUNT_FIELDS, "firstRaceDateJst", "lastRaceDateJst"):
        if totals[field] != overall[field]:
            raise ValueError(f"Version bucket reconciliation failed: {field}")
    for section, fields in (
        ("audit", (*ADDITIVE_AUDIT_FIELDS, "failureCounts")),
        ("auditedMoney", ADDITIVE_MONEY_FIELDS),
    ):
        for field in fields:
            if totals[section][field] != overall[section][field]:
                raise ValueError(f"Version bucket reconciliation failed: {section}.{field}")
    return {"status": "PASS", "bucketSums": totals,
            "percentagesAreAdditive": False}


def versioned_report(payload, as_of):
    if not isinstance(payload, dict) or "schemaVersion" not in payload:
        raise ValueError("Expected an Android schemaVersion=1 backup envelope")
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    # Evaluate all rows FIRST: cross-version duplicate BUYs and invalid bets must
    # still fail exactly as they do in the frozen evaluator, before partitioning.
    overall_evaluation = evaluate(payload, as_of, protocol)
    anchor = parse_date(as_of)
    rows = payload["predictions"]
    groups = defaultdict(list)
    groups[None] = []  # Always show the legacy bucket, including a zero count.
    for row in rows:
        groups[source_version(row)].append(row)
    overall = summarize(rows, overall_evaluation, anchor)
    versions = [None, *sorted(version for version in groups if version is not None)]
    buckets = []
    for version in versions:
        group = groups[version]
        # Original dictionaries retain sourceAppVersion. The frozen evaluator
        # owns normalization, cohort, audit, and money; none is reimplemented.
        evaluation = evaluate(group, as_of, protocol)
        buckets.append({
            "bucketType": "legacy_unversioned" if version is None else "versioned",
            "sourceAppVersion": version,
            **summarize(group, evaluation, anchor),
        })
    audited = overall["audit"]["auditedBuyCount"]
    target = protocol["diagnostics"]["minimumOverallAuditedBuys"]
    return {
        "reportVersion": "v016-versioned-evidence-1",
        "protocolVersion": overall_evaluation["protocolVersion"],
        "asOfJst": as_of,
        "backupProvenance": {
            "schemaVersion": payload["schemaVersion"],
            "appVersion": payload["appVersion"],
            "exportedAt": payload["exportedAt"],
            "rowVersionInferredFromEnvelope": False,
        },
        "groupingSemantics": {
            "key": "Exact nonblank sourceAppVersion string on each prediction row",
            "legacy": "Absent, null, empty, or whitespace-only sourceAppVersion",
            "versionsMerged": False,
            "versionSort": "Legacy first, then lexical display order; not a version comparison",
            "dateScope": "Prediction date <= asOfJst; future rows counted separately",
            "dateRange": "JST race dates of all included predictions, including SKIP and unsettled",
            "moneyScope": "Frozen settled/evaluationEligible/recommended/value-v1 audited predictions only",
            "actualPurchasesGrouped": False,
        },
        "allRecords": overall,
        "versionBuckets": buckets,
        "reconciliation": reconcile(overall, buckets),
        "formalEvaluation": {
            "auditedBuyTarget": target,
            "auditedBuyCount": audited,
            "remainingAuditedBuys": max(0, target - audited),
            "overallSampleThresholdReached": audited >= target,
            "frozenDiagnosticsStatus": overall_evaluation["diagnostics"]["status"],
            "productionPromotion": overall_evaluation["productionPromotion"],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--as-of", default=datetime.now(JST).date().isoformat(),
                        help="YYYY-MM-DD in Asia/Tokyo; same default as frozen evaluator")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.output.resolve() == args.input.resolve():
        parser.error("--output must not overwrite the input backup")
    report = versioned_report(json.loads(args.input.read_text(encoding="utf-8")), args.as_of)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
