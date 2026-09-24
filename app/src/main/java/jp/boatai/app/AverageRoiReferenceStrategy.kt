package jp.boatai.app

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.max

/**
 * AI-first live value strategy.
 *
 * v0.15.14 reproduced a research configuration that mixed only 25% model probability
 * with 75% market probability. In the Android approximation that caused excessive
 * favourite/inside-lane following, especially 1-first trifectas. v0.15.15 separates
 * prediction from pricing: finish-order probability is AI-led, while market odds are
 * used to demand a measurable edge and positive expected value.
 *
 * The old 2026-05..09 ROI 117.3% belongs to the previous market-heavy research setup.
 * It is retained only as historical comparison and MUST NOT be presented as the
 * validated ROI of this corrected live strategy.
 */
internal object AverageRoiReferenceStrategy {
    const val ENABLED = true
    const val RELEASE_QUALIFIED = false

    // Historical comparison only (previous v0.15.14 market-heavy configuration).
    const val HISTORICAL_ROI = 117.3
    const val HISTORICAL_PURCHASES = 2_407
    const val HISTORICAL_HITS = 45
    const val POSITIVE_MONTHS = 4
    const val TOTAL_MONTHS = 5
    const val WORST_MONTH_ROI = 94.7
    const val HISTORICAL_ROI_APPLIES_TO_CURRENT = false

    const val BUDGET = 1_200
    const val MAX_POINTS = 2
    const val MODEL_WEIGHT = 0.80
    const val MIN_EV = 1.05
    const val MIN_PROBABILITY = 0.005
    const val MAX_ODDS = 150.0
    const val MIN_MARKET_EDGE_RATIO = 1.08
    const val MAX_FIRST_FORM_RANK = 2
    const val ALT_FIRST_SCORE_RATIO = 0.88

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

    /**
     * Form/ability score deliberately excludes the large static lane prior used by the
     * legacy engine. This is the score used to decide whether a racer deserves to be a
     * first-place candidate on evidence beyond simply drawing an inside lane.
     */
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

    /** Smaller, realistic course prior: course still matters, but cannot dominate form. */
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

