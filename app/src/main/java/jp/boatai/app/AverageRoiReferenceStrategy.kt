package jp.boatai.app

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.sqrt

/**
 * Model A forecast plus live-odds purchase recommendation boundary.
 *
 * Forecast ordering remains completely market-free. Purchase recommendations are
 * evaluated separately, only after current official trifecta odds are available.
 * Historical final-like odds are not used to qualify this live policy and no
 * historical realized ROI claim is made for it.
 */
internal object AverageRoiReferenceStrategy {
    const val FORECAST_ENABLED = true
    const val PURCHASE_RECOMMENDATION_ENABLED = true
    const val ENABLED = PURCHASE_RECOMMENDATION_ENABLED
    const val RELEASE_QUALIFIED = false
    const val MODEL_A_FORECAST_RELEASE_QUALIFIED = true

    // Historical comparison only; neither number is a claim for the current forecast/purchase policy.
    const val HISTORICAL_ROI = 117.3
    const val HISTORICAL_PURCHASES = 2_407
    const val HISTORICAL_HITS = 45
    const val HISTORICAL_ROI_APPLIES_TO_CURRENT = false

    const val BUDGET = 3_000
    const val FORECAST_POINTS = 4
    const val MIN_PURCHASE_POINTS = 4
    const val MAX_PURCHASE_POINTS = 8
    private const val MIN_BUDGET = 1_000
    private const val MAX_BUDGET = 3_000
    private const val STAKE_STEP = 100
    private const val UTILITY_BANKROLL = 30_000.0
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

