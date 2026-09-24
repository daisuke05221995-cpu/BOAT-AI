package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

class ModelAConditionalPredictorTest {
    @Test
    fun buildsFrozenStageRowWidths() {
        val input = input()
        val rows = ModelAConditionalPredictor.FeatureRows(input)

        assertEquals(545, rows.row(intArrayOf(), 0).size)
        assertEquals(715, rows.row(intArrayOf(1), 0).size)
        assertEquals(885, rows.row(intArrayOf(1, 2), 0).size)
    }

    @Test
    fun zeroScoresProduceUniform120CombinationForecast() {
        val predictor = ModelAConditionalPredictor(
            stage0Score = { 0.0 },
            stage1Score = { 0.0 },
            stage2Score = { 0.0 }
        )

        val forecast = predictor.predict(input())

        assertEquals(120, forecast.combinations.size)
        assertEquals(120, forecast.combinations.toSet().size)
        assertEquals("1-2-3", forecast.combinations.first().text)
        assertEquals("6-5-4", forecast.combinations.last().text)
        assertEquals(1.0, forecast.probabilities.sum(), 1e-12)
        forecast.probabilities.forEach { probability ->
            assertEquals(1.0 / 120.0, probability, 1e-12)
        }
        forecast.firstMarginals().forEach { probability ->
            assertEquals(1.0 / 6.0, probability, 1e-12)
        }
    }

    @Test
    fun laneSensitiveScoresRemainNormalizedAndOrdered() {
        fun candidateScore(row: DoubleArray): Double {
            val oneHotStart = 82 * 4
            return (0..5).first { row[oneHotStart + it] == 1.0 }.toDouble()
        }
        val predictor = ModelAConditionalPredictor(
            stage0Score = ::candidateScore,
            stage1Score = ::candidateScore,
            stage2Score = ::candidateScore
        )

        val forecast = predictor.predict(input())
        val marginals = forecast.firstMarginals()

        assertEquals(1.0, forecast.probabilities.sum(), 1e-12)
        assertEquals(1.0, marginals.sum(), 1e-12)
        for (index in 0 until marginals.lastIndex) {
            assertTrue(marginals[index + 1] > marginals[index])
        }
        assertTrue(forecast.probabilities.all { it.isFinite() && it > 0.0 })
    }

    @Test
    fun missingBoatValuesCreateMissingFlagsWithoutInfiniteRows() {
        val input = input()
        input.boat[2][7] = Double.NaN
        val rows = ModelAConditionalPredictor.FeatureRows(input)
        val row = rows.row(intArrayOf(0, 1), 2)
        val missingFlagStart = 82 * 3

        assertEquals(1.0, row[missingFlagStart + 7], 0.0)
        assertTrue(row.none { it.isInfinite() })
        assertTrue(row.any { it.isNaN() })
    }

    @Test
    fun temperatureCalibrationKeepsProbabilityMassOne() {
        val predictor = ModelAConditionalPredictor(
            stage0Score = { it[82 * 4] },
            stage1Score = { it[82 * 4 + 1] },
            stage2Score = { it[82 * 4 + 2] },
            temperature = 1.2
        )
        val forecast = predictor.predict(input())
        assertTrue(abs(forecast.probabilities.sum() - 1.0) <= 1e-12)
    }

    private fun input(): ModelAConditionalPredictor.Input {
        val boat = Array(6) { lane ->
            DoubleArray(82) { feature ->
                (lane + 1) * 0.1 + feature * 0.003
            }
        }
        val global = DoubleArray(24) { index -> index * 0.05 }
        global[22] = 7.0
        global[23] = 9.0
        return ModelAConditionalPredictor.Input(
            boat = boat,
            global = global,
            venue = 7,
            raceNumber = 9
        )
    }
}
