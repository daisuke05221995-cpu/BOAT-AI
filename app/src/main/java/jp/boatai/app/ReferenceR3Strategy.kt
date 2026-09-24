package jp.boatai.app

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.exp

/**
 * Temporary reference operation requested by the user.
 *
 * Historical r3 place-small showed 258.54% ROI in 2024, but only 24 purchases / 3 hits,
 * failed the preregistered annual gate, and was NOT production-qualified. The original
 * research model is quarterly LightGBM and is not executable in the Android runtime.
 * This object therefore applies the frozen r3 betting policy to a transparent live
 * approximation: market-implied 1st-place probability + current BOAT AI conditional
 * 2nd/3rd strength. The historical ROI MUST NOT be attributed to this approximation.
 */
internal object ReferenceR3Strategy {
    const val ENABLED = true
    const val HISTORICAL_ROI = 258.54
    const val HISTORICAL_PURCHASES = 24
    const val HISTORICAL_HITS = 3
    const val BUDGET = 1_200
    const val MAX_POINTS = 3
    const val MIN_EV = 1.10
    const val MIN_PROBABILITY = 0.01
    const val MAX_ODDS = 40.0

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
        if (race.racers.size != 6 || officialOdds.count { it.value > 0.0 } < 100) {
            return skip("公式3連単オッズが十分に取得できていません")
        }
        val inverse = combinations.associateWith { combo ->
            officialOdds[combo]?.takeIf { it > 1.0 }?.let { 1.0 / it } ?: 0.0
        }
        val inverseTotal = inverse.values.sum()
        if (inverseTotal <= 0.0) return skip("公式オッズを確率へ変換できません")

        val firstMarket = DoubleArray(7)
        inverse.forEach { (combo, raw) ->
            val first = combo.substringBefore('-').toIntOrNull() ?: return@forEach
            firstMarket[first] += raw / inverseTotal
        }
        val firstTotal = firstMarket.sum()
        if (firstTotal <= 0.0) return skip("1着市場確率を計算できません")
        for (lane in 1..6) firstMarket[lane] /= firstTotal

        val racers = race.racers.associateBy { it.lane }
        val rawScores = (1..6).associateWith { lane ->
            racers[lane]?.let(PredictionEngine::racerScore) ?: 0.0
        }
        val maxScore = rawScores.values.maxOrNull() ?: 0.0
        val weights = (1..6).associateWith { lane -> exp(((rawScores[lane] ?: 0.0) - maxScore) / 18.0) }

        data class Candidate(val combination: String, val probability: Double, val odds: Double, val ev: Double)
        val candidates = mutableListOf<Candidate>()
        for (combo in combinations) {
            val lanes = combo.split('-').mapNotNull(String::toIntOrNull)
            if (lanes.size != 3) continue
            val (first, second, third) = lanes
            val odds = officialOdds[combo]?.takeIf { it > 1.0 && it <= MAX_ODDS } ?: continue
            val remainingAfterFirst = (1..6).filter { it != first }
            val sumSecond = remainingAfterFirst.sumOf { weights[it] ?: 0.0 }
            if (sumSecond <= 0.0) continue
            val pSecond = (weights[second] ?: 0.0) / sumSecond
            val remainingAfterSecond = remainingAfterFirst.filter { it != second }
            val sumThird = remainingAfterSecond.sumOf { weights[it] ?: 0.0 }
            if (sumThird <= 0.0) continue
            val pThird = (weights[third] ?: 0.0) / sumThird
            val probability = firstMarket[first] * pSecond * pThird
            val ev = probability * odds
            if (probability >= MIN_PROBABILITY && ev >= MIN_EV) {
                candidates += Candidate(combo, probability, odds, ev)
            }
        }
        val selected = candidates.sortedWith(
            compareByDescending<Candidate> { it.ev }.thenByDescending { it.probability }
        ).take(MAX_POINTS)
        if (selected.isEmpty()) return skip("r3参考固定条件に該当する買い目がありません")

        val stakes = BetStrategy.allocateEvenly(selected.size, budget.coerceIn(1_000, 3_000))
        val picks = selected.mapIndexed { index, candidate ->
            PredictionPick(
                combination = candidate.combination,
                score = candidate.ev,
                odds = candidate.odds,
                recommendedStake = stakes[index],
                tier = when {
                    index == 0 && candidate.odds < 15.0 -> BetTier.MAIN
                    candidate.odds >= 35.0 -> BetTier.LONG
                    else -> BetTier.MID
                },
                reason = "r3参考固定条件 EV${"%.2f".format(candidate.ev)}"
            )
        }
        return ValueSelection(
            picks = picks,
            recommendation = RaceRecommendation.BUY,
            reason = "参考購入：r3固定条件を現行確率近似で適用（過去ROI258.5%は24購入・3的中で検証不合格）"
        )
    }

    private fun skip(detail: String) = ValueSelection(
        picks = emptyList(),
        recommendation = RaceRecommendation.SKIP,
        reason = "参考見送り：$detail（r3は検証不合格モデル）"
    )
}
