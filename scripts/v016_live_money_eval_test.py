"""Synthetic and golden contract fixtures only; no production profitability assertion."""
from datetime import date, timedelta
import json
from pathlib import Path
import unittest

from v016_live_money_eval import evaluate

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_BACKUP = ROOT / "data/v016_live_money_golden_backup.json"


def fixture(day="2026-09-27", race=1, winner="1-2-3", stake=1000, payout=200):
    return {"id": f"{day}-01-{race}", "date": day, "stadiumNumber": 1,
            "raceNumber": race, "settled": True, "evaluationEligible": True,
            "recommended": True, "strategyId": "value-v1", "combinations": ["1-2-3"],
            "stakes": [stake], "liveOddsFetchedAt": 1790460000000,
            "liveOddsSource": "synthetic-official", "liveOddsCount": 120,
            "livePickOdds": [2.0], "resultCombination": winner,
            "trifectaPayout": payout, "createdAt": 1790460000000,
            "firstLane": 1, "confidence": 75}


def bet(race=1, combination="1-2-3", stake=100, payout=0, settled=True):
    return {"id": f"bet-{race}-{combination}", "date": "2026-09-27", "stadiumNumber": 1,
            "raceNumber": race, "combination": combination, "stake": stake, "payout": payout,
            "settled": settled, "createdAt": 1790460000000}


def backup(predictions=None, bets=None):
    return {"schemaVersion": 1, "appVersion": "0.16.7", "exportedAt": "2026-09-27T01:00:00Z",
            "bets": bets if bets is not None else [],
            "predictions": predictions if predictions is not None else [], "learning": {},
            "historicalBaselineMigratedThrough": ""}


