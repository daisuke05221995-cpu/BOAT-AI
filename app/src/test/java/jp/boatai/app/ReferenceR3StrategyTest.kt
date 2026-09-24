package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReferenceR3StrategyTest {
    @Test
    fun exposesFrozenReferencePolicyAndAllCombinations() {
        assertEquals(120, ReferenceR3Strategy.allCombinations().distinct().size)
        assertEquals(1_200, ReferenceR3Strategy.BUDGET)
        assertEquals(3, ReferenceR3Strategy.MAX_POINTS)
        assertEquals(1.10, ReferenceR3Strategy.MIN_EV, 0.00001)
        assertEquals(40.0, ReferenceR3Strategy.MAX_ODDS, 0.00001)
        assertFalse(ReferenceR3Strategy.HISTORICAL_PURCHASES >= 360)
    }

    @Test
    fun evaluationNeverReturnsMoreThanThreePicksAndKeepsBudget() {
        val odds = ReferenceR3Strategy.allCombinations().associateWith { 20.0 }
        val result = ReferenceR3Strategy.evaluate(testRace(), odds, 1_200)
        assertTrue(result.picks.size <= 3)
        if (result.recommendation == RaceRecommendation.BUY) {
            assertEquals(1_200, result.picks.sumOf { it.recommendedStake })
            assertTrue(result.picks.all { (it.odds ?: 999.0) <= 40.0 })
            assertTrue(result.reason.contains("検証不合格"))
        }
    }

    private fun testRace() = RaceData(
        date = "2026-09-24", stadiumNumber = 1, raceNumber = 1, closedAt = "23:59",
        gradeNumber = null, title = "test", subtitle = "", distance = 1800, dayNumber = 1,
        racers = (1..6).map { lane ->
            Racer(
                lane = lane, name = "r$lane", registrationNumber = 4000 + lane, rank = "A1",
                branch = null, age = null, weight = 52.0, averageStart = 0.15 + lane * 0.001,
                nationalWinRate = 7.0 - lane * 0.2, nationalTop2 = null, nationalTop3 = null,
                localWinRate = 6.5 - lane * 0.15, localTop2 = null, localTop3 = null,
                motorNumber = lane, motorTop2 = 40.0 - lane, motorTop3 = null,
                boatNumber = lane, boatTop2 = 35.0, boatTop3 = null,
                preview = PreviewRacer(lane, 0.12 + lane * 0.005, 52.0, 0.0, 6.70 + lane * 0.01, 0.0)
            )
        },
        preview = PreviewData(2, null, 2, null, null, null), result = null
    )
}