    /** Re-evaluate on every live-odds refresh so a stale recommendation is not frozen. */
    fun evaluateAndCache(
        race: RaceData,
        officialOdds: Map<String, Double>,
        budget: Int = BUDGET
    ): ValueSelection {
        val evaluated = evaluate(race, officialOdds, budget)
        selections[race.id] = evaluated
        return evaluated
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

    /** Top trifecta outcomes by AI probability only. Odds never change forecast ordering. */
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

    internal fun evaluate(
        race: RaceData,
        officialOdds: Map<String, Double>,
        budget: Int = BUDGET
    ): ValueSelection {
        if (!PURCHASE_RECOMMENDATION_ENABLED) return skip("購入推奨は停止中")
        if (race.racers.size != 6) return skip("6艇分の出走データが揃っていません")
        if (officialOdds.count { it.value.isFinite() && it.value > 0.0 } < 120) {
            return skip("公式3連単120通りのライブオッズ取得を待っています")
        }
        val probabilities = ModelAProduction.probabilities(race)
            ?: return skip("Model Aのライブ確率を計算できないため安全側で見送り")
        return evaluateProbabilities(probabilities, officialOdds, budget)
    }

    /** Pure recommendation core, kept independent for deterministic unit tests. */
    internal fun evaluateProbabilities(
        probabilities: Map<String, Double>,
        officialOdds: Map<String, Double>,
        budget: Int = BUDGET
    ): ValueSelection {
        if (probabilities.size != 120 || combinations.any { (probabilities[it] ?: 0.0) <= 0.0 }) {
            return skip("Model Aの120通り確率が揃っていません")
        }
        if (combinations.any { (officialOdds[it] ?: 0.0) <= 0.0 }) {
            return skip("公式3連単120通りのライブオッズが揃っていません")
        }

        val maxBudget = budget.coerceIn(MIN_BUDGET, MAX_BUDGET) / 100 * 100
        val firstMarginal = DoubleArray(6)
        combinations.forEach { combo ->
            val lane = combo.substringBefore('-').toInt() - 1
            firstMarginal[lane] += probabilities.getValue(combo)
        }
        val laneOrder = (0 until 6).sortedByDescending { firstMarginal[it] }
        val primaryLane = laneOrder[0] + 1
        val secondLane = laneOrder[1] + 1
        val primaryP = firstMarginal[laneOrder[0]]
        val secondP = firstMarginal[laneOrder[1]]

        fun rankingScore(combo: String): Double {
            val p = probabilities.getValue(combo)
            val odds = officialOdds.getValue(combo)
            val edge = p * odds
            val valueFactor = sqrt(edge.coerceIn(0.55, 1.75))
            return p * valueFactor
        }

        val byLane = (1..6).associateWith { lane ->
            combinations.filter { it.startsWith("$lane-") }
                .sortedWith(
                    compareByDescending<String> { rankingScore(it) }
                        .thenByDescending { probabilities.getValue(it) }
                        .thenBy { combinations.indexOf(it) }
                )
        }

        val target = targetConditionalCoverage(primaryP)
        val primaryRank = byLane.getValue(primaryLane)
        var points = MAX_PURCHASE_POINTS
        for (candidate in MIN_PURCHASE_POINTS..MAX_PURCHASE_POINTS) {
            val coverage = primaryRank.take(candidate).sumOf { probabilities.getValue(it) } / primaryP.coerceAtLeast(1e-12)
            if (coverage >= target) {
                points = candidate
                break
            }
        }

        var alternativeCount = 0
        if (primaryP < 0.48 && secondP >= 0.25) alternativeCount = 1
        if (primaryP < 0.40 && secondP >= 0.30) alternativeCount = 2
        alternativeCount = alternativeCount.coerceAtMost((points - MIN_PURCHASE_POINTS).coerceAtLeast(0))

        val selected = mutableListOf<String>()
        selected += primaryRank.take(points - alternativeCount)
        selected += byLane.getValue(secondLane).take(alternativeCount)
        val ordered = selected.distinct().sortedWith(
            compareByDescending<String> { rankingScore(it) }
                .thenByDescending { probabilities.getValue(it) }
                .thenBy { combinations.indexOf(it) }
        ).toMutableList()
        if (ordered.size < points) {
            combinations.sortedByDescending(::rankingScore).forEach { combo ->
                if (combo !in ordered && ordered.size < points) ordered += combo
            }
        }

        val selectedCombos = ordered.take(points)
        val selectedProbabilities = selectedCombos.map(probabilities::getValue)
        val selectedOdds = selectedCombos.map(officialOdds::getValue)
        val allocation = allocateStakes(selectedProbabilities, selectedOdds, maxBudget)
            ?: return skip("現在オッズでは買わない方が期待対数効用が高いため見送り")

        val picks = selectedCombos.mapIndexed { index, combo ->
            val p = selectedProbabilities[index]
            val odds = selectedOdds[index]
            PredictionPick(
                combination = combo,
                score = p * odds,
                odds = odds,
                recommendedStake = allocation.stakes[index],
                tier = when {
                    index == 0 && odds < 15.0 -> BetTier.MAIN
                    odds >= 35.0 -> BetTier.LONG
                    else -> BetTier.MID
                },
                reason = "Model A ${"%.1f".format(p * 100.0)}% × ライブオッズ ${"%.1f".format(odds)}倍"
            )
        }

        return ValueSelection(
            picks = picks,
            recommendation = RaceRecommendation.BUY,
            reason = "購入推奨：Model A×現在オッズで期待対数効用がプラス（${picks.size}点 / ${allocation.budget}円 / 推定期待回収率 ${"%.0f".format(allocation.expectedRoi)}%）"
        )
    }

    private data class Allocation(
        val stakes: List<Int>,
        val budget: Int,
        val expectedRoi: Double,
        val utility: Double
    )

    private fun allocateStakes(probabilities: List<Double>, odds: List<Double>, maxBudget: Int): Allocation? {
        if (probabilities.isEmpty() || probabilities.size != odds.size) return null
        val stakes = MutableList(probabilities.size) { STAKE_STEP }
        var best: Allocation? = null
        val noBetUtility = ln(UTILITY_BANKROLL)

        while (stakes.sum() < maxBudget) {
            var bestIndex = -1
            var bestCandidateUtility = Double.NEGATIVE_INFINITY
            for (index in stakes.indices) {
                val candidate = stakes.toMutableList()
                candidate[index] += STAKE_STEP
                val utility = expectedLogUtility(probabilities, odds, candidate)
                if (utility > bestCandidateUtility + 1e-15) {
                    bestCandidateUtility = utility
                    bestIndex = index
                }
            }
            if (bestIndex < 0) break
            stakes[bestIndex] += STAKE_STEP
            val currentBudget = stakes.sum()
            if (currentBudget < MIN_BUDGET) continue

            val expectedReturn = probabilities.indices.sumOf { index ->
                probabilities[index] * odds[index] * stakes[index]
            }
            val expectedRoi = expectedReturn * 100.0 / currentBudget
            val current = Allocation(stakes.toList(), currentBudget, expectedRoi, bestCandidateUtility)
            if (best == null || current.utility > best!!.utility) best = current
        }

        val candidate = best ?: return null
        return candidate.takeIf { it.utility > noBetUtility + 1e-12 && it.expectedRoi > 100.0 }
    }

    private fun expectedLogUtility(probabilities: List<Double>, odds: List<Double>, stakes: List<Int>): Double {
        val budget = stakes.sum().toDouble()
        val baseWealth = UTILITY_BANKROLL - budget
        if (baseWealth <= 0.0) return Double.NEGATIVE_INFINITY
        val selectedProbability = probabilities.sum().coerceIn(0.0, 1.0)
        var utility = (1.0 - selectedProbability) * ln(baseWealth)
        for (index in probabilities.indices) {
            val outcomeWealth = baseWealth + stakes[index] * odds[index]
            if (outcomeWealth <= 0.0) return Double.NEGATIVE_INFINITY
            utility += probabilities[index] * ln(outcomeWealth)
        }
        return utility
    }

    private fun targetConditionalCoverage(firstProbability: Double): Double = when {
        firstProbability >= 0.62 -> 0.49
        firstProbability >= 0.55 -> 0.54
        firstProbability >= 0.48 -> 0.59
        firstProbability >= 0.42 -> 0.64
        else -> 0.68
    }

    private fun skip(detail: String) = ValueSelection(
        picks = emptyList(),
        recommendation = RaceRecommendation.SKIP,
        reason = "購入判定：$detail"
    )
}
