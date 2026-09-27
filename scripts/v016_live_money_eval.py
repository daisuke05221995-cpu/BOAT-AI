#!/usr/bin/env python3
"""Evaluate exported, settled value-v1 live BUY records without retrospective ROI.

Usage: python scripts/v016_live_money_eval.py BOAT-AI-backup.json
No device export is bundled. The existing Android backup is the primary input.
"""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

PROTOCOL = Path(__file__).resolve().parents[1] / "data/v016_live_money_protocol.json"
JST = ZoneInfo("Asia/Tokyo")
COMBINATION = re.compile(r"^[1-6]{3}$")


def parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"Invalid date: {value!r}")
    return date.fromisoformat(value)


def integer(value, field, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ValueError(f"Invalid {field}: {value!r}")
    return value


def candidate(record):
    return (record.get("settled") is True and record.get("evaluationEligible") is True
            and record.get("recommended") is True and record.get("strategyId") == "value-v1")


def normalize_prediction(record):
    """Mirror absent audit fields in PredictionRecord.fromJson for legacy backups."""
    result = dict(record)
    defaults = {"combinations": [], "stakes": [], "liveOddsFetchedAt": None,
                "liveOddsSource": None, "liveOddsCount": 0, "livePickOdds": [],
                "resultCombination": None, "trifectaPayout": 0}
    for key, value in defaults.items():
        result.setdefault(key, value)
    return result


def audit(record):
    failures = []
    if type(record["liveOddsFetchedAt"]) is not int or record["liveOddsFetchedAt"] <= 0:
        failures.append("FETCH_TIME")
    if not isinstance(record["liveOddsSource"], str) or not record["liveOddsSource"].strip():
        failures.append("SOURCE")
    if type(record["liveOddsCount"]) is not int or record["liveOddsCount"] < 120:
        failures.append("ODDS_COUNT")
    picks = record["combinations"]
    stakes = record["stakes"]
    odds = record["livePickOdds"]
    if not picks:
        failures.append("COMBINATIONS")
    if picks and (len(stakes) != len(picks) or any(type(v) is not int or v < 100 or v % 100 for v in stakes)):
        failures.append("STAKES")
    if picks and (len(odds) != len(picks) or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in odds)):
        failures.append("PICK_ODDS")
    return failures


def validate(record):
    required = json.loads(PROTOCOL.read_text(encoding="utf-8"))["input"]["requiredFields"]
    missing = [key for key in required if key not in record]
    if missing:
        raise ValueError(f"Missing candidate keys: {missing}")
    parse_date(record["date"])
    integer(record["stadiumNumber"], "stadiumNumber", 1)
    if record["stadiumNumber"] > 24:
        raise ValueError("Invalid stadiumNumber")
    integer(record["raceNumber"], "raceNumber", 1)
    if record["raceNumber"] > 12:
        raise ValueError("Invalid raceNumber")
    integer(record["createdAt"], "createdAt", 1)
    if not isinstance(record["id"], str) or not record["id"].strip():
        raise ValueError("Missing record id")
    for key in ("combinations", "stakes", "livePickOdds"):
        if not isinstance(record[key], list):
            raise ValueError(f"Invalid {key}")
    if any(not isinstance(p, str) or not COMBINATION.fullmatch(p) or len(set(p)) != 3 for p in record["combinations"]):
        raise ValueError("Invalid combination")
    if len(set(record["combinations"])) != len(record["combinations"]):
        raise ValueError("Repeated combination in one race")
    result = record["resultCombination"]
    if result is not None and (not isinstance(result, str) or not COMBINATION.fullmatch(result) or len(set(result)) != 3):
        raise ValueError("Invalid resultCombination")
    integer(record["trifectaPayout"], "trifectaPayout", 0)
    if (result is None) != (record["trifectaPayout"] == 0):
        raise ValueError("Result and trifecta payout disagree")
    if "confidence" in record:
        if integer(record["confidence"], "confidence", 0) > 100:
            raise ValueError("Invalid confidence")
    if record.get("firstLane") is not None and integer(record["firstLane"], "firstLane", 1) > 6:
        raise ValueError("Invalid firstLane")
    if "modelProbability" in record:
        probability = record["modelProbability"]
        if type(probability) not in (float, int) or not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("Invalid modelProbability")


def accounted(record):
    stake = sum(record["stakes"])
    winner = record["resultCombination"]
    payout = (record["trifectaPayout"] * record["stakes"][record["combinations"].index(winner)] // 100
              if winner in record["combinations"] else 0)
    return stake, payout


