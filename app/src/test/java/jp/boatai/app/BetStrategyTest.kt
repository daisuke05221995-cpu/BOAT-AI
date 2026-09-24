package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
    fun preservesUpstreamEqualAllocationAtValidatedBudget() {
        val picks = listOf(
            PredictionPick("1-2-3", 1.2, odds = 20.0, recommendedStake = 600, reason = "value"),
            PredictionPick("1-3-2", 1.1, odds = 25.0, recommendedStake = 600, reason = "value")
        )

        val result = BetStrategy.allocate(testRace(), picks, 1_200)

        assertEquals(listOf(600, 600), result.map { it.recommendedStake })
        assertEquals(listOf("value", "value"), result.map { it.reason })
    }

    @Test
    fun scalesUpstreamAllocationWithoutChangingItsRatio() {
        val picks = listOf(
            PredictionPick("1-2-3", 1.2, odds = 20.0, recommendedStake = 600),
            PredictionPick("1-3-2", 1.1, odds = 25.0, recommendedStake = 600)
        )

        val result = BetStrategy.allocate(testRace(), picks, 2_000)

        assertEquals(listOf(1_000, 1_000), result.map { it.recommendedStake })
        assertEquals(2_000, result.sumOf { it.recommendedStake })
    }

    @Test
    fun preservesValidatedUnevenAllocationWhenBudgetUnchanged() {
        val picks = listOf(
            PredictionPick("1-2-3", 10.0, recommendedStake = 500),
            PredictionPick("1-3-2", 9.0, recommendedStake = 400),
            PredictionPick("1-2-4", 8.0, recommendedStake = 200),
            PredictionPick("1-4-2", 7.0, recommendedStake = 100)
        )

        val result = BetStrategy.allocate(testRace(), picks, 1_200)

        assertEquals(listOf(500, 400, 200, 100), result.map { it.recommendedStake })
    }

    @Test
    fun manualBudgetChangeRebalancesAcrossAllPicks() {
        val picks = listOf(
            PredictionPick("1-2-3", 10.0, recommendedStake = 500),
            PredictionPick("1-3-2", 9.0, recommendedStake = 400),
            PredictionPick("1-2-4", 8.0, recommendedStake = 200),
            PredictionPick("1-4-2", 7.0, recommendedStake = 100)
        )

        val at1300 = BetStrategy.allocate(testRace(), picks, 1_300)
        assertEquals(listOf(400, 300, 300, 300), at1300.map { it.recommendedStake })

        val at1400 = BetStrategy.allocate(testRace(), at1300, 1_400)
        assertEquals(listOf(400, 400, 300, 300), at1400.map { it.recommendedStake })

        val backTo1300 = BetStrategy.allocate(testRace(), at1400, 1_300)
        assertEquals(listOf(400, 300, 300, 300), backTo1300.map { it.recommendedStake })
    }

    @Test
    fun clampsBudgetToUserLimit() {
        val result = BetStrategy.allocate(testRace(), listOf(PredictionPick("1-2-3", 10.0)), 9_999)
        assertEquals(3_000, result.single().recommendedStake)
    }

    @Test
    fun alertBuyGateMatchesDisplayedOddsDecision() {
        val picks = listOf(
            PredictionPick("1-2-3", 10.0, odds = 4.0, recommendedStake = 500),
            PredictionPick("1-3-2", 9.0, odds = 4.0, recommendedStake = 400),
            PredictionPick("1-2-4", 8.0, odds = 8.0, recommendedStake = 200),
            PredictionPick("1-4-2", 7.0, odds = 15.0, recommendedStake = 100)
        )

        assertTrue(BetStrategy.oddsRecommended(picks))
        assertTrue(BetStrategy.oddsDecision(picks).startsWith("購入推奨"))
    }

    @Test
    fun alertSkipGateMatchesDisplayedOddsDecision() {
        val picks = listOf(
            PredictionPick("1-2-3", 10.0, odds = 1.5, recommendedStake = 500),
            PredictionPick("1-3-2", 9.0, odds = 1.5, recommendedStake = 400),
            PredictionPick("1-2-4", 8.0, odds = 1.5, recommendedStake = 200),
            PredictionPick("1-4-2", 7.0, odds = 1.5, recommendedStake = 100)
        )

        assertFalse(BetStrategy.oddsRecommended(picks))
        assertTrue(BetStrategy.oddsDecision(picks).startsWith("見送り"))
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
