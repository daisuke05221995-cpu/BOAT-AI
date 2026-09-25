package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AverageRoiReferenceStrategyTest {
    @Test
    fun forecastAndLivePurchaseRecommendationAreEnabled() {
        assertTrue(AverageRoiReferenceStrategy.FORECAST_ENABLED)
        assertTrue(AverageRoiReferenceStrategy.MODEL_A_FORECAST_RELEASE_QUALIFIED)
        assertTrue(AverageRoiReferenceStrategy.PURCHASE_RECOMMENDATION_ENABLED)
        assertTrue(AverageRoiReferenceStrategy.ENABLED)
        assertFalse(AverageRoiReferenceStrategy.RELEASE_QUALIFIED)
        assertFalse(AverageRoiReferenceStrategy.HISTORICAL_ROI_APPLIES_TO_CURRENT)
        assertEquals(4, AverageRoiReferenceStrategy.FORECAST_POINTS)
        assertEquals(4, AverageRoiReferenceStrategy.MIN_PURCHASE_POINTS)
        assertEquals(8, AverageRoiReferenceStrategy.MAX_PURCHASE_POINTS)
    }

    @Test
    fun genericValueOddsFacadeExposesAll120ForLiveModelA() {
        PredictionEngine.installValueStrategyModel(null)
        val combinations = PredictionEngine.valueOddsCombinations()
        assertEquals(120, combinations.size)
        assertEquals(120, combinations.toSet().size)
    }

    @Test
    fun genericValueOddsFacadeEvaluatesAndCachesLiveModelA() {
        PredictionEngine.installValueStrategyModel(null)
        PredictionEngine.clearValueSelections()
        val race = strongLaneOneRace()
        val odds = AverageRoiReferenceStrategy.allCombinations().associateWith { 200.0 }

        val selection = PredictionEngine.applyValueOdds(race, odds)

        assertNotNull(selection)
        assertNotNull(PredictionEngine.cachedValueSelection(race))
        assertEquals(selection?.recommendation, PredictionEngine.cachedValueSelection(race)?.recommendation)
        PredictionEngine.clearValueSelections()
    }

    @Test
    fun forecastDoesNotNeedOddsAndWeakLaneOneIsNotForcedToFirst() {
        val race = weakLaneOneRace()
        val picks = AverageRoiReferenceStrategy.forecast(race, 4)
        assertEquals(4, picks.size)
        assertTrue(picks.first().combination.startsWith("3-"))
        assertTrue(picks.first().reason.contains("AI着順確率"))
        assertTrue(picks.zipWithNext().all { (a,b) -> a.score >= b.score })
    }

    @Test
    fun genuinelyStrongLaneOneCanStillLeadForecast() {
        val picks = AverageRoiReferenceStrategy.forecast(strongLaneOneRace(), 4)
        assertEquals(4, picks.size)
        assertTrue(picks.first().combination.startsWith("1-"))
    }

    @Test
    fun positiveLiveValueCanProduceVariablePurchaseRecommendation() {
        val probabilities = uniformProbabilities()
        val odds = AverageRoiReferenceStrategy.allCombinations().associateWith { 200.0 }
        val result = AverageRoiReferenceStrategy.evaluateProbabilities(probabilities, odds, 3_000)
        assertEquals(RaceRecommendation.BUY, result.recommendation)
        assertTrue(result.picks.size in 4..8)
        assertTrue(result.picks.all { it.recommendedStake >= 100 && it.recommendedStake % 100 == 0 })
        assertTrue(result.picks.sumOf { it.recommendedStake } in 1_000..3_000)
        assertTrue(result.reason.contains("期待対数効用がプラス"))
    }

    @Test
    fun poorLiveValueIsSkipped() {
        val probabilities = uniformProbabilities()
        val odds = AverageRoiReferenceStrategy.allCombinations().associateWith { 50.0 }
        val result = AverageRoiReferenceStrategy.evaluateProbabilities(probabilities, odds, 3_000)
        assertEquals(RaceRecommendation.SKIP, result.recommendation)
        assertTrue(result.picks.isEmpty())
        assertTrue(result.reason.contains("見送り"))
    }

    @Test
    fun incompleteOddsAreSkipped() {
        val probabilities = uniformProbabilities()
        val odds = AverageRoiReferenceStrategy.allCombinations().take(119).associateWith { 150.0 }
        val result = AverageRoiReferenceStrategy.evaluateProbabilities(probabilities, odds, 3_000)
        assertEquals(RaceRecommendation.SKIP, result.recommendation)
        assertTrue(result.picks.isEmpty())
        assertTrue(result.reason.contains("120通り"))
    }

    private fun uniformProbabilities(): Map<String, Double> =
        AverageRoiReferenceStrategy.allCombinations().associateWith { 1.0 / 120.0 }

    private fun weakLaneOneRace() = baseRace { lane ->
        when (lane) {
            1 -> racer(lane, 4.2, 3.8, 26.0, 0.19, 6.88, 0.18)
            3 -> racer(lane, 8.4, 8.0, 48.0, 0.11, 6.62, 0.08)
            4 -> racer(lane, 7.8, 7.4, 44.0, 0.12, 6.66, 0.10)
            else -> racer(lane, 6.0, 5.8, 34.0, 0.16, 6.78, 0.14)
        }
    }

    private fun strongLaneOneRace() = baseRace { lane ->
        when (lane) {
            1 -> racer(lane, 9.0, 8.7, 52.0, 0.10, 6.58, 0.07)
            2 -> racer(lane, 7.0, 6.8, 38.0, 0.14, 6.72, 0.12)
            3 -> racer(lane, 6.8, 6.5, 36.0, 0.15, 6.75, 0.13)
            else -> racer(lane, 5.7, 5.4, 32.0, 0.17, 6.82, 0.16)
        }
    }

    private fun baseRace(factory: (Int) -> Racer) = RaceData(
        date = "2026-09-25", stadiumNumber = 1, raceNumber = 1, closedAt = "23:59",
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
