package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class ProfitAnalyticsTest {
    @Test
    fun comparesAutoSkipWithBaseline() {
        val records = listOf(
            record("a", true, false, 1_000),
            record("b", false, true, 0)
        )
        val result = ProfitAnalytics.build(records, AnalyticsPeriod.ALL, LocalDate.parse("2026-09-22"))
        assertEquals(2, result.baseline.races)
        assertEquals(1, result.adjusted.races)
        assertTrue(result.avoidedLoss > 0)
    }

    private fun record(id: String, hit: Boolean, skipped: Boolean, payout: Int) = PredictionRecord(
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
        autoSkipped = skipped
    )
}
