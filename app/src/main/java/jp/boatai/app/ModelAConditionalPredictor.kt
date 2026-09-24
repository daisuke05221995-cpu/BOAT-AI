package jp.boatai.app

import kotlin.math.exp
import kotlin.math.pow

/**
 * Android-side probability engine for frozen v0.16 forecast-only Model A.
 *
 * This class mirrors scripts/v016_r2_model.py context()/rows()/predict() for the
 * r4 reaction variant. It is deliberately not wired into PredictionEngine yet.
 * The caller supplies the already constructed market-free Model A boat features
 * (82 values per lane) and reaction-variant global features (24 values).
 */
internal class ModelAConditionalPredictor(
    private val stage0Score: (DoubleArray) -> Double,
    private val stage1Score: (DoubleArray) -> Double,
    private val stage2Score: (DoubleArray) -> Double,
    private val temperature: Double = 1.0
) {
    init {
        require(temperature > 0.0 && temperature.isFinite())
    }

    constructor(
        stage0: LightGbmTextModel,
        stage1: LightGbmTextModel,
        stage2: LightGbmTextModel,
        temperature: Double = 1.0
    ) : this(stage0::predict, stage1::predict, stage2::predict, temperature)

    data class Input(
        val boat: Array<DoubleArray>,
        val global: DoubleArray,
        val venue: Int,
        val raceNumber: Int
    )

    data class Combination(val first: Int, val second: Int, val third: Int) {
        init {
            require(first in 0..5 && second in 0..5 && third in 0..5)
            require(first != second && first != third && second != third)
        }

        val text: String get() = "${first + 1}-${second + 1}-${third + 1}"
    }

    data class Forecast(
        val combinations: List<Combination>,
        val probabilities: DoubleArray
    ) {
        init {
            require(combinations.size == 120)
            require(probabilities.size == 120)
        }

        fun firstMarginals(): DoubleArray {
            val out = DoubleArray(6)
            probabilities.forEachIndexed { index, probability ->
                out[combinations[index].first] += probability
            }
            return out
        }
    }

    fun predict(input: Input): Forecast {
        val rows = FeatureRows(input)

        val first = softmax(
            DoubleArray(6) { candidate -> stage0Score(rows.row(intArrayOf(), candidate)) }
        )

        val second = Array(6) { firstLane ->
            val candidates = available(intArrayOf(firstLane))
            val probability = softmax(
                DoubleArray(candidates.size) { index ->
                    stage1Score(rows.row(intArrayOf(firstLane), candidates[index]))
                }
            )
            DoubleArray(6).also { table ->
                candidates.forEachIndexed { index, candidate -> table[candidate] = probability[index] }
            }
        }

        val third = Array(6) { Array(6) { DoubleArray(6) } }
        for (firstLane in 0..5) {
            for (secondLane in 0..5) {
                if (secondLane == firstLane) continue
                val prefix = intArrayOf(firstLane, secondLane)
                val candidates = available(prefix)
                val probability = softmax(
                    DoubleArray(candidates.size) { index ->
                        stage2Score(rows.row(prefix, candidates[index]))
                    }
                )
                candidates.forEachIndexed { index, candidate ->
                    third[firstLane][secondLane][candidate] = probability[index]
                }
            }
        }

        val combinations = combinations()
        val chained = DoubleArray(combinations.size) { index ->
            val combo = combinations[index]
            first[combo.first] * second[combo.first][combo.second] * third[combo.first][combo.second][combo.third]
        }
        require(chained.all { it.isFinite() && it >= 0.0 }) { "Invalid Model A chain probability" }
        val sum = chained.sum()
        require(kotlin.math.abs(sum - 1.0) <= 1e-10) { "Model A chain probability sum=$sum" }

        val calibrated = if (temperature == 1.0) {
            chained
        } else {
            val powered = DoubleArray(chained.size) { index -> chained[index].coerceAtLeast(1e-15).pow(1.0 / temperature) }
            val denominator = powered.sum()
            DoubleArray(powered.size) { index -> powered[index] / denominator }
        }
        return Forecast(combinations, calibrated)
    }

    internal class FeatureRows(private val input: Input) {
        private val boatDimension: Int
        private val mean: DoubleArray
        private val spread: DoubleArray
        private val raw: Array<DoubleArray>
        private val expandedGlobal: DoubleArray

        init {
            require(input.boat.size == 6) { "Model A requires six lanes" }
            boatDimension = input.boat.firstOrNull()?.size ?: 0
            require(boatDimension == 82) { "Frozen reaction Model A requires 82 boat features, got $boatDimension" }
            require(input.boat.all { it.size == boatDimension }) { "Inconsistent boat feature width" }
            require(input.global.size == 24) { "Frozen reaction Model A requires 24 global features, got ${input.global.size}" }
            require(input.venue in 1..24) { "Venue must be 1..24" }
            require(input.raceNumber > 0) { "Race number must be positive" }

            mean = DoubleArray(boatDimension)
            spread = DoubleArray(boatDimension)
            for (feature in 0 until boatDimension) {
                val finite = input.boat.map { it[feature] }.filter { it.isFinite() }
                mean[feature] = if (finite.isEmpty()) Double.NaN else finite.average()
                spread[feature] = if (finite.isEmpty()) Double.NaN else finite.maxOrNull()!! - finite.minOrNull()!!
            }

            raw = Array(6) { lane ->
                DoubleArray(boatDimension * 4).also { row ->
                    var offset = 0
                    for (value in input.boat[lane]) row[offset++] = value
                    for (feature in 0 until boatDimension) row[offset++] = input.boat[lane][feature] - mean[feature]
                    for (feature in 0 until boatDimension) row[offset++] = spread[feature]
                    for (feature in 0 until boatDimension) row[offset++] = if (input.boat[lane][feature].isFinite()) 0.0 else 1.0
                }
            }

            val values = ArrayList<Double>(211)
            // Reaction-variant global array: first 22 values, then venue/race in the final two positions.
            for (index in 0 until input.global.size - 2) values += input.global[index]
            for (venueIndex in 1..24) values += if (venueIndex == input.venue) 1.0 else 0.0
            values += input.raceNumber.toDouble()
            for (feature in 0 until boatDimension) values += input.boat[0][feature]
            for (feature in 0 until boatDimension) values += input.boat[0][feature] - mean[feature]
            expandedGlobal = values.toDoubleArray()
            require(expandedGlobal.size == 211)
        }

        fun row(prefix: IntArray, candidate: Int): DoubleArray {
            require(prefix.size in 0..2)
            require(candidate in 0..5)
            require(prefix.all { it in 0..5 })
            require(prefix.distinct().size == prefix.size)
            require(candidate !in prefix)

            val expectedSize = 545 + 170 * prefix.size
            val values = ArrayList<Double>(expectedSize)
            raw[candidate].forEach(values::add)
            oneHot(candidate).forEach(values::add)
            expandedGlobal.forEach(values::add)

            for (selected in prefix) {
                input.boat[selected].forEach(values::add)
                for (feature in 0 until boatDimension) {
                    values += input.boat[candidate][feature] - input.boat[selected][feature]
                }
                oneHot(selected).forEach(values::add)
            }
            require(values.size == expectedSize) { "stage ${prefix.size}: row width ${values.size} != $expectedSize" }
            // Python rows() ends with .astype(np.float32). Preserve that exact
            // inference contract before the serialized LightGBM thresholds are evaluated.
            return DoubleArray(values.size) { index -> values[index].toFloat().toDouble() }
        }

        private fun oneHot(lane: Int): DoubleArray = DoubleArray(6) { index -> if (index == lane) 1.0 else 0.0 }
    }

    companion object {
        fun combinations(): List<Combination> = buildList(120) {
            for (first in 0..5) {
                for (second in 0..5) {
                    if (second == first) continue
                    for (third in 0..5) {
                        if (third == first || third == second) continue
                        add(Combination(first, second, third))
                    }
                }
            }
        }

        private fun available(prefix: IntArray): IntArray = (0..5).filter { it !in prefix }.toIntArray()

        private fun softmax(raw: DoubleArray): DoubleArray {
            require(raw.isNotEmpty())
            require(raw.all { it.isFinite() }) { "Non-finite Model A raw score" }
            val max = raw.maxOrNull()!!
            val expValues = DoubleArray(raw.size) { index -> exp(raw[index] - max) }
            val denominator = expValues.sum()
            require(denominator.isFinite() && denominator > 0.0)
            return DoubleArray(raw.size) { index -> expValues[index] / denominator }
        }
    }
}
