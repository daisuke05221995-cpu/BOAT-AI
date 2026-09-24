package jp.boatai.app

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.exp
import kotlin.math.ln

/**
 * Reference-only live approximation of the frozen 2026 v12 operating policy.
 *
 * Historical development evidence (2026-05..09): 2,407 purchase races, 45 hits,
 * combined ROI 117.3%, four positive months out of five, worst month ROI 94.7%.
 * The original research model did NOT pass independent multi-year validation, so this
 * strategy is deliberately labelled reference-only and MUST NOT be described as a
 * production-qualified or profit-guaranteed model.
 *
 * The historical model was a monthly conditional finish-order model. Android does not
 * ship those monthly learned weights, therefore the model probability below is a
 * transparent live approximation derived from the current BOAT AI racer scores. The
 * historical v12 market blend and ticket gate themselves are kept frozen:
 * alpha=0.25, minEV=1.05, minProbability=0.005, maxOdds=150, maxPoints=2, equal stake.
 */
internal object AverageRoiReferenceStrategy {
    const val ENABLED = true
    const val RELEASE_QUALIFIED = false
    const val HISTORICAL_ROI = 117.3
    const val HISTORICAL_PURCHASES = 2_407
    const val HISTORICAL_HITS = 45
    const val POSITIVE_MONTHS = 4
    const val TOTAL_MONTHS = 5
    const val WORST_MONTH_ROI = 94.7

    const val BUDGET = 1_200
    const val MAX_POINTS = 2
    const val ALPHA = 0.25
    const val MIN_EV = 1.05
    const val MIN_PROBABILITY = 0.005
    const val MAX_ODDS = 150.0

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
        val rawScores = (1..6).associateWith { lane ->
            racers[lane]?.let(PredictionEngine::racerScore) ?: 0.0
        }
        val maxScore = rawScores.values.maxOrNull() ?: 0.0
        val weights = (1..6).associateWith { lane ->
            exp(((rawScores[lane] ?: 0.0) - maxScore) / 18.0)
        }
        val weightTotal = weights.values.sum()
        if (weightTotal <= 0.0) return skip("AI確率を計算できません")

        data class BlendRow(
            val combination: String,
            val odds: Double,
            val rawBlend: Double
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

                val rawBlend = exp(
                    ALPHA * ln(modelProbability.coerceAtLeast(1e-12)) +
                        (1.0 - ALPHA) * ln(marketProbability.coerceAtLeast(1e-12))
                )
                add(BlendRow(combo, odds, rawBlend))
            }
        }
        val blendTotal = rows.sumOf { it.rawBlend }
        if (blendTotal <= 0.0) return skip("AIと市場の混合確率を計算できません")

        data class Candidate(
            val combination: String,
            val probability: Double,
            val odds: Double,
            val ev: Double
        )

        val selected = rows.mapNotNull { row ->
            val probability = row.rawBlend / blendTotal
            val ev = probability * row.odds
            if (row.odds > MAX_ODDS || probability < MIN_PROBABILITY || ev < MIN_EV) {
                null
            } else {
                Candidate(row.combination, probability, row.odds, ev)
            }
        }.sortedWith(
            compareByDescending<Candidate> { it.ev }.thenByDescending { it.probability }
        ).take(MAX_POINTS)

        if (selected.isEmpty()) {
            return skip("平均ROI参考条件（EV・確率・オッズ上限）に該当する買い目がありません")
        }

        val stakes = BetStrategy.allocateEvenly(selected.size, budget.coerceIn(1_000, 3_000))
        val picks = selected.mapIndexed { index, candidate ->
            PredictionPick(
                combination = candidate.combination,
                score = candidate.ev,
                odds = candidate.odds,
                recommendedStake = stakes[index],
                tier = when {
                    index == 0 && candidate.odds < 15.0 -> BetTier.MAIN
                    candidate.odds >= 80.0 -> BetTier.LONG
                    else -> BetTier.MID
                },
                reason = "平均ROI参考 α${"%.2f".format(ALPHA)} EV${"%.2f".format(candidate.ev)}"
            )
        }
        return ValueSelection(
            picks = picks,
            recommendation = RaceRecommendation.BUY,
            reason = "参考購入：2026年5〜9月の平均ROI固定条件を現行AIで近似（2,407購入・ROI117.3%、複数年検証は不合格）"
        )
    }

    private fun skip(detail: String) = ValueSelection(
        picks = emptyList(),
        recommendation = RaceRecommendation.SKIP,
        reason = "参考見送り：$detail（平均ROI条件は複数年検証不合格）"
    )
}
