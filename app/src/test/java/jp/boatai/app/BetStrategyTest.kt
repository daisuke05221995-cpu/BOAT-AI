package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class BetStrategyTest {
    @Test
    fun allocatesFourPicksWithinRequestedBudget() {
        val race = testRace()
        val picks = (1..4).map { PredictionPick("1-2-${(it + 2).coerceAtMost(6)}", 100.0 - it) }
        val result = BetStrategy.allocate(race, picks, 1_200)
        assertEquals(1_200, result.sumOf { it.recommendedStake })
        assertTrue(result.all { it.recommendedStake >= 100 && it.recommendedStake % 100 == 0 })
    }

    @Test
    fun clampsBudgetToUserLimit() {
        val result = BetStrategy.allocate(testRace(), listOf(PredictionPick("1-2-3", 10.0)), 9_999)
        assertEquals(3_000, result.single().recommendedStake)
    }

    private fun testRace() = RaceData(
        date = "2026-09-22", stadiumNumber = 1, raceNumber = 1, closedAt = "12:00",
        gradeNumber = null, title = "test", subtitle = "", distance = 1800, dayNumber = 1,
        racers = (1..6).map { lane ->
            Racer(
                lane = lane,
                name = "r$lane",
                registrationNumber = null,
                rank = "A1",
                branch = null,
                age = null,
                weight = null,
                averageStart = 0.15,
                nationalWinRate = 6.0,
                nationalTop2 = null,
                nationalTop3 = null,
                localWinRate = 6.0,
                localTop2 = null,
                localTop3 = null,
                motorNumber = 1,
                motorTop2 = 35.0,
                motorTop3 = null,
                boatNumber = 1,
                boatTop2 = null,
                boatTop3 = null,
                preview = null
            )
        },
        preview = null,
        result = null
    )
}
