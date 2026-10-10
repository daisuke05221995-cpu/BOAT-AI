package jp.boatai.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PredictionTrackingPolicyTest {
    private fun record(settled: Boolean, strategyId: String = "value-v1") = PredictionRecord(
        id = "2026-10-10-01-1",
        date = "2026-10-10",
        stadiumNumber = 1,
        raceNumber = 1,
        combinations = listOf("1-2-3"),
        stakePerPick = 300,
        resultCombination = if (settled) "1-2-3" else null,
        trifectaPayout = if (settled) 1000 else 0,
        settled = settled,
        createdAt = 1L,
        evaluationEligible = true,
        recommended = true,
        stakes = listOf(300),
        strategyId = strategyId
    )

    @Test
    fun unsettledValueRecordIsReevaluatedNearClose() {
        assertFalse(PredictionTrackingPolicy.shouldSkipEvaluation(record(settled = false)))
    }

    @Test
    fun unsettledLegacyRecordIsAlsoReevaluatedNearClose() {
        assertFalse(
            PredictionTrackingPolicy.shouldSkipEvaluation(
                record(settled = false, strategyId = "legacy-final-v1")
            )
        )
    }

    @Test
    fun settledRecordRemainsImmutable() {
        assertTrue(PredictionTrackingPolicy.shouldSkipEvaluation(record(settled = true)))
    }

    @Test
    fun missingRecordDoesNotBlockEvaluation() {
        assertFalse(PredictionTrackingPolicy.shouldSkipEvaluation(null))
    }
}
