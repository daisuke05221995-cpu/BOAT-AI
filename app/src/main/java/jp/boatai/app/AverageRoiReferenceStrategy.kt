package jp.boatai.app

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.exp
import kotlin.math.max

/**
 * Pure AI finish-order forecast used by v0.15.16.
 *
 * Prediction and purchase selection are intentionally separate. The v0.15.15
 * purchase-value ranking bought 99.5% of usable July-August 2025 races in the
 * sealed-safe diagnostic and returned 68.5% archived-odds ROI, so automatic BUY
 * recommendations are paused instead of being presented as prediction.
 *
 * Forecast probability uses only pre-race racer/form/course information. Odds never
 * change the ordering of forecast picks. A future purchase policy must be validated
 * separately before PURCHASE_RECOMMENDATION_ENABLED can be turned on.
 */
internal object AverageRoiReferenceStrategy {
    const val FORECAST_ENABLED = true
    const val PURCHASE_RECOMMENDATION_ENABLED = false
    const val ENABLED = PURCHASE_RECOMMENDATION_ENABLED
    const val RELEASE_QUALIFIED = false

    // Historical comparison only; neither number is a claim for the v0.15.16 forecast.
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
     * Top trifecta outcomes by the AI model probability only. Official odds are not an
     * input, so favourite/longshot pricing cannot move a combination up or down here.
     */
    internal fun forecast(race: RaceData, maxPicks: Int = FORECAST_POINTS): List<PredictionPick> {
        if (!FORECAST_ENABLED || race.racers.size != 6) return emptyList()
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
                reason = "AI着順確率 ${"%.1f".format(probability * 100.0)}%"
            )
        }.sortedByDescending { it.score }
            .take(maxPicks.coerceIn(1, FORECAST_POINTS))
    }

    /** Automatic purchase policy is deliberately paused after the v0.15.15 audit. */
    internal fun evaluate(
        race: RaceData,
        officialOdds: Map<String, Double>,
        budget: Int = BUDGET
    ): ValueSelection = skip(
        "v0.15.15購入ロジックは過去診断不合格のため自動推奨を停止中。AI予想と手動購入は利用できます"
    )

    private fun skip(detail: String) = ValueSelection(
        picks = emptyList(),
        recommendation = RaceRecommendation.SKIP,
        reason = "購入判定：$detail"
    )
}
