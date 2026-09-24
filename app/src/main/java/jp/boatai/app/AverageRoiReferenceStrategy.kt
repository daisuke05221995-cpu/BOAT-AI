package jp.boatai.app

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.exp
import kotlin.math.max

/**
 * Forecast/purchase separation boundary.
 *
 * v0.16 uses the independently validated, market-free Model A whenever its frozen
 * assets and prior-day history are available. The v0.15.16 Plackett-Luce forecaster
 * remains a fail-safe for missing/stale assets or historical-date views.
 *
 * Automatic BUY remains disabled: the archived historical odds could not be proven
 * to be a realizable pre-close snapshot, so forecast quality does not promote a
 * purchase policy.
 */
internal object AverageRoiReferenceStrategy {
    const val FORECAST_ENABLED = true
    const val PURCHASE_RECOMMENDATION_ENABLED = false
    const val ENABLED = PURCHASE_RECOMMENDATION_ENABLED
    const val RELEASE_QUALIFIED = false
    const val MODEL_A_FORECAST_RELEASE_QUALIFIED = true

    // Historical comparison only; neither number is a claim for the current forecast.
    const val HISTORICAL_ROI = 117.3
    const val HISTORICAL_PURCHASES = 2_407
    const val HISTORICAL_HITS = 45
    const val HISTORICAL_ROI_APPLIES_TO_CURRENT = false

    const val BUDGET = 1_200
    const val FORECAST_POINTS = 4
    private const val SCORE_TEMPERATURE = 14.0

    private val selections = ConcurrentHashMap<String, ValueSelection>()
    private val combinations = buildList(120) {
        for (first in 1..6) for (second in 1..6) for (third in 1..6) {
            if (first != second && first != third && second != third) add("$first-$second-$third")
        }
    }

    fun allCombinations(): List<String> = combinations
    fun cached(race: RaceData): ValueSelection? = selections[race.id]
    fun clear() = selections.clear()

    fun evaluateAndCache(
        race: RaceData,
        officialOdds: Map<String, Double>,
        budget: Int = BUDGET
    ): ValueSelection = selections.computeIfAbsent(race.id) {
        evaluate(race, officialOdds, budget)
    }

    internal fun formScore(racer: Racer): Double {
        val national = (racer.nationalWinRate ?: 0.0) * 5.2
        val local = (racer.localWinRate ?: 0.0) * 2.6
        val motor = (racer.motorTop2 ?: 0.0) * 0.22
        val boat = (racer.boatTop2 ?: 0.0) * 0.08
        val start = racer.averageStart?.let { max(0.0, (0.22 - it) * 58.0) } ?: 0.0
        val exhibition = racer.preview?.exhibitionTime?.let { max(-5.0, (6.95 - it) * 18.0) } ?: 0.0
        val previewStart = racer.preview?.startTiming?.let { max(-4.0, (0.18 - it) * 32.0) } ?: 0.0
        return national + local + motor + boat + start + exhibition + previewStart
    }

    private fun coursePrior(racer: Racer): Double {
        val course = racer.preview?.course ?: racer.lane
        return when (course) {
            1 -> 8.0
            2 -> 4.0
            3 -> 2.0
            4 -> 0.0
            5 -> -1.5
            6 -> -3.0
            else -> 0.0
        }
    }

    /**
     * Top trifecta outcomes by AI probability only. Odds never change ordering.
     * Model A is preferred; the prior v0.15.16 formula is a fail-safe only.
     */
    internal fun forecast(race: RaceData, maxPicks: Int = FORECAST_POINTS): List<PredictionPick> {
        if (!FORECAST_ENABLED || race.racers.size != 6) return emptyList()
        ModelAProduction.forecast(race, maxPicks)?.let { return it }

        val racers = race.racers.associateBy { it.lane }
        val rawScores = (1..6).associateWith { lane ->
            val racer = racers[lane] ?: return@associateWith Double.NEGATIVE_INFINITY
            formScore(racer) + coursePrior(racer)
        }
        val finiteScores = rawScores.values.filter { it.isFinite() }
        val maxScore = finiteScores.maxOrNull() ?: return emptyList()
        val weights = (1..6).associateWith { lane ->
            val score = rawScores[lane] ?: Double.NEGATIVE_INFINITY
            if (score.isFinite()) exp((score - maxScore) / SCORE_TEMPERATURE) else 0.0
        }
        val weightTotal = weights.values.sum()
        if (weightTotal <= 0.0) return emptyList()

        return combinations.mapNotNull { combo ->
            val lanes = combo.split('-').mapNotNull(String::toIntOrNull)
            if (lanes.size != 3) return@mapNotNull null
            val firstWeight = weights[lanes[0]] ?: 0.0
            val secondWeight = weights[lanes[1]] ?: 0.0
            val thirdWeight = weights[lanes[2]] ?: 0.0
            val secondDenom = weightTotal - firstWeight
            val thirdDenom = secondDenom - secondWeight
            if (firstWeight <= 0.0 || secondDenom <= 0.0 || thirdDenom <= 0.0) return@mapNotNull null
            val probability =
                (firstWeight / weightTotal) *
                    (secondWeight / secondDenom) *
                    (thirdWeight / thirdDenom)
            PredictionPick(
                combination = combo,
                score = probability,
                reason = "互換AI着順確率 ${"%.1f".format(probability * 100.0)}%"
            )
        }.sortedByDescending { it.score }
            .take(maxPicks.coerceIn(1, FORECAST_POINTS))
    }

    /** Automatic purchase policy remains paused; forecast validation is not ROI validation. */
    internal fun evaluate(
        race: RaceData,
        officialOdds: Map<String, Double>,
        budget: Int = BUDGET
    ): ValueSelection = skip(
        "自動購入は停止中。履歴オッズの締切前時刻を証明できないため、Model A予想と手動購入のみ利用できます"
    )

    private fun skip(detail: String) = ValueSelection(
        picks = emptyList(),
        recommendation = RaceRecommendation.SKIP,
        reason = "購入判定：$detail"
    )
}
