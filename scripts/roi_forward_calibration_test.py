"""Synthetic-only forward evidence tests. No user backup or sealed holdout."""

from copy import deepcopy
import unittest

from roi_forward_calibration import analyze
from v016_live_money_eval_test import backup, fixture


AS_OF = "2026-11-20"


def tracked(day="2026-10-29", race=1, stake=1000, payout=200,
            p=0.2, odds=5.0, **kwargs):
    row = fixture(day=day, race=race, stake=stake, payout=payout, **kwargs)
    row.update(
        sourceAppVersion="0.18.22",
        livePickOdds=[odds],
        livePickAiProbabilities=[p],
        liveExpectedRoiPercent=p * odds * 100,
        decisionCapturedAt=row["liveOddsFetchedAt"] + 1000,
    )
    return row


class ForwardSelectedBuyCalibrationTest(unittest.TestCase):
    def test_empty_backup_never_claims_policy_qualification(self):
        report = analyze(backup(), AS_OF)
        self.assertFalse(report["productionPromotionAllowed"])
        self.assertEqual(report["coverage"]["validNumericSnapshots"], 0)
        self.assertIsNone(report["observedCalibration"]["brierScore"])
        self.assertEqual(report["sampleGoal"]["status"], "COLLECT_FORWARD_DATA")
        self.assertEqual(report["sampleGoal"]["remainingBuys"], 360)

    def test_stake_weighted_roi_and_selected_hit_mass(self):
        hit = tracked(race=1, stake=1000, payout=300, p=0.2, odds=5.0)
        miss = tracked(race=2, stake=2000, p=0.1, odds=10.0, winner="2-3-4")
        report = analyze(backup([hit, miss]), AS_OF)
        s = report["observedCalibration"]
        self.assertEqual(s["auditedBuyRaces"], 2)
        self.assertEqual((s["stakeYen"], s["payoutYen"], s["profitYen"]), (3000, 3000, 0))
        self.assertEqual(s["realizedRoiPercent"], 100.0)
        self.assertEqual(s["stakeWeightedExpectedRoiPercent"], 100.0)
        self.assertEqual(s["actualHits"], 1)
        self.assertEqual(s["expectedHits"], 0.3)
        self.assertEqual(s["actualHitRatePercent"], 50.0)
        self.assertEqual(s["expectedHitRatePercent"], 15.0)
        self.assertEqual(s["brierScore"], 0.325)
        self.assertEqual(s["logLoss"], 0.857399)
        self.assertEqual(report["coverage"]["validNumericSnapshots"], 2)

    def test_filters_versions_and_start_day_without_reclassification(self):
        old_day = tracked(day="2026-10-28", race=1)
        old_version = tracked(race=2)
        old_version["sourceAppVersion"] = "0.18.21"
        next_version = tracked(race=3)
        next_version["sourceAppVersion"] = "0.18.23"
        eligible = tracked(race=4)
        report = analyze(backup([old_day, old_version, next_version, eligible]), AS_OF)
        self.assertEqual(report["coverage"]["eligibleBuyDecisions"], 1)
        self.assertEqual(report["coverage"]["validNumericSnapshots"], 1)
        self.assertEqual(report["daily"][0]["label"], "2026-10-29")

    def test_pending_incomplete_invalid_and_missing_are_distinct(self):
        pending = tracked(race=1)
        pending["settled"] = False
        incomplete = tracked(race=2)
        incomplete["liveOddsCount"] = 119
        invalid = tracked(race=3)
        invalid["liveExpectedRoiPercent"] = 999
        missing = tracked(race=4)
        missing.pop("livePickAiProbabilities")
        missing.pop("liveExpectedRoiPercent")
        missing.pop("decisionCapturedAt")
        early = tracked(race=5)
        early["decisionCapturedAt"] = early["liveOddsFetchedAt"] - 1
        report = analyze(backup([pending, incomplete, invalid, missing, early]), AS_OF)
        c = report["coverage"]
        self.assertEqual(c["eligibleBuyDecisions"], 5)
        self.assertEqual(c["pendingUnsettled"], 1)
        self.assertEqual(c["incompleteAudits"], 1)
        self.assertEqual(c["validNumericSnapshots"], 0)
        self.assertEqual(c["invalidNumericSnapshots"], 2)
        self.assertEqual(c["missingNumericSnapshots"], 1)

    def test_duplicate_race_and_sealed_q4_fail_closed(self):
        row = tracked()
        with self.assertRaisesRegex(ValueError, "Duplicate live BUY race"):
            analyze(backup([row, deepcopy(row)]), AS_OF)
        sealed = fixture(day="2025-11-02")
        with self.assertRaisesRegex(ValueError, "Q4 final holdout is sealed"):
            analyze(backup([sealed]), AS_OF)


if __name__ == "__main__":
    unittest.main()
