package jp.boatai.app

/**
 * Ultra-selective 1→2 strategy.
 *
 * The 90% gate is a Model A estimated probability threshold, not a promise that 90% of
 * future races will finish 1→2. Realized calibration is tracked separately in
 * [OneTwoLockHistoryStore].
 */
data class OneTwoLockSelection(
    val pairProbability: Double,
    val thirdLanes: List<Int>,
    val combinations: List<String>,
    val combinationProbabilities: Map<String, Double>,
    val ticketProbability: Double
) {
    val conditionalThirdCoverage: Double
        get() = if (pairProbability > 0.0) (ticketProbability / pairProbability).coerceIn(0.0, 1.0) else 0.0
    val eligible: Boolean
        get() = pairProbability >= OneTwoLockStrategy.TARGET_PAIR_PROBABILITY
}

data class OneTwoLockQuote(
    val selection: OneTwoLockSelection,
    val odds: Map<String, Double> = emptyMap(),
    val fetchedAt: Long? = null,
    val source: String? = null,
    val error: String? = null
) {
    val oddsComplete: Boolean
        get() = selection.combinations.all { (odds[it] ?: 0.0) > 0.0 }
    val minOdds: Double?
        get() = if (oddsComplete) selection.combinations.minOf { odds.getValue(it) } else null
    val purchaseQualified: Boolean
        get() = selection.eligible && oddsComplete && (minOdds ?: 0.0) >= OneTwoLockStrategy.MIN_ODDS
}

object OneTwoLockStrategy {
    const val STRATEGY_ID = "one-two-lock-v1"
    const val TARGET_PAIR_PROBABILITY = 0.90
    const val MIN_ODDS = 3.10
    const val THIRD_COUNT = 3

    fun selection(race: RaceData): OneTwoLockSelection? {
        val probabilities = ModelAProduction.probabilities(race) ?: return null
        return selectionFromProbabilities(probabilities)
    }

    internal fun selectionFromProbabilities(probabilities: Map<String, Double>): OneTwoLockSelection? {
        val pairCombinations = (3..6).map { third -> "1-2-$third" }
        if (pairCombinations.any { (probabilities[it] ?: 0.0) <= 0.0 }) return null

        val pairProbability = pairCombinations.sumOf { probabilities.getValue(it) }
        val thirdLanes = (3..6)
            .sortedByDescending { third -> probabilities.getValue("1-2-$third") }
            .take(THIRD_COUNT)
        val combinations = thirdLanes.map { third -> "1-2-$third" }
        val selectedProbabilities = combinations.associateWith { probabilities.getValue(it) }
        val ticketProbability = selectedProbabilities.values.sum()
        return OneTwoLockSelection(
            pairProbability = pairProbability.coerceIn(0.0, 1.0),
            thirdLanes = thirdLanes,
            combinations = combinations,
            combinationProbabilities = selectedProbabilities,
            ticketProbability = ticketProbability.coerceIn(0.0, 1.0)
        )
    }

    fun quote(selection: OneTwoLockSelection, result: OddsFetchResult): OneTwoLockQuote =
        OneTwoLockQuote(
            selection = selection,
            odds = result.odds.filterKeys { it in selection.combinations },
            fetchedAt = result.fetchedAt,
            source = result.source
        )

    /**
     * Equal-stake only. With 3 tickets, a winning odds value of 3.1x or higher returns
     * more than the 3-ticket stake regardless of which selected third-place lane hits.
     * Any budget remainder that would make stakes unequal is intentionally left unused.
     */
    fun purchasePicks(quote: OneTwoLockQuote, requestedBudget: Int): List<PredictionPick> {
        if (!quote.purchaseQualified) return emptyList()
        val budget = requestedBudget.coerceIn(BetStrategy.MIN_BUDGET, BetStrategy.MAX_BUDGET)
        val stakeEach = (budget / (THIRD_COUNT * 100)) * 100
        if (stakeEach < 100) return emptyList()

        return quote.selection.combinations.map { combination ->
            PredictionPick(
                combination = combination,
                score = quote.selection.combinationProbabilities[combination] ?: 0.0,
                odds = quote.odds[combination],
                recommendedStake = stakeEach,
                tier = BetTier.MAIN,
                reason = "1→2鉄板候補 / 3点均等 / 最低3.1倍ゲート"
            )
        }
    }
}
