"""Synthetic-only regression tests; no private BUY ledger or holdout data."""

from copy import deepcopy
import unittest

from roi_recovery_diagnostic import (
    analyze, expected_roi_reason_diagnostic, production_version, structured_roi_diagnostic,
    top_payout_sensitivity,
)
from v016_live_money_eval import evaluate
from v016_live_money_eval_test import backup, bet, fixture


AS_OF = "2026-10-28"


def new_row(day="2026-10-20", race=1, version="0.18.21", **kwargs):
    row = fixture(day=day, race=race, **kwargs)
    row["sourceAppVersion"] = version
    return row


class RoiRecoveryDiagnosticTest(unittest.TestCase):
    def test_empty_private_backup_has_no_roi_claim(self):
        result = analyze(backup(), AS_OF)
        new = result["prospectiveNewPolicy"]
        self.assertEqual(new["auditedBuys"], 0)
        self.assertIsNone(new["money"]["roiPercent"])
        self.assertEqual(new["validationStatus"], "INSUFFICIENT_NEW_PROSPECTIVE_SAMPLE")
        self.assertFalse(result["productionPromotionAllowed"])

    def test_old_date_is_separate_even_if_reexported_by_new_version(self):
        old = new_row(day="2026-10-14", race=1)
        fresh = new_row(day="2026-10-20", race=2)
        result = analyze(backup([old, fresh]), AS_OF)
        self.assertEqual(result["oldDateAudited"]["auditedBuys"], 1)
        self.assertEqual(result["prospectiveNewPolicy"]["auditedBuys"], 1)
        self.assertEqual(result["unattributedPostCutoff"]["auditedBuys"], 0)

    def test_legacy_and_old_version_are_quarantined_not_relabelled(self):
        older = new_row(race=1, version="0.18.14")
        legacy = fixture(day="2026-10-20", race=2)
        valid = new_row(race=3, version="0.18.15")
        payload = backup([older, legacy, valid])
        payload["appVersion"] = "0.18.21"
        result = analyze(payload, AS_OF)
        self.assertEqual(result["prospectiveNewPolicy"]["auditedBuys"], 1)
        self.assertEqual(result["unattributedPostCutoff"]["auditedBuys"], 2)
        self.assertEqual(production_version("0.18.9"), (0, 18, 9))
        self.assertIsNone(production_version("0.18.21-beta"))

    def test_incomplete_and_skip_are_excluded_from_prospective_money(self):
        valid = new_row(race=1)
        incomplete = new_row(race=2)
        incomplete.update(liveOddsCount=119, livePickOdds=[])
        skip = new_row(race=3)
        skip["recommended"] = False
        rows = [valid, incomplete, skip]
        report = analyze(backup(rows), AS_OF)
        new = report["prospectiveNewPolicy"]
        self.assertEqual(new["settledCandidateBuys"], 2)
        self.assertEqual(new["auditedBuys"], 1)
        self.assertEqual(new["incompleteAudits"], 1)
        self.assertEqual(new["auditFailureCounts"], {"ODDS_COUNT": 1, "PICK_ODDS": 1})
        self.assertEqual(new["money"]["stakeYen"], 1000)

    def test_full_frozen_money_reconciles_and_actual_bets_do_not_enter_roi(self):
        rows = [new_row(race=1, payout=250), new_row(race=2, winner="2-3-4")]
        payload = backup(rows, [bet(stake=5000, payout=20000)])
        result = analyze(payload, AS_OF)
        truth = evaluate(payload, AS_OF)["performance"]["all"]["money"]
        actual = result["prospectiveNewPolicy"]["money"]
        self.assertEqual((actual["stakeYen"], actual["payoutYen"]),
                         (truth["stakeYen"], truth["payoutYen"]))
        self.assertTrue(result["allAuditedMoneyMatchesFrozenEvaluator"])

    def test_big_winner_removal_is_descriptive_and_does_not_change_ledger(self):
        rows = [new_row(race=1, payout=1000), new_row(race=2, payout=200),
                new_row(race=3, winner="2-3-4")]
        before = deepcopy(rows)
        result = analyze(backup(rows), AS_OF)["prospectiveNewPolicy"]
        self.assertEqual(rows, before)
        self.assertAlmostEqual(result["money"]["roiPercent"], 400)
        sensitivity = result["payoutConcentration"]
        self.assertEqual(sensitivity["withoutTop1PayoutRaces"]["remainingRaces"], 2)
        self.assertAlmostEqual(sensitivity["withoutTop1PayoutRaces"]["roiPercent"], 100)
        self.assertIsNone(top_payout_sensitivity([])["withoutTop1PayoutRaces"]["roiPercent"])

    def test_duplicate_audited_race_fails_closed(self):
        row = new_row()
        with self.assertRaisesRegex(ValueError, "Duplicate live BUY race"):
            analyze(backup([row, deepcopy(row)]), AS_OF)

    def test_expected_roi_reason_is_stake_weighted_and_text_only(self):
        low = new_row(race=1, stake=1000, payout=200)
        low["recommendationReason"] = "購入推奨（推定期待回収率 130%）"
        high = new_row(race=2, stake=3000, payout=200)
        high["recommendationReason"] = "購入推奨（推定期待回収率 250%）"
        missing = new_row(race=3)
        missing["recommendationReason"] = "購入推奨・率なし"
        result = analyze(backup([low, high, missing]), AS_OF)["prospectiveNewPolicy"]
        diagnostic = result["expectedRoiReasonDiagnostic"]
        self.assertEqual(diagnostic["coveredRaces"], 2)
        self.assertEqual(diagnostic["missingReasonRoiRaces"], 1)
        self.assertEqual(diagnostic["overallWithReason"]["stakeYen"], 4000)
        self.assertEqual(diagnostic["overallWithReason"]["payoutYen"], 8000)
        self.assertEqual(diagnostic["overallWithReason"]["stakeWeightedEstimatedRoiPercent"], 220)
        self.assertEqual(diagnostic["overallWithReason"]["realizedRoiPercent"], 200)
        self.assertEqual([b["races"] for b in diagnostic["bands"]], [0, 1, 0, 0, 1])
        self.assertFalse(result.get("productionPromotionAllowed", False))

    def test_missing_or_malformed_reason_does_not_invent_expected_roi(self):
        rows = [new_row(race=1), new_row(race=2)]
        rows[0]["recommendationReason"] = "推定期待回収率 -500%"
        rows[1]["recommendationReason"] = "推定期待回収率 99999%"
        diagnosis = expected_roi_reason_diagnostic(rows)
        self.assertEqual(diagnosis["coveredRaces"], 0)
        self.assertIsNone(diagnosis["overallWithReason"]["stakeWeightedEstimatedRoiPercent"])

    def test_structured_probability_snapshot_reconciles_expected_and_observed(self):
        hits = new_row(race=1, stake=1000, payout=300)
        hits.update(
            livePickAiProbabilities=[0.2],
            livePickOdds=[5.0],
            liveExpectedRoiPercent=100.0,
            decisionCapturedAt=1790000000000,
        )
        misses = new_row(race=2, stake=2000, payout=300, winner="2-3-4")
        misses.update(
            livePickAiProbabilities=[0.1],
            livePickOdds=[10.0],
            liveExpectedRoiPercent=100.0,
            decisionCapturedAt=1790000000000,
        )
        report = analyze(backup([hits, misses]), AS_OF)["prospectiveNewPolicy"]["structuredRoiDiagnostic"]
        self.assertEqual(report["coveredRaces"], 2)
        self.assertEqual((report["stakeYen"], report["payoutYen"]), (3000, 3000))
        self.assertEqual(report["stakeWeightedEstimatedRoiPercent"], 100)
        self.assertEqual(report["expectedHitCount"], 0.3)
        self.assertEqual(report["actualHitCount"], 1)
        self.assertEqual(report["expectedHitRatePercent"], 15)
        self.assertEqual(report["actualHitRatePercent"], 50)

    def test_structured_snapshot_missing_and_tampered_are_never_used(self):
        missing = new_row(race=1)
        forged = new_row(race=2)
        forged.update(livePickAiProbabilities=[0.2], liveExpectedRoiPercent=900.0,
                      decisionCapturedAt=1790000000000)
        report = structured_roi_diagnostic([missing, forged])
        self.assertEqual(report["coveredRaces"], 0)
        self.assertEqual(report["missingRaces"], 1)
        self.assertEqual(report["invalidRaces"], 1)
        self.assertIsNone(report["realizedRoiPercent"])


if __name__ == "__main__":
    unittest.main()
