"""Synthetic version-provenance and frozen-evaluator parity tests only."""

from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from v016_live_money_eval import evaluate
from v016_live_money_eval_test import backup, bet, fixture, GOLDEN_BACKUP
from v016_versioned_evidence_report import versioned_report


AS_OF = "2026-10-11"
HELPER = Path(__file__).with_name("v016_versioned_evidence_report.py")


def versioned(row, version):
    row["sourceAppVersion"] = version
    return row


def buckets_by_version(report):
    return {bucket["sourceAppVersion"]: bucket for bucket in report["versionBuckets"]}


class VersionedEvidenceTests(unittest.TestCase):
    def assert_frozen_parity(self, report, payload, as_of=AS_OF):
        frozen = evaluate(payload, as_of)
        expected = frozen["performance"]["all"]
        self.assertEqual(report["allRecords"]["audit"], expected["audit"])
        for field, value in report["allRecords"]["auditedMoney"].items():
            self.assertEqual(value, expected["money"][field])
        self.assertEqual(report["formalEvaluation"]["frozenDiagnosticsStatus"],
                         frozen["diagnostics"]["status"])
        self.assertEqual(report["formalEvaluation"]["productionPromotion"],
                         frozen["productionPromotion"])

    def test_legacy_missing_null_and_blank_ignore_envelope_version(self):
        rows = [fixture(race=1), versioned(fixture(race=2), None),
                versioned(fixture(race=3), ""), versioned(fixture(race=4), " \t ")]
        payload = backup(rows)
        payload["appVersion"] = "0.18.8"
        report = versioned_report(payload, AS_OF)
        buckets = buckets_by_version(report)
        self.assertEqual(set(buckets), {None})
        self.assertEqual(buckets[None]["bucketType"], "legacy_unversioned")
        self.assertEqual(buckets[None]["predictionCount"], 4)
        self.assertFalse(report["backupProvenance"]["rowVersionInferredFromEnvelope"])
        self.assert_frozen_parity(report, payload)

    def test_exact_version_strings_survive_and_input_is_not_mutated(self):
        versions = ["0.18.7", "0.18.8", "0.18.10", "0.18.9", " 0.18.8 "]
        payload = backup([versioned(fixture(race=index + 1), value)
                          for index, value in enumerate(versions)])
        before = deepcopy(payload)
        report = versioned_report(payload, AS_OF)
        buckets = buckets_by_version(report)
        self.assertEqual(set(buckets), {None, *versions})
        self.assertEqual(buckets[None]["predictionCount"], 0)
        self.assertEqual([b["sourceAppVersion"] for b in report["versionBuckets"]],
                         [None, *sorted(versions)])
        self.assertEqual(payload, before)
        for row in payload["predictions"]:
            self.assertEqual(buckets[row["sourceAppVersion"]]["predictionCount"], 1)

    def test_version_label_cannot_collide_with_legacy_bucket(self):
        payload = backup([fixture(race=1), versioned(fixture(race=2), "legacy_unversioned")])
        buckets = buckets_by_version(versioned_report(payload, AS_OF))
        self.assertEqual(buckets[None]["bucketType"], "legacy_unversioned")
        self.assertEqual(buckets["legacy_unversioned"]["bucketType"], "versioned")

    def test_mixed_buckets_reconcile_and_only_audited_money_is_included(self):
        multi = versioned(fixture(race=3, winner="2-3-4", payout=550), "0.18.8")
        multi.update(combinations=["1-2-3", "2-3-4"], stakes=[300, 700], livePickOdds=[3.0, 5.5])
        incomplete = versioned(fixture(race=4), "0.18.8")
        incomplete.update(liveOddsCount=119, livePickOdds=[])
        skip = versioned(fixture(race=5), "0.18.8")
        skip["recommended"] = False
        pending = versioned(fixture(race=6), "0.18.8")
        pending["settled"] = False
        old_strategy = fixture(race=7)
        old_strategy["strategyId"] = "legacy-final-v1"
        payload = backup([fixture(race=1),
                          versioned(fixture(race=2, winner="2-3-4"), "0.18.7"),
                          multi, incomplete, skip, pending, old_strategy])
        report = versioned_report(payload, AS_OF)
        total = report["allRecords"]
        self.assertEqual(total["predictionCount"], 7)
        self.assertEqual(total["audit"], {
            "liveBuyCount": 4, "auditedBuyCount": 3, "incompleteCount": 1,
            "completenessPercent": 75.0,
            "failureCounts": {"ODDS_COUNT": 1, "PICK_ODDS": 1},
        })
        money = total["auditedMoney"]
        self.assertEqual((money["stakeYen"], money["payoutYen"], money["profitYen"],
                          money["roiPercent"]), (3000, 5850, 2850, 195.0))
        self.assertEqual(report["reconciliation"]["status"], "PASS")
        for section in ("audit", "auditedMoney"):
            for field, value in report["reconciliation"]["bucketSums"][section].items():
                self.assertEqual(value, total[section][field])
        self.assert_frozen_parity(report, payload)

    def test_version_assignment_does_not_change_any_frozen_audit_rule(self):
        mutations = [{"liveOddsFetchedAt": None}, {"liveOddsSource": " "},
                     {"liveOddsCount": 119}, {"liveOddsCount": 121},
                     {"livePickOdds": []}, {"stakes": [150]},
                     {"combinations": []}, {"recommended": False},
                     {"settled": False}, {"evaluationEligible": False},
                     {"strategyId": "model-a-retro-flex-v2"},
                     {"trifectaPayout": 0}, {"resultCombination": None, "trifectaPayout": 0}]
        for changes in mutations:
            with self.subTest(changes=changes):
                row = fixture()
                row.update(changes)
                legacy_payload = backup([row])
                labelled_payload = backup([versioned(deepcopy(row), "0.18.8")])
                legacy = versioned_report(legacy_payload, AS_OF)
                labelled = versioned_report(labelled_payload, AS_OF)
                self.assertEqual(legacy["allRecords"], labelled["allRecords"])
                self.assert_frozen_parity(labelled, labelled_payload)
                bucket = buckets_by_version(labelled)["0.18.8"]
                self.assertEqual(bucket["audit"], labelled["allRecords"]["audit"])
                self.assertEqual(bucket["auditedMoney"], labelled["allRecords"]["auditedMoney"])

    def test_recommended_default_and_missing_audit_fields_keep_frozen_behavior(self):
        row = versioned(fixture(), "0.18.8")
        row.pop("recommended")
        for field in ("liveOddsFetchedAt", "liveOddsSource", "liveOddsCount", "livePickOdds"):
            row.pop(field)
        payload = backup([row])
        report = versioned_report(payload, AS_OF)
        self.assertEqual(report["allRecords"]["audit"]["liveBuyCount"], 1)
        self.assertEqual(report["allRecords"]["audit"]["auditedBuyCount"], 0)
        self.assertEqual(report["allRecords"]["audit"]["failureCounts"],
                         {"FETCH_TIME": 1, "SOURCE": 1, "ODDS_COUNT": 1, "PICK_ODDS": 1})
        self.assert_frozen_parity(report, payload)

    def test_global_duplicate_buy_rejected_even_across_versions(self):
        payload = backup([fixture(), versioned(fixture(), "0.18.8")])
        for evaluator in (evaluate, versioned_report):
            with self.assertRaisesRegex(ValueError, "Duplicate live BUY race"):
                evaluator(payload, AS_OF)

    def test_empty_or_no_buy_bucket_has_null_rates_and_no_profitability_claim(self):
        skip = versioned(fixture(), "0.18.8")
        skip["recommended"] = False
        for payload in (backup(), backup([skip])):
            with self.subTest(predictions=len(payload["predictions"])):
                report = versioned_report(payload, AS_OF)
                for bucket in report["versionBuckets"]:
                    self.assertIsNone(bucket["audit"]["completenessPercent"])
                    self.assertIsNone(bucket["auditedMoney"]["roiPercent"])
                self.assertFalse(report["formalEvaluation"]["overallSampleThresholdReached"])
                self.assertFalse(report["formalEvaluation"]["productionPromotion"])
                self.assertEqual(report["formalEvaluation"]["remainingAuditedBuys"], 360)

    def test_race_date_scope_excludes_future_and_does_not_use_created_at(self):
        earlier = fixture(day="2026-10-09", race=1)
        earlier["createdAt"] = 1  # Deliberately unrelated to the race's JST date.
        current = versioned(fixture(day=AS_OF, race=2), "0.18.8")
        future = versioned(fixture(day="2026-10-12", race=3), "0.18.8")
        skip = versioned(fixture(day="2026-10-08", race=4), "0.18.8")
        skip["recommended"] = False
        payload = backup([future, current, earlier, skip])
        report = versioned_report(payload, AS_OF)
        total = report["allRecords"]
        self.assertEqual((total["predictionCount"], total["exportedPredictionCount"],
                          total["excludedFuturePredictionCount"]), (3, 4, 1))
        self.assertEqual((total["firstRaceDateJst"], total["lastRaceDateJst"]),
                         ("2026-10-08", AS_OF))
        self.assertEqual(total["audit"]["auditedBuyCount"], 2)
        self.assertEqual(buckets_by_version(report)["0.18.8"]["firstRaceDateJst"], "2026-10-08")
        self.assert_frozen_parity(report, payload)

    def test_invalid_version_is_not_coerced_or_guessed(self):
        for version in (188, True, {}, []):
            with self.subTest(version=version):
                with self.assertRaisesRegex(ValueError, "sourceAppVersion"):
                    versioned_report(backup([versioned(fixture(), version)]), AS_OF)

    def test_reporting_requires_valid_race_date_even_for_nonbuy_rows(self):
        row = fixture()
        row.update(recommended=False, date="invalid")
        with self.assertRaisesRegex(ValueError, "Invalid date"):
            versioned_report(backup([row]), AS_OF)

    def test_360_gate_is_global_and_not_reset_for_each_version(self):
        start = date(2026, 9, 1)
        rows = [fixture(day=str(start + timedelta(days=index // 12)), race=index % 12 + 1)
                for index in range(360)]
        for row in rows[180:]:
            row["sourceAppVersion"] = "0.18.8"
        for count, reached in ((359, False), (360, True)):
            with self.subTest(count=count):
                payload = backup(rows[:count])
                report = versioned_report(payload, AS_OF)
                gate = report["formalEvaluation"]
                self.assertEqual(gate["auditedBuyTarget"], 360)
                self.assertEqual(gate["auditedBuyCount"], count)
                self.assertEqual(gate["remainingAuditedBuys"], 360 - count)
                self.assertEqual(gate["overallSampleThresholdReached"], reached)
                self.assertFalse(gate["productionPromotion"])
                self.assertTrue(all(bucket["audit"]["auditedBuyCount"] < 360
                                    for bucket in report["versionBuckets"]))
                self.assert_frozen_parity(report, payload)

    def test_actual_purchases_are_not_attributed_to_prediction_versions(self):
        rows = [versioned(fixture(), "0.18.8")]
        payload = backup(rows, [bet(stake=5000, payout=20000)])
        report = versioned_report(payload, AS_OF)
        self.assertEqual(report["allRecords"], versioned_report(backup(rows), AS_OF)["allRecords"])
        self.assertFalse(report["groupingSemantics"]["actualPurchasesGrouped"])
        self.assertEqual(report["allRecords"]["auditedMoney"]["stakeYen"], 1000)
        invalid = backup(rows, [bet(), bet()])
        with self.assertRaisesRegex(ValueError, "Duplicate actual purchase ticket"):
            versioned_report(invalid, AS_OF)

    def test_golden_android_synthetic_fixture_stays_legacy_and_reconciles(self):
        payload = json.loads(GOLDEN_BACKUP.read_text(encoding="utf-8"))
        report = versioned_report(payload, "2026-09-27")
        self.assertEqual(set(buckets_by_version(report)), {None})
        self.assertEqual(report["allRecords"]["audit"]["completenessPercent"], 50.0)
        self.assertEqual(report["allRecords"]["auditedMoney"]["payoutYen"], 5950)
        self.assert_frozen_parity(report, payload, "2026-09-27")

    def test_backup_envelope_contract_is_not_weakened(self):
        payload = backup([fixture()])
        payload.pop("learning")
        with self.assertRaisesRegex(ValueError, "learning"):
            versioned_report(payload, AS_OF)
        with self.assertRaisesRegex(ValueError, "backup envelope"):
            versioned_report([fixture()], AS_OF)

    def test_cli_writes_synthetic_report_and_preserves_input(self):
        payload = backup([fixture(race=1), versioned(fixture(race=2), "0.18.8")])
        with tempfile.TemporaryDirectory() as folder:
            input_path = Path(folder) / "synthetic-backup.json"
            output_path = Path(folder) / "synthetic-report.json"
            input_bytes = json.dumps(payload).encode("utf-8")
            input_path.write_bytes(input_bytes)
            command = [sys.executable, str(HELPER), str(input_path), "--as-of", AS_OF]
            completed = subprocess.run([*command, "--output", str(output_path)],
                                       check=True, capture_output=True, text=True)
            self.assertEqual(completed.stdout, "")
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")),
                             versioned_report(payload, AS_OF))
            self.assertEqual(input_path.read_bytes(), input_bytes)
            rejected = subprocess.run([*command, "--output", str(input_path)],
                                      capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 2)
            self.assertEqual(input_path.read_bytes(), input_bytes)


if __name__ == "__main__":
    unittest.main()