    internal fun evaluate(
        race: RaceData,
        officialOdds: Map<String, Double>,
        budget: Int = BUDGET
    ): ValueSelection {
        if (race.racers.size != 6 || officialOdds.count { it.value > 1.0 } < 100) {
            return skip("公式3連単オッズが十分に取得できていません")
        }

        val inverseOdds = combinations.associateWith { combo ->
            officialOdds[combo]?.takeIf { it > 1.0 }?.let { 1.0 / it } ?: 0.0
        }
        val marketTotal = inverseOdds.values.sum()
        if (marketTotal <= 0.0) return skip("公式オッズを市場確率へ変換できません")

        val racers = race.racers.associateBy { it.lane }
        val formScores = (1..6).associateWith { lane ->
            racers[lane]?.let(::formScore) ?: Double.NEGATIVE_INFINITY
        }
        val formRanks = formScores.entries
            .sortedByDescending { it.value }
            .mapIndexed { index, entry -> entry.key to (index + 1) }
            .toMap()

        val rawScores = (1..6).associateWith { lane ->
            val racer = racers[lane] ?: return@associateWith Double.NEGATIVE_INFINITY
            formScore(racer) + coursePrior(racer)
        }
        val finiteScores = rawScores.values.filter { it.isFinite() }
        val maxScore = finiteScores.maxOrNull() ?: return skip("AI確率を計算できません")
        val weights = (1..6).associateWith { lane ->
            val score = rawScores[lane] ?: Double.NEGATIVE_INFINITY
            if (score.isFinite()) exp((score - maxScore) / SCORE_TEMPERATURE) else 0.0
        }
        val weightTotal = weights.values.sum()
        if (weightTotal <= 0.0) return skip("AI確率を計算できません")

        data class BlendRow(
            val combination: String,
            val firstLane: Int,
            val odds: Double,
            val modelProbability: Double,
            val marketProbability: Double,
            val rawForecast: Double
        )

        val rows = buildList(120) {
            for (combo in combinations) {
                val lanes = combo.split('-').mapNotNull(String::toIntOrNull)
                if (lanes.size != 3) continue
                val first = lanes[0]
                val second = lanes[1]
                val third = lanes[2]
                val odds = officialOdds[combo]?.takeIf { it > 1.0 } ?: continue

                val firstWeight = weights[first] ?: 0.0
                val secondWeight = weights[second] ?: 0.0
                val thirdWeight = weights[third] ?: 0.0
                val secondDenom = weightTotal - firstWeight
                val thirdDenom = secondDenom - secondWeight
                if (firstWeight <= 0.0 || secondDenom <= 0.0 || thirdDenom <= 0.0) continue

                val modelProbability =
                    (firstWeight / weightTotal) *
                    (secondWeight / secondDenom) *
                    (thirdWeight / thirdDenom)
                val marketProbability = (inverseOdds[combo] ?: 0.0) / marketTotal
                if (modelProbability <= 0.0 || marketProbability <= 0.0) continue

                val rawForecast = exp(
                    MODEL_WEIGHT * ln(modelProbability.coerceAtLeast(1e-12)) +
                        (1.0 - MODEL_WEIGHT) * ln(marketProbability.coerceAtLeast(1e-12))
                )
                add(BlendRow(combo, first, odds, modelProbability, marketProbability, rawForecast))
            }
        }
        val forecastTotal = rows.sumOf { it.rawForecast }
        if (forecastTotal <= 0.0) return skip("AI予測確率を計算できません")

        data class Candidate(
            val combination: String,
            val firstLane: Int,
            val probability: Double,
            val odds: Double,
            val ev: Double,
            val marketEdgeRatio: Double,
            val rankingScore: Double
        )

        val candidates = rows.mapNotNull { row ->
            // 1着候補は、コース有利を除いた実力・直前状態でも上位2艇にいることを要求。
            if ((formRanks[row.firstLane] ?: 99) > MAX_FIRST_FORM_RANK) return@mapNotNull null

            val probability = row.rawForecast / forecastTotal
            val marketEdgeRatio = row.modelProbability / row.marketProbability
            val ev = probability * row.odds
            if (
                row.odds > MAX_ODDS ||
                probability < MIN_PROBABILITY ||
                ev < MIN_EV ||
                marketEdgeRatio < MIN_MARKET_EDGE_RATIO
            ) {
                null
            } else {
                val rankingScore = ev * marketEdgeRatio.coerceAtMost(2.5)
                Candidate(
                    row.combination,
                    row.firstLane,
                    probability,
                    row.odds,
                    ev,
                    marketEdgeRatio,
                    rankingScore
                )
            }
        }.sortedWith(
            compareByDescending<Candidate> { it.rankingScore }
                .thenByDescending { it.ev }
                .thenByDescending { it.probability }
        )

        if (candidates.isEmpty()) {
            return skip("AIが市場人気を上回る根拠のある買い目がありません")
        }

        val primary = candidates.first()
        val alternateFirst = candidates.drop(1).firstOrNull { candidate ->
            candidate.firstLane != primary.firstLane &&
                candidate.rankingScore >= primary.rankingScore * ALT_FIRST_SCORE_RATIO
        }
        val selected = if (MAX_POINTS <= 1) {
            listOf(primary)
        } else if (alternateFirst != null) {
            listOf(primary, alternateFirst)
        } else {
            candidates.take(MAX_POINTS)
        }

        val stakes = BetStrategy.allocateEvenly(selected.size, budget.coerceIn(1_000, 3_000))
        val picks = selected.mapIndexed { index, candidate ->
            PredictionPick(
                combination = candidate.combination,
                score = candidate.rankingScore,
                odds = candidate.odds,
                recommendedStake = stakes[index],
                tier = when {
                    index == 0 && candidate.odds < 15.0 -> BetTier.MAIN
                    candidate.odds >= 80.0 -> BetTier.LONG
                    else -> BetTier.MID
                },
                reason = "AI主体 市場差+${"%.0f".format((candidate.marketEdgeRatio - 1.0) * 100.0)}% EV${"%.2f".format(candidate.ev)}"
            )
        }
        return ValueSelection(
            picks = picks,
            recommendation = RaceRecommendation.BUY,
            reason = "AI主体予想：コース基礎有利を圧縮し、実力・モーター・ST・展示を主評価。市場より8%以上の上積みがある買い目のみ購入候補"
        )
    }

    private fun skip(detail: String) = ValueSelection(
        picks = emptyList(),
        recommendation = RaceRecommendation.SKIP,
        reason = "AI差分見送り：$detail"
    )
}
