package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AverageRoiReferenceStrategyTest {
    @Test
    fun exposesAiFirstPolicyAndHistoricalRoiIsNotClaimedForCurrentLogic() {
        assertEquals(120, AverageRoiReferenceStrategy.allCombinations().distinct().size)
        assertEquals(1_200, AverageRoiReferenceStrategy.BUDGET)
        assertEquals(2, AverageRoiReferenceStrategy.MAX_POINTS)
        assertEquals(0.80, AverageRoiReferenceStrategy.MODEL_WEIGHT, 0.00001)
        assertEquals(1.08, AverageRoiReferenceStrategy.MIN_MARKET_EDGE_RATIO, 0.00001)
        assertEquals(2, AverageRoiReferenceStrategy.MAX_FIRST_FORM_RANK)
        assertEquals(1.05, AverageRoiReferenceStrategy.MIN_EV, 0.00001)
        assertEquals(150.0, AverageRoiReferenceStrategy.MAX_ODDS, 0.00001)
        assertEquals(117.3, AverageRoiReferenceStrategy.HISTORICAL_ROI, 0.00001)
        assertFalse(AverageRoiReferenceStrategy.HISTORICAL_ROI_APPLIES_TO_CURRENT)
        assertFalse(AverageRoiReferenceStrategy.RELEASE_QUALIFIED)
    }

    @Test
    fun weakLaneOneIsNotPromotedToFirstJustBecauseOfInsideLane() {
        val odds = AverageRoiReferenceStrategy.allCombinations().associateWith { 40.0 }
        val race = weakLaneOneRace()
        val result = AverageRoiReferenceStrategy.evaluate(race, odds, 1_200)

        assertTrue(AverageRoiReferenceStrategy.formScore(race.racers.first { it.lane == 3 }) >
            AverageRoiReferenceStrategy.formScore(race.racers.first { it.lane == 1 }))
        if (result.recommendation == RaceRecommendation.BUY) {
            assertTrue(result.picks.isNotEmpty())
            assertTrue(result.picks.none { it.combination.startsWith("1-") })
            assertEquals(1_200, result.picks.sumOf { it.recommendedStake })
        }
    }

    @Test
    fun evaluationNeverReturnsMoreThanTwoPicksAndKeepsBudget() {
        val odds = AverageRoiReferenceStrategy.allCombinations().associateWith { 40.0 }
        val result = AverageRoiReferenceStrategy.evaluate(strongMixedRace(), odds, 1_200)
        assertTrue(result.picks.size <= 2)
        if (result.recommendation == RaceRecommendation.BUY) {
            assertEquals(1_200, result.picks.sumOf { it.recommendedStake })
            assertTrue(result.picks.all { (it.odds ?: 999.0) <= 150.0 })
            assertTrue(result.reason.contains("AI主体予想"))
            assertFalse(result.reason.contains("ROI117.3%"))
        }
    }

    private fun weakLaneOneRace() = baseRace { lane ->
        when (lane) {
            1 -> racer(lane, 4.2, 3.8, 26.0, 0.19, 6.88, 0.18)
            3 -> racer(lane, 8.4, 8.0, 48.0, 0.11, 6.62, 0.08)
            4 -> racer(lane, 7.8, 7.4, 44.0, 0.12, 6.66, 0.10)
            else -> racer(lane, 6.0, 5.8, 34.0, 0.16, 6.78, 0.14)
        }
    }

    private fun strongMixedRace() = baseRace { lane ->
        when (lane) {
            1 -> racer(lane, 7.2, 6.8, 38.0, 0.14, 6.72, 0.12)
            2 -> racer(lane, 7.8, 7.4, 43.0, 0.12, 6.67, 0.10)
            3 -> racer(lane, 7.6, 7.2, 42.0, 0.13, 6.68, 0.11)
            else -> racer(lane, 6.1, 5.9, 34.0, 0.16, 6.80, 0.15)
        }
    }

    private fun baseRace(factory: (Int) -> Racer) = RaceData(
        date = "2026-09-24", stadiumNumber = 1, raceNumber = 1, closedAt = "23:59",
        gradeNumber = null, title = "test", subtitle = "", distance = 1800, dayNumber = 1,
        racers = (1..6).map(factory),
        preview = PreviewData(2, null, 2, null, null, null), result = null
    )

    private fun racer(
        lane: Int,
        national: Double,
        local: Double,
        motor: Double,
        averageStart: Double,
        exhibition: Double,
        previewStart: Double
    ) = Racer(
        lane = lane, name = "r$lane", registrationNumber = 4000 + lane, rank = "A1",
        branch = null, age = null, weight = 52.0, averageStart = averageStart,
        nationalWinRate = national, nationalTop2 = null, nationalTop3 = null,
        localWinRate = local, localTop2 = null, localTop3 = null,
        motorNumber = lane, motorTop2 = motor, motorTop3 = null,
        boatNumber = lane, boatTop2 = 35.0, boatTop3 = null,
        preview = PreviewRacer(lane, previewStart, 52.0, 0.0, exhibition, 0.0)
    )
}
