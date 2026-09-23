package jp.boatai.app

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.sin

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

    @Test
    fun pythonReferenceAndAndroidAgreeOnFeatureModelAndProbabilityAllocation() {
        val model = model(maxPoints = 4, allocationMode = "probability", weighted = true)
        val race = race().copy(
            racers = race().racers.map { racer ->
                val lane = racer.lane
                racer.copy(
                    nationalWinRate = 4.6 + 0.32 * lane,
                    localWinRate = 5.8 - 0.13 * lane,
                    motorTop2 = 28.0 + 3.4 * lane,
                    boatTop2 = 33.0 + 2.1 * lane,
                    averageStart = 0.12 + 0.013 * lane,
                    preview = PreviewRacer(
                        course = if (lane == 2) 3 else if (lane == 3) 2 else lane,
                        startTiming = 0.1 + 0.012 * lane,
                        weight = null, weightAdjustment = null,
                        exhibitionTime = 6.7 + 0.035 * lane, tilt = null
                    )
                )
            },
            preview = PreviewData(
                windSpeed = 4, windDirection = null, waveHeight = 3, weather = null,
                airTemperature = null, waterTemperature = null
            )
        )
        val odds = model.allCombinations().associateWith { combination ->
            val (first, second, third) = combination.split("-").map(String::toInt)
            (68 + ((first * 17 + second * 11 + third * 7) % 81)).toDouble()
        }

        val actual = model.select(race, LearningProfile(), odds)
        // Recompute the expected values with scripts/value_strategy_parity_fixture.py.
        assertEquals(RaceRecommendation.BUY, actual.recommendation)
        assertEquals(listOf("6-4-1", "6-1-5", "6-5-1", "6-5-4"), actual.picks.map { it.combination })
        assertEquals(listOf(300, 200, 400, 300), actual.picks.map { it.recommendedStake })
        listOf(2.036882015331196, 1.9540563643325664, 1.868608339528893, 1.8343676391415265)
            .zip(actual.picks).forEach { (expected, pick) ->
                assertEquals(expected, pick.score, 1e-7)
            }
    }

    private fun model(
        maxPoints: Int,
        thirdFeatures: Int = 65,
        allocationMode: String = "equal",
        weighted: Boolean = false
    ): ValueStrategyModel {
        fun section(features: Int, phase: Double) = JSONObject()
            .put("mean", JSONArray(List(features) { 0.0 }))
            .put("std", JSONArray(List(features) { 1.0 }))
            .put("weights", JSONArray(List(features) { index ->
                if (weighted) sin((index + 1) * 0.61 + phase) * 0.28 else 0.0
            }))
        val root = JSONObject()
            .put("trainedThrough", "2026-09-22")
            .put("strategy", JSONObject()
                .put("alpha", 0.25)
                .put("minEv", 1.05)
                .put("minProbability", 0.005)
                .put("maxOdds", 150.0)
                .put("maxPoints", maxPoints)
                .put("allocationMode", allocationMode)
                .put("budget", 1_200))
            .put("first", section(32, 0.3))
            .put("second", section(50, 0.7))
            .put("third", section(thirdFeatures, 1.1))
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
