package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class ProfitAnalyticsTest {
    @Test
    fun comparesRecommendedOnlyWithAllPredictions() {
        val records = listOf(
            record("a", hit = true, recommended = true, payout = 1_000),
            record("b", hit = false, recommended = false, payout = 0)
        )
        val result = ProfitAnalytics.build(records, AnalyticsPeriod.ALL, LocalDate.parse("2026-09-22"))

        assertEquals(2, result.baseline.races)
        assertEquals(1, result.adjusted.races)
        assertEquals(1, result.adjusted.hits)
        assertEquals(1, result.returnFocused.races)
        assertTrue(result.avoidedLoss > 0)
    }

    private fun record(id: String, hit: Boolean, recommended: Boolean, payout: Int) = PredictionRecord(
        id = id,
        date = "2026-09-22",
        stadiumNumber = 1,
        raceNumber = 1,
        combinations = listOf("1-2-3"),
        stakePerPick = 300,
        resultCombination = if (hit) "1-2-3" else "2-1-3",
        trifectaPayout = payout,
        settled = true,
        createdAt = 1,
        evaluationEligible = true,
        autoSkipped = !recommended,
        recommended = recommended,
        recommendationReason = if (recommended) "購入基準を満たす" else "見送り基準"
    )
}