def statistics(records, amounts=accounted):
    ordered = sorted(records, key=lambda r: (r["date"], r["stadiumNumber"], r["raceNumber"]))
    total_stake = total_payout = cumulative = max_drawdown = 0
    peak = 0
    curve = []
    hit_count = 0
    for record in ordered:
        stake, payout = amounts(record)
        total_stake += stake
        total_payout += payout
        hit_count += int(payout > 0)
        cumulative += payout - stake
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
        curve.append({"date": record["date"], "stadiumNumber": record["stadiumNumber"],
                      "raceNumber": record["raceNumber"], "cumulativeProfitYen": cumulative})
    count = len(ordered)
    return {"buyRaces": count, "hitCount": hit_count,
            "hitRatePercent": 100 * hit_count / count if count else None,
            "stakeYen": total_stake, "payoutYen": total_payout,
            "profitYen": total_payout - total_stake,
            "roiPercent": 100 * total_payout / total_stake if total_stake else None,
            "averageStakeYen": total_stake / count if count else None,
            "maxDrawdownYen": max_drawdown, "cumulativeProfitCurve": curve}


def band(value, edges):
    if value is None:
        return "UNKNOWN"
    for edge in edges:
        if value < edge:
            return f"<{edge}"
    return f">={edges[-1]}"


def diagnostics(records, protocol):
    minimum = protocol["diagnostics"]
    if len(records) < minimum["minimumOverallAuditedBuys"]:
        return {"status": "INSUFFICIENT_OVERALL_SAMPLE", "slices": []}
    groups = defaultdict(list)
    for record in records:
        stake, _ = accounted(record)
        selected_odds = record["livePickOdds"]
        odds_band = band(min(selected_odds), [5, 10, 20, 50])
        probability = record.get("modelProbability")
        confidence = record.get("confidence")
        prob_band = (band(probability, [0.1, 0.2, 0.4]) if probability is not None
                     else f"confidence:{band(confidence, [40, 60, 80])}")
        dt = datetime.fromtimestamp(record["createdAt"] / 1000, JST)
        dims = {"venue": str(record["stadiumNumber"]), "selectedOddsBand": odds_band,
                "selectedPointCount": str(len(record["combinations"])), "stakeBand": band(stake, [1000, 2000, 3000]),
                "modelProbabilityBand": prob_band,
                "firstLanePredicted": str(record.get("firstLane", "UNKNOWN")),
                "weekday": str(parse_date(record["date"]).weekday()), "hourJst": str(dt.hour)}
        for dimension, label in dims.items():
            groups[(dimension, label)].append(record)
    slices = []
    for (dimension, label), rows in sorted(groups.items()):
        days = len({r["date"] for r in rows})
        hits = sum(accounted(r)[1] > 0 for r in rows)
        if len(rows) < minimum["minimumSliceBuys"] or days < minimum["minimumSliceActiveDays"] or hits < minimum["minimumSliceHits"]:
            continue
        stats = statistics(rows)
        stats.pop("cumulativeProfitCurve")
        slices.append({"dimension": dimension, "value": label, "activeDays": days, **stats})
    return {"status": "DESCRIPTIVE_ONLY_NO_PROMOTION", "slices": slices}


def validate_bet(row):
    for key in ("id", "date", "stadiumNumber", "raceNumber", "combination", "stake",
                "payout", "settled", "createdAt"):
        if key not in row:
            raise ValueError(f"Missing actual purchase key: {key}")
    parse_date(row["date"])
    integer(row["stadiumNumber"], "bet stadiumNumber", 1)
    integer(row["raceNumber"], "bet raceNumber", 1)
    if row["stadiumNumber"] > 24 or row["raceNumber"] > 12:
        raise ValueError("Invalid actual purchase venue/race")
    if not isinstance(row["combination"], str) or not COMBINATION.fullmatch(row["combination"]) or len(set(row["combination"])) != 3:
        raise ValueError("Invalid actual purchase combination")
    integer(row["stake"], "bet stake", 100)
    integer(row["payout"], "bet payout", 0)
    integer(row["createdAt"], "bet createdAt", 1)
    if type(row["settled"]) is not bool:
        raise ValueError("Invalid actual purchase settled flag")
    if not isinstance(row["id"], str) or not row["id"].strip():
        raise ValueError("Missing actual purchase id")


