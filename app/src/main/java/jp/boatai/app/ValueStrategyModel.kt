package jp.boatai.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.exp
import kotlin.math.floor
import kotlin.math.ln

internal data class ValueStrategyConfig(
    val alpha: Double,
    val minEv: Double,
    val minProbability: Double,
    val maxOdds: Double,
    val maxPoints: Int,
    val allocationMode: String,
    val budget: Int
)

private data class ModelSection(
    val mean: DoubleArray,
    val std: DoubleArray,
    val weights: DoubleArray
)

internal data class ValueSelection(
    val picks: List<PredictionPick>,
    val recommendation: RaceRecommendation,
    val reason: String
)

internal class ValueStrategyModel private constructor(
    val trainedThrough: String,
    val config: ValueStrategyConfig,
    private val first: ModelSection,
    private val second: ModelSection,
    private val third: ModelSection
) {
    fun select(
        race: RaceData,
        learning: LearningProfile,
        officialOdds: Map<String, Double>
    ): ValueSelection {
        if (race.racers.size != 6 || officialOdds.size < 100) {
            return ValueSelection(
                picks = emptyList(),
                recommendation = RaceRecommendation.SKIP,
                reason = "見送り：公式3連単オッズが十分に取得できていません"
            )
        }
        val modelProbabilities = trifectaProbabilities(race, learning)
        if (modelProbabilities.size != 120) {
            return ValueSelection(emptyList(), RaceRecommendation.SKIP, "見送り：AI確率を計算できません")
        }

        val inverse = officialOdds.mapValues { (_, odds) -> if (odds > 0.0) 1.0 / odds else 0.0 }
            .filterValues { it > 0.0 }
        val inverseTotal = inverse.values.sum()
        if (inverseTotal <= 0.0) {
            return ValueSelection(emptyList(), RaceRecommendation.SKIP, "見送り：公式オッズを確率へ変換できません")
        }

        data class Candidate(
            val combination: String,
            val modelP: Double,
            val marketP: Double,
            val odds: Double,
            var blendedP: Double = 0.0,
            var expectedValue: Double = 0.0
        )

        val candidates = modelProbabilities.mapNotNull { (combination, modelP) ->
            val odds = officialOdds[combination]?.takeIf { it > 0.0 } ?: return@mapNotNull null
            val marketP = (inverse[combination] ?: return@mapNotNull null) / inverseTotal
            Candidate(combination, modelP, marketP, odds)
        }
        if (candidates.size < 100) {
            return ValueSelection(emptyList(), RaceRecommendation.SKIP, "見送り：有効な公式オッズが不足しています")
        }

        val rawBlend = candidates.map { candidate ->
            exp(
                config.alpha * ln(candidate.modelP.coerceAtLeast(1e-12)) +
                    (1.0 - config.alpha) * ln(candidate.marketP.coerceAtLeast(1e-12))
            )
        }
        val blendTotal = rawBlend.sum()
        if (blendTotal <= 0.0) {
            return ValueSelection(emptyList(), RaceRecommendation.SKIP, "見送り：期待値を計算できません")
        }
        candidates.forEachIndexed { index, candidate ->
            candidate.blendedP = rawBlend[index] / blendTotal
            candidate.expectedValue = candidate.blendedP * candidate.odds
        }

        val selected = candidates
            .asSequence()
            .filter { it.expectedValue >= config.minEv }
            .filter { it.blendedP >= config.minProbability }
            .filter { it.odds <= config.maxOdds }
            .sortedWith(compareByDescending<Candidate> { it.expectedValue }.thenByDescending { it.blendedP })
            .take(config.maxPoints.coerceIn(1, 10))
            .toList()

        if (selected.isEmpty()) {
            return ValueSelection(
                picks = emptyList(),
                recommendation = RaceRecommendation.SKIP,
                reason = "見送り：AI確率と公式オッズの期待値条件に届きません"
            )
        }

        val stakes = allocate(selected.map { Triple(it.blendedP, it.odds, it.expectedValue) })
        val picks = selected.mapIndexed { index, candidate ->
            PredictionPick(
                combination = candidate.combination,
                score = candidate.expectedValue,
                odds = candidate.odds,
                recommendedStake = stakes[index],
                tier = when {
                    index == 0 && candidate.odds < 15.0 -> BetTier.MAIN
                    candidate.odds >= 35.0 -> BetTier.LONG
                    else -> BetTier.MID
                },
                reason = "AI確率と公式オッズの期待値基準を通過"
            )
        }
        return ValueSelection(
            picks = picks,
            recommendation = RaceRecommendation.BUY,
            reason = "購入推奨：公式オッズ反映後の期待値基準を通過（${picks.size}点）"
        )
    }

    fun allCombinations(): List<String> = buildList(120) {
        for (firstLane in 1..6) {
            for (secondLane in 1..6) {
                if (secondLane == firstLane) continue
                for (thirdLane in 1..6) {
                    if (thirdLane == firstLane || thirdLane == secondLane) continue
                    add("$firstLane-$secondLane-$thirdLane")
                }
            }
        }
    }

    private fun allocate(items: List<Triple<Double, Double, Double>>): List<Int> {
        val count = items.size
        if (count <= 0) return emptyList()
        val totalUnits = (config.budget.coerceIn(100, 3_000) / 100).coerceAtLeast(count)
        val units = MutableList(count) { 1 }
        var remaining = totalUnits - count
        if (remaining <= 0) return units.map { it * 100 }

        if (config.allocationMode == "equal") {
            var cursor = 0
            while (remaining > 0) {
                units[cursor % count] += 1
                cursor += 1
                remaining -= 1
            }
            return units.map { it * 100 }
        }

        val weights = items.map { (probability, odds, _) ->
            if (config.allocationMode == "edge") {
                ((probability * odds - 1.0) / (odds - 1.0).coerceAtLeast(1e-9)).coerceAtLeast(0.0)
            } else {
                probability.coerceAtLeast(0.0)
            }
        }
        val totalWeight = weights.sum()
        if (totalWeight <= 0.0) {
            var cursor = 0
            while (remaining > 0) {
                units[cursor % count] += 1
                cursor += 1
                remaining -= 1
            }
            return units.map { it * 100 }
        }

        val raw = weights.map { remaining * it / totalWeight }
        val floors = raw.map { floor(it).toInt() }
        floors.forEachIndexed { index, value -> units[index] += value }
        var leftover = totalUnits - units.sum()
        val order = raw.indices.sortedByDescending { raw[it] - floor(raw[it]) }
        var cursor = 0
        while (leftover > 0) {
            units[order[cursor % order.size]] += 1
            cursor += 1
            leftover -= 1
        }
        return units.map { it * 100 }
    }

    private fun trifectaProbabilities(race: RaceData, learning: LearningProfile): Map<String, Double> {
        val racers = race.racers.sortedBy { it.lane }
        if (racers.size != 6 || racers.map { it.lane } != (1..6).toList()) return emptyMap()
        val base = racers.map { featureRow(race, it, learning) }
        val firstProbabilities = probabilities(base, first, emptySet())
        if (firstProbabilities.size != 6) return emptyMap()

        val result = linkedMapOf<String, Double>()
        for (firstIndex in 0 until 6) {
            val secondRows = secondRows(base, firstIndex)
            val secondProbabilities = probabilities(secondRows, second, setOf(firstIndex))
            for (secondIndex in 0 until 6) {
                if (secondIndex == firstIndex) continue
                val thirdRows = thirdRows(base, firstIndex, secondIndex)
                val thirdProbabilities = probabilities(thirdRows, third, setOf(firstIndex, secondIndex))
                for (thirdIndex in 0 until 6) {
                    if (thirdIndex == firstIndex || thirdIndex == secondIndex) continue
                    result["${firstIndex + 1}-${secondIndex + 1}-${thirdIndex + 1}"] =
                        firstProbabilities[firstIndex] * secondProbabilities[secondIndex] * thirdProbabilities[thirdIndex]
                }
            }
        }
        val total = result.values.sum()
        return if (total > 0.0) result.mapValues { it.value / total } else emptyMap()
    }

    private fun featureRow(race: RaceData, racer: Racer, learning: LearningProfile): DoubleArray {
        val lane = racer.lane
        val course = racer.preview?.course?.takeIf { it in 1..6 } ?: lane
        val national = racer.nationalWinRate
        val local = racer.localWinRate
        val motor = racer.motorTop2
        val boat = racer.boatTop2
        val avgStart = racer.averageStart
        val exhibition = racer.preview?.exhibitionTime
        val previewStart = racer.preview?.startTiming
        val wind = race.preview?.windSpeed ?: 0
        val wave = race.preview?.waveHeight ?: 0

        val values = mutableListOf<Double>()
        values += (national ?: 5.0).coerceIn(0.0, 10.0)
        values += (local ?: 5.0).coerceIn(0.0, 10.0)
        values += (motor ?: 30.0).coerceIn(0.0, 100.0)
        values += (boat ?: 30.0).coerceIn(0.0, 100.0)
        values += (avgStart ?: 0.18).coerceIn(0.0, 0.50)
        values += (exhibition ?: 6.90).coerceIn(6.0, 8.0)
        values += (previewStart ?: 0.18).coerceIn(-0.20, 0.60)
        values += learning.bonus(race, racer)
        for (value in 1..6) values += if (lane == value) 1.0 else 0.0
        for (value in 1..6) values += if (course == value) 1.0 else 0.0
        values += if (course != lane) 1.0 else 0.0
        values += wind.toDouble() * if (lane == 1) 1.0 else 0.0
        values += wind.toDouble() * if (lane >= 4) 1.0 else 0.0
        values += wave.toDouble() * if (lane == 1) 1.0 else 0.0
        values += wave.toDouble() * if (lane >= 4) 1.0 else 0.0
        values += if (national == null) 1.0 else 0.0
        values += if (local == null) 1.0 else 0.0
        values += if (motor == null) 1.0 else 0.0
        values += if (boat == null) 1.0 else 0.0
        values += if (avgStart == null) 1.0 else 0.0
        values += if (exhibition == null) 1.0 else 0.0
        values += if (previewStart == null) 1.0 else 0.0
        return values.toDoubleArray()
    }

    private fun secondRows(base: List<DoubleArray>, firstIndex: Int): List<DoubleArray> {
        val firstValues = base[firstIndex]
        return (0 until 6).map { candidate ->
            val values = base[candidate].toMutableList()
            for (index in 0 until 8) values += base[candidate][index] - firstValues[index]
            for (index in 0 until 6) values += if (firstIndex == index) 1.0 else 0.0
            val delta = candidate - firstIndex
            values += delta / 5.0
            values += abs(delta) / 5.0
            values += if (candidate < firstIndex) 1.0 else 0.0
            values += if (candidate > firstIndex) 1.0 else 0.0
            values.toDoubleArray()
        }
    }

    private fun thirdRows(base: List<DoubleArray>, firstIndex: Int, secondIndex: Int): List<DoubleArray> {
        val firstValues = base[firstIndex]
        val secondValues = base[secondIndex]
        val low = minOf(firstIndex, secondIndex)
        val high = maxOf(firstIndex, secondIndex)
        return (0 until 6).map { candidate ->
            val values = base[candidate].toMutableList()
            for (index in 0 until 8) values += base[candidate][index] - firstValues[index]
            for (index in 0 until 8) values += base[candidate][index] - secondValues[index]
            for (index in 0 until 6) values += if (firstIndex == index) 1.0 else 0.0
            for (index in 0 until 6) values += if (secondIndex == index) 1.0 else 0.0
            val deltaFirst = candidate - firstIndex
            val deltaSecond = candidate - secondIndex
            values += deltaFirst / 5.0
            values += abs(deltaFirst) / 5.0
            values += deltaSecond / 5.0
            values += abs(deltaSecond) / 5.0
            values += if (candidate in (low + 1) until high) 1.0 else 0.0
            values.toDoubleArray()
        }
    }

    private fun probabilities(
        rows: List<DoubleArray>,
        section: ModelSection,
        excluded: Set<Int>
    ): DoubleArray {
        if (rows.size != 6) return DoubleArray(0)
        val logits = DoubleArray(6) { index ->
            if (index in excluded) {
                -1.0e9
            } else {
                val row = rows[index]
                if (row.size != section.mean.size || section.std.size != row.size || section.weights.size != row.size) {
                    return DoubleArray(0)
                }
                var value = 0.0
                for (feature in row.indices) {
                    value += ((row[feature] - section.mean[feature]) / section.std[feature]) * section.weights[feature]
                }
                value
            }
        }
        val validMax = logits.filterIndexed { index, _ -> index !in excluded }.maxOrNull() ?: return DoubleArray(0)
        val exps = DoubleArray(6) { index ->
            if (index in excluded) 0.0 else exp((logits[index] - validMax).coerceIn(-40.0, 40.0))
        }
        val total = exps.sum()
        if (total <= 0.0) return DoubleArray(0)
        return DoubleArray(6) { exps[it] / total }
    }

    companion object {
        private const val ASSET_NAME = "value_strategy_model.json"

        fun load(context: Context): ValueStrategyModel? = runCatching {
            fromJson(context.assets.open(ASSET_NAME).bufferedReader().use { it.readText() })
        }.getOrNull()

        internal fun fromJson(text: String): ValueStrategyModel {
            val root = JSONObject(text)
            val configJson = root.getJSONObject("strategy")
            val config = ValueStrategyConfig(
                alpha = configJson.getDouble("alpha"),
                minEv = configJson.getDouble("minEv"),
                minProbability = configJson.getDouble("minProbability"),
                maxOdds = configJson.getDouble("maxOdds"),
                maxPoints = configJson.getInt("maxPoints").coerceIn(1, 10),
                allocationMode = configJson.getString("allocationMode"),
                budget = configJson.optInt("budget", BetStrategy.DEFAULT_BUDGET)
            )
            fun section(name: String): ModelSection {
                val obj = root.getJSONObject(name)
                return ModelSection(
                    mean = obj.getJSONArray("mean").doubleArray(),
                    std = obj.getJSONArray("std").doubleArray(),
                    weights = obj.getJSONArray("weights").doubleArray()
                )
            }
            ValueStrategyModel(
                trainedThrough = root.getString("trainedThrough"),
                config = config,
                first = section("first"),
                second = section("second"),
                third = section("third")
            )
        }

        private fun JSONArray.doubleArray(): DoubleArray = DoubleArray(length()) { index -> getDouble(index) }
    }
}
