package jp.boatai.app

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ValueStrategyModelTest {
    @Test
    fun fullMarketSelectsAtMostConfiguredPointsAndAllocatesTheWholeBudget() {
        val model = model(maxPoints = 10)
        val combinations = model.allCombinations()
        assertEquals(120, combinations.size)
        assertEquals(120, combinations.toSet().size)

        val selection = model.select(race(), LearningProfile(), combinations.associateWith { 150.0 })

        assertEquals(RaceRecommendation.BUY, selection.recommendation)
        assertEquals(10, selection.picks.size)
        assertEquals(1_200, selection.picks.sumOf { it.recommendedStake })
        assertTrue(selection.picks.all { it.recommendedStake >= 100 && it.recommendedStake % 100 == 0 })
    }

    @Test
    fun lowExpectedValueAndInsufficientMarketBothSkip() {
        val model = model(maxPoints = 2)
        val combinations = model.allCombinations()
        val lowValue = model.select(race(), LearningProfile(), combinations.associateWith { 100.0 })
        val incomplete = model.select(race(), LearningProfile(), combinations.take(99).associateWith { 150.0 })

        assertEquals(RaceRecommendation.SKIP, lowValue.recommendation)
        assertTrue(lowValue.picks.isEmpty())
        assertEquals(RaceRecommendation.SKIP, incomplete.recommendation)
        assertTrue(incomplete.picks.isEmpty())
    }

    @Test
    fun equalAllocationPreservesTwoPointBudget() {
        val model = model(maxPoints = 2)
        val selection = model.select(race(), LearningProfile(), model.allCombinations().associateWith { 150.0 })

        assertEquals(RaceRecommendation.BUY, selection.recommendation)
        assertEquals(listOf(600, 600), selection.picks.map { it.recommendedStake })
    }

    @Test
    fun invalidModelFeatureDimensionsSkipSafely() {
        val model = model(maxPoints = 2, thirdFeatures = 64)
        val selection = model.select(race(), LearningProfile(), model.allCombinations().associateWith { 150.0 })

        assertEquals(RaceRecommendation.SKIP, selection.recommendation)
        assertTrue(selection.picks.isEmpty())
    }

    private fun model(maxPoints: Int, thirdFeatures: Int = 65): ValueStrategyModel {
        fun section(features: Int) = JSONObject()
            .put("mean", JSONArray(List(features) { 0.0 }))
            .put("std", JSONArray(List(features) { 1.0 }))
            .put("weights", JSONArray(List(features) { 0.0 }))
        val root = JSONObject()
            .put("trainedThrough", "2026-09-22")
            .put("strategy", JSONObject()
                .put("alpha", 0.25)
                .put("minEv", 1.05)
                .put("minProbability", 0.005)
                .put("maxOdds", 150.0)
                .put("maxPoints", maxPoints)
                .put("allocationMode", "equal")
                .put("budget", 1_200))
            .put("first", section(32))
            .put("second", section(50))
            .put("third", section(thirdFeatures))
        return ValueStrategyModel.fromJson(root.toString())
    }

    private fun race() = RaceData(
        date = "2026-09-23", stadiumNumber = 1, raceNumber = 1, closedAt = "23:59",
        gradeNumber = null, title = "test", subtitle = "", distance = 1800, dayNumber = 1,
        racers = (1..6).map { lane ->
            Racer(
                lane = lane, name = "r$lane", registrationNumber = null, rank = "A1",
                branch = null, age = null, weight = null, averageStart = 0.15,
                nationalWinRate = 6.0, nationalTop2 = null, nationalTop3 = null,
                localWinRate = 6.0, localTop2 = null, localTop3 = null,
                motorNumber = 1, motorTop2 = 35.0, motorTop3 = null,
                boatNumber = 1, boatTop2 = 35.0, boatTop3 = null, preview = null
            )
        },
        preview = null, result = null
    )
}