def actual_purchase(bets, anchor, periods):
    seen = set()
    settled = defaultdict(list)
    pending = defaultdict(int)
    for row in bets:
        validate_bet(row)
        if parse_date(row["date"]) > anchor:
            continue
        key = row["date"], row["stadiumNumber"], row["raceNumber"]
        ticket = (*key, row["combination"])
        if ticket in seen:
            raise ValueError(f"Duplicate actual purchase ticket: {ticket}")
        seen.add(ticket)
        if row["settled"]:
            settled[key].append(row)
        else:
            pending[key] += row["stake"]
    races = [{"date": key[0], "stadiumNumber": key[1], "raceNumber": key[2],
              "stake": sum(r["stake"] for r in tickets),
              "payout": sum(r["payout"] for r in tickets)} for key, tickets in settled.items()]
    result = {}
    for name, includes in periods.items():
        selected = [r for r in races if includes(parse_date(r["date"]))]
        result[name] = {"money": statistics(selected, lambda r: (r["stake"], r["payout"])),
                        "pendingStakeYen": sum(stake for key, stake in pending.items() if includes(parse_date(key[0])))}
    return result


def evaluate(payload, as_of, protocol=None):
    protocol = protocol or json.loads(PROTOCOL.read_text(encoding="utf-8"))
    is_backup = isinstance(payload, dict) and "schemaVersion" in payload
    if is_backup:
        if type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1:
            raise ValueError("Unsupported backup schemaVersion")
        if not isinstance(payload.get("appVersion"), str) or not isinstance(payload.get("exportedAt"), str):
            raise ValueError("Backup missing appVersion/exportedAt")
        bets = payload.get("bets")
        predictions = payload.get("predictions")
        if not isinstance(bets, list) or any(not isinstance(r, dict) for r in bets):
            raise ValueError("Invalid backup bets array")
    else:
        bets = None
        predictions = payload.get("records") if isinstance(payload, dict) else payload
    if not isinstance(predictions, list) or any(not isinstance(row, dict) for row in predictions):
        raise ValueError("Expected backup predictions or array of prediction records")
    anchor = parse_date(as_of)
    candidates = []
    seen = set()
    for original in predictions:
        if not candidate(original):
            continue
        row = normalize_prediction(original)
        validate(row)
        if parse_date(row["date"]) > anchor:
            continue
        key = row["date"], row["stadiumNumber"], row["raceNumber"]
        if key in seen:
            raise ValueError(f"Duplicate live BUY race: {key}")
        seen.add(key)
        candidates.append(row)
    audited = []
    failures = Counter()
    for row in candidates:
        reasons = audit(row)
        if reasons:
            failures.update(reasons)
        else:
            audited.append(row)
    periods = {
        "today": lambda d: d == anchor,
        "7d": lambda d: d >= anchor - timedelta(days=6),
        "30d": lambda d: d >= anchor - timedelta(days=29),
        "month": lambda d: (d.year, d.month) == (anchor.year, anchor.month),
        "year": lambda d: d.year == anchor.year,
        "all": lambda d: True,
    }
    result = {}
    for name, includes in periods.items():
        cohort = [r for r in candidates if includes(parse_date(r["date"]))]
        selected = [r for r in audited if includes(parse_date(r["date"]))]
        result[name] = {"audit": {"liveBuyCount": len(cohort), "auditedBuyCount": len(selected),
                                    "incompleteCount": len(cohort) - len(selected),
                                    "completenessPercent": 100 * len(selected) / len(cohort) if cohort else None,
                                    "failureCounts": dict(sorted(Counter(reason for r in cohort for reason in audit(r)).items()))},
                        "money": statistics(selected)}
    return {"protocolVersion": protocol["protocolVersion"], "asOfJst": as_of,
            "dataStatus": "BACKUP_EVALUATION" if is_backup else "PREDICTION_ONLY_EVALUATION" if predictions else "NO_LIVE_EXPORT",
            "appVersion": payload.get("appVersion") if is_backup else None,
            "performance": result, "diagnostics": diagnostics(audited, protocol),
            "actualPurchasePerformance": actual_purchase(bets, anchor, periods) if is_backup else None,
            "productionPromotion": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--as-of", default=datetime.now(JST).date().isoformat(), help="YYYY-MM-DD in Asia/Tokyo (default: today JST)")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(json.loads(args.input.read_text(encoding="utf-8")), args.as_of)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