class MoneyEvalTests(unittest.TestCase):
    def test_empty_export_has_no_profitability_claim(self):
        result = evaluate([], "2026-09-27")
        self.assertEqual(result["dataStatus"], "NO_LIVE_EXPORT")
        self.assertIsNone(result["performance"]["all"]["money"]["roiPercent"])
        self.assertFalse(result["productionPromotion"])

    def test_money_curve_drawdown_and_race_accounting(self):
        rows = [fixture(race=1, winner="1-2-3", stake=1000, payout=200),
                fixture(race=2, winner="2-3-4", stake=1000, payout=100),
                fixture(race=3, winner="3-4-5", stake=1000, payout=100)]
        result = evaluate(rows, "2026-09-27")["performance"]["all"]["money"]
        self.assertEqual((result["stakeYen"], result["payoutYen"], result["profitYen"]), (3000, 2000, -1000))
        self.assertEqual(result["hitCount"], 1)
        self.assertAlmostEqual(result["roiPercent"], 2000 / 30)
        self.assertEqual([p["cumulativeProfitYen"] for p in result["cumulativeProfitCurve"]], [1000, 0, -1000])
        self.assertEqual(result["maxDrawdownYen"], 2000)

    def test_multiple_combinations_use_winning_ticket_stake(self):
        row = fixture(winner="2-3-4", payout=550)
        row["combinations"] = ["1-2-3", "2-3-4"]
        row["stakes"] = [300, 700]
        row["livePickOdds"] = [3.0, 5.5]
        money = evaluate([row], "2026-09-27")["performance"]["all"]["money"]
        self.assertEqual((money["stakeYen"], money["payoutYen"], money["profitYen"]), (1000, 3850, 2850))

    def test_period_boundaries_are_inclusive_and_exclude_future(self):
        anchor = date(2026, 9, 27)
        offsets = [0, 6, 7, 29, 30, 270]
        rows = [fixture(day=str(anchor - timedelta(days=n)), race=1) for n in offsets]
        rows.append(fixture(day="2026-09-28", race=2))
        perf = evaluate(rows, str(anchor))["performance"]
        self.assertEqual([perf[p]["money"]["buyRaces"] for p in ("today", "7d", "30d", "month", "year", "all")],
                         [1, 2, 4, 3, 5, 6])

    def test_incomplete_audit_counts_but_excludes_money(self):
        incomplete = fixture(race=2)
        incomplete["liveOddsCount"] = 119
        incomplete["livePickOdds"] = []
        result = evaluate([fixture(), incomplete], "2026-09-27")["performance"]["all"]
        self.assertEqual(result["audit"]["liveBuyCount"], 2)
        self.assertEqual(result["audit"]["auditedBuyCount"], 1)
        self.assertEqual(result["audit"]["failureCounts"], {"ODDS_COUNT": 1, "PICK_ODDS": 1})
        self.assertEqual(result["money"]["stakeYen"], 1000)

    def test_legacy_missing_audit_fields_remain_in_denominator(self):
        missing = fixture()
        for key in ("liveOddsFetchedAt", "liveOddsSource", "liveOddsCount", "livePickOdds", "stakes"):
            missing.pop(key)
        output = evaluate(backup([missing]), "2026-09-27")["performance"]["all"]
        self.assertEqual(output["audit"]["liveBuyCount"], 1)
        self.assertEqual(output["audit"]["auditedBuyCount"], 0)
        self.assertEqual(set(output["audit"]["failureCounts"]),
                         {"FETCH_TIME", "SOURCE", "ODDS_COUNT", "STAKES", "PICK_ODDS"})

    def test_android_legacy_recommended_default_is_applied_before_cohort_filter(self):
        legacy_buy = fixture()
        legacy_buy.pop("recommended")
        legacy_buy["confidence"] = 75
        result = evaluate(backup([legacy_buy]), "2026-09-27")["performance"]["all"]
        self.assertEqual(result["audit"]["liveBuyCount"], 1)
        self.assertEqual(result["audit"]["auditedBuyCount"], 1)

        legacy_skip = fixture(race=2)
        legacy_skip.pop("recommended")
        legacy_skip["confidence"] = 69
        result = evaluate(backup([legacy_skip]), "2026-09-27")["performance"]["all"]
        self.assertEqual(result["audit"]["liveBuyCount"], 0)

    def test_android_allows_known_result_with_zero_payout(self):
        row = fixture(payout=0)
        result = evaluate(backup([row]), "2026-09-27")["performance"]["all"]["money"]
        self.assertEqual((result["buyRaces"], result["stakeYen"], result["payoutYen"], result["profitYen"]),
                         (1, 1000, 0, -1000))

    def test_legacy_and_retro_are_never_counted(self):
        retro = fixture(race=2)
        retro["strategyId"] = "model-a-retro-flex-v2"
        skip = fixture(race=3)
        skip["recommended"] = False
        actual = fixture(race=4)
        actual["evaluationEligible"] = False
        self.assertEqual(evaluate([fixture(), retro, skip, actual], "2026-09-27")["performance"]["all"]["audit"]["liveBuyCount"], 1)

    def test_reject_duplicate_race_even_different_ids(self):
        duplicate = fixture()
        duplicate["id"] = "another snapshot"
        with self.assertRaisesRegex(ValueError, "Duplicate live BUY race"):
            evaluate([fixture(), duplicate], "2026-09-27")

    def test_reject_malformed_candidate_and_positive_payout_without_result(self):
        bad = fixture()
        bad.pop("date")
        with self.assertRaisesRegex(ValueError, "Missing candidate"):
            evaluate([bad], "2026-09-27")
        bad = fixture(winner=None, payout=100)
        with self.assertRaisesRegex(ValueError, "disagree"):
            evaluate([bad], "2026-09-27")

    def test_android_export_field_names_are_exact_no_aliases(self):
        bad = fixture()
        bad["venueNumber"] = bad.pop("stadiumNumber")
        with self.assertRaisesRegex(ValueError, "Missing candidate"):
            evaluate([bad], "2026-09-27")
        bad_bet = bet()
        bad_bet["actualPayout"] = bad_bet.pop("payout")
        with self.assertRaisesRegex(ValueError, "Missing actual purchase key"):
            evaluate(backup([], [bad_bet]), "2026-09-27")

    def test_diagnostics_suppressed_for_small_sample(self):
        result = evaluate([fixture()], "2026-09-27")
        self.assertEqual(result["diagnostics"], {"status": "INSUFFICIENT_OVERALL_SAMPLE", "slices": []})

    def test_single_big_hit_cannot_publish_weak_slice(self):
        rows = []
        for index in range(360):
            row = fixture(day=str(date(2026, 1, 1) + timedelta(days=index // 12)), race=index % 12 + 1,
                          winner="1-2-3" if index == 0 else "2-3-4", payout=100000 if index == 0 else 100)
            row["stadiumNumber"] = index % 3 + 1
            rows.append(row)
        result = evaluate(rows, "2026-09-27")
        self.assertEqual(result["diagnostics"]["status"], "DESCRIPTIVE_ONLY_NO_PROMOTION")
        self.assertEqual(result["diagnostics"]["slices"], [])

    def test_android_backup_separates_actual_and_live_and_groups_tickets(self):
        data = backup([fixture(payout=200)],
                      [bet(combination="1-2-3", stake=100, payout=200),
                       bet(combination="2-3-4", stake=200, payout=0),
                       bet(race=2, stake=500, settled=False)])
        output = evaluate(data, "2026-09-27")
        self.assertEqual(output["dataStatus"], "BACKUP_EVALUATION")
        self.assertEqual(output["performance"]["all"]["money"]["stakeYen"], 1000)
        actual = output["actualPurchasePerformance"]["all"]
        self.assertEqual((actual["money"]["buyRaces"], actual["money"]["stakeYen"],
                          actual["money"]["payoutYen"], actual["pendingStakeYen"]), (1, 300, 200, 500))

    def test_backup_schema_and_actual_ticket_duplicates_rejected(self):
        data = backup([], [bet(), bet()])
        with self.assertRaisesRegex(ValueError, "Duplicate actual purchase ticket"):
            evaluate(data, "2026-09-27")
        data["schemaVersion"] = 2
        with self.assertRaisesRegex(ValueError, "schemaVersion"):
            evaluate(data, "2026-09-27")

    def test_backup_envelope_requires_android_learning_object(self):
        data = backup()
        data.pop("learning")
        with self.assertRaisesRegex(ValueError, "learning"):
            evaluate(data, "2026-09-27")

    def test_golden_android_backup_contract_and_live_audit_parity(self):
        data = json.loads(GOLDEN_BACKUP.read_text(encoding="utf-8"))
        output = evaluate(data, "2026-09-27")
        live = output["performance"]["all"]
        self.assertEqual(live["audit"], {
            "liveBuyCount": 2,
            "auditedBuyCount": 1,
            "incompleteCount": 1,
            "completenessPercent": 50.0,
            "failureCounts": {"ODDS_COUNT": 1, "PICK_ODDS": 1},
        })
        self.assertEqual((live["money"]["buyRaces"], live["money"]["hitCount"],
                          live["money"]["stakeYen"], live["money"]["payoutYen"],
                          live["money"]["profitYen"], live["money"]["roiPercent"]),
                         (1, 1, 1000, 5950, 4950, 595.0))
        actual = output["actualPurchasePerformance"]["all"]
        self.assertEqual((actual["money"]["buyRaces"], actual["money"]["hitCount"],
                          actual["money"]["stakeYen"], actual["money"]["payoutYen"],
                          actual["money"]["profitYen"], actual["pendingStakeYen"]),
                         (1, 1, 1000, 5950, 4950, 500))


if __name__ == "__main__":
    unittest.main()
