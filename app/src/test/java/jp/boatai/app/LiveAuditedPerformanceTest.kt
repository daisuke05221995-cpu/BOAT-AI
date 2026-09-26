package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LiveAuditedPerformanceTest {
    private fun record(
        id: String = "2026-09-26-01-8",
        recommended: Boolean = true,
        strategyId: String? = "value-v1",
        liveOddsFetchedAt: Long? = 1_797_000_000_000L,
        liveOddsSource: String? = "公式PC版",
        liveOddsCount: Int = 120,
        combinations: List<String> = listOf("1-2-3", "1-3-2"),
        stakes: List<Int> = listOf(600, 400),
        livePickOdds: List<Double> = listOf(12.4, 18.7),
        settled: Boolean = true,
        evaluationEligible: Boolean = true
    ) = PredictionRecord(
        id = id,
        date = "2026-09-26",
        stadiumNumber = 1,
        raceNumber = 8,
        combinations = combinations,
        stakePerPick = 500,
        resultCombination = "1-2-3",
        trifectaPayout = 1240,
        settled = settled,
        createdAt = 10L,
        evaluationEligible = evaluationEligible,
        recommended = recommended,
        stakes = stakes,
        strategyId = strategyId,
        liveOddsFetchedAt = liveOddsFetchedAt,
        liveOddsSource = liveOddsSource,
        liveOddsCount = liveOddsCount,
        livePickOdds = livePickOdds
    )

    @Test
    fun completeSettledValueBuyIsAccepted() {
        assertTrue(LiveAuditedPerformance.isAuditedBuy(record()))
    }

    @Test
    fun incompleteOrNonLiveRecordsAreRejected() {
        assertFalse(LiveAuditedPerformance.isAuditedBuy(record(liveOddsFetchedAt = null)))
        assertFalse(LiveAuditedPerformance.isAuditedBuy(record(liveOddsSource = null)))
        assertFalse(LiveAuditedPerformance.isAuditedBuy(record(liveOddsCount = 119)))
        assertFalse(LiveAuditedPerformance.isAuditedBuy(record(livePickOdds = listOf(12.4))))
        assertFalse(LiveAuditedPerformance.isAuditedBuy(record(stakes = listOf(1000))))
        assertFalse(LiveAuditedPerformance.isAuditedBuy(record(strategyId = "model-a-retro-flex-v2")))
        assertFalse(LiveAuditedPerformance.isAuditedBuy(record(recommended = false)))
        assertFalse(LiveAuditedPerformance.isAuditedBuy(record(settled = false)))
        assertFalse(LiveAuditedPerformance.isAuditedBuy(record(evaluationEligible = false)))
    }

    @Test
    fun coverageCountsOnlySettledEligibleValueBuysAsCandidates() {
        val audited = record(id = "audited")
        val missingAudit = record(id = "missing", liveOddsCount = 0, livePickOdds = emptyList())
        val skip = record(id = "skip", recommended = false, combinations = emptyList(), stakes = emptyList(), livePickOdds = emptyList())
        val retrospective = record(id = "retro", strategyId = "model-a-retro-flex-v2")

        val coverage = LiveAuditedPerformance.coverage(listOf(audited, missingAudit, skip, retrospective))

        assertEquals(2, coverage.liveBuyCount)
        assertEquals(1, coverage.auditedBuyCount)
        assertEquals(1, coverage.missingAuditCount)
        assertEquals(50.0, coverage.coveragePercent, 0.0001)
        assertEquals(listOf(audited), LiveAuditedPerformance.eligible(listOf(audited, missingAudit, skip, retrospective)))
    }
}
