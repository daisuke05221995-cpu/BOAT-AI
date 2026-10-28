"""Synthetic-only regression tests; no private BUY ledger or holdout data."""

from copy import deepcopy
import unittest

from roi_recovery_diagnostic import analyze, production_version, top_payout_sensitivity
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


if __name__ == "__main__":
    unittest.main()
