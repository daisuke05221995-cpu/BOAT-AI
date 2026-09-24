package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AverageRoiReferenceStrategyTest {
    @Test
    fun exposesFrozenAverageRoiPolicyAndAllCombinations() {
        assertEquals(120, AverageRoiReferenceStrategy.allCombinations().distinct().size)
        assertEquals(1_200, AverageRoiReferenceStrategy.BUDGET)
        assertEquals(2, AverageRoiReferenceStrategy.MAX_POINTS)
        assertEquals(0.25, AverageRoiReferenceStrategy.ALPHA, 0.00001)
        assertEquals(1.05, AverageRoiReferenceStrategy.MIN_EV, 0.00001)
        assertEquals(0.005, AverageRoiReferenceStrategy.MIN_PROBABILITY, 0.00001)
        assertEquals(150.0, AverageRoiReferenceStrategy.MAX_ODDS, 0.00001)
        assertEquals(2_407, AverageRoiReferenceStrategy.HISTORICAL_PURCHASES)
        assertEquals(45, AverageRoiReferenceStrategy.HISTORICAL_HITS)
        assertEquals(117.3, AverageRoiReferenceStrategy.HISTORICAL_ROI, 0.00001)
        assertEquals(4, AverageRoiReferenceStrategy.POSITIVE_MONTHS)
        assertEquals(5, AverageRoiReferenceStrategy.TOTAL_MONTHS)
        assertFalse(AverageRoiReferenceStrategy.RELEASE_QUALIFIED)
    }

    @Test
    fun evaluationNeverReturnsMoreThanTwoPicksAndKeepsBudget() {
        val odds = AverageRoiReferenceStrategy.allCombinations().associateWith { 20.0 }
        val result = AverageRoiReferenceStrategy.evaluate(testRace(), odds, 1_200)
        assertTrue(result.picks.size <= 2)
        if (result.recommendation == RaceRecommendation.BUY) {
            assertEquals(1_200, result.picks.sumOf { it.recommendedStake })
            assertTrue(result.picks.all { (it.odds ?: 999.0) <= 150.0 })
            assertTrue(result.reason.contains("2,407購入"))
            assertTrue(result.reason.contains("複数年検証は不合格"))
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
