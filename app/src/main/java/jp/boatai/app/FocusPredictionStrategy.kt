package jp.boatai.app

import kotlin.math.sqrt

enum class FocusMode(
    val label: String,
    val optionCount: Int,
    val maxTickets: Int,
    val strategyId: String
) {
    FOUR("フォーカス4択", 4, 18, "focus-4-v1"),
    FIVE("フォーカス5択", 5, 24, "focus-5-v1")
}

data class FocusPattern(
    val notation: String,
    val combinations: List<String>,
    val probabilityMass: Double,
    val reciprocal: Boolean
)

data class FocusSelection(
    val mode: FocusMode,
    val patterns: List<FocusPattern>,
    val combinations: List<String>,
    val coverageProbability: Double
) {
    val minimumStake: Int get() = combinations.size * 100
}

/**
 * Keirin-style grouped focus layer on top of the frozen, market-free Model A probabilities.
 *
 * This object does not change Model A and does not use odds to rank the focus patterns.
 * A focus option is a compact expression such as `1⇔2 / 3着 3・4・5`; the actual
 * purchase candidates are the expanded trifecta combinations behind those expressions.
 */
object FocusPredictionStrategy {
    fun selection(race: RaceData, mode: FocusMode): FocusSelection? {
        val probabilities = ModelAProduction.probabilities(race) ?: return null
        return selectionFromProbabilities(probabilities, mode)
    }

    fun purchasePicks(
        race: RaceData,
        mode: FocusMode,
        budget: Int = BetStrategy.DEFAULT_BUDGET
    ): List<PredictionPick> {
        val probabilities = ModelAProduction.probabilities(race) ?: return emptyList()
        val selection = selectionFromProbabilities(probabilities, mode) ?: return emptyList()
        return purchasePicksFromProbabilities(selection, probabilities, budget)
    }

    internal fun selectionFromProbabilities(
        probabilities: Map<String, Double>,
        mode: FocusMode
    ): FocusSelection? {
        val all = allCombinations()
        if (probabilities.size != 120 || all.any { (probabilities[it] ?: 0.0) <= 0.0 }) return null

        val candidates = mutableListOf<FocusPattern>()

        // Fixed first/second focus: A→B, third place spread across the strongest three lanes.
        for (first in 1..6) {
            for (second in 1..6) {
                if (first == second) continue
                val thirds = (1..6)
                    .filter { it != first && it != second }
                    .sortedByDescending { third -> probabilities.getValue("$first-$second-$third") }
                    .take(3)
                val combinations = thirds.map { third -> "$first-$second-$third" }
                candidates += FocusPattern(
                    notation = "$first→$second / 3着 ${thirds.joinToString("・")}",
                    combinations = combinations,
                    probabilityMass = combinations.sumOf(probabilities::getValue),
                    reciprocal = false
                )
            }
        }

        // Reciprocal pair focus: A⇔B, strongest three third-place lanes across both orders.
        for (first in 1..6) {
            for (second in (first + 1)..6) {
                if (second > 6) continue
                val thirds = (1..6)
                    .filter { it != first && it != second }
                    .sortedByDescending { third ->
                        probabilities.getValue("$first-$second-$third") +
                            probabilities.getValue("$second-$first-$third")
                    }
                    .take(3)
                val combinations = thirds.flatMap { third ->
                    listOf("$first-$second-$third", "$second-$first-$third")
                }
                candidates += FocusPattern(
                    notation = "$first⇔$second / 3着 ${thirds.joinToString("・")}",
                    combinations = combinations,
                    probabilityMass = combinations.sumOf(probabilities::getValue),
                    reciprocal = true
                )
            }
        }

        val baseOrder = candidates.sortedWith(
            compareByDescending<FocusPattern> { quality(it) }
                .thenByDescending { it.probabilityMass }
                .thenBy { it.notation }
        )

        val selected = mutableListOf<FocusPattern>()
        val covered = linkedSetOf<String>()
        val maxReciprocal = if (mode == FocusMode.FOUR) 2 else 3

        while (selected.size < mode.optionCount) {
            val next = baseOrder
                .asSequence()
                .filter { it !in selected }
                .filter { candidate ->
                    if (candidate.reciprocal && selected.count { it.reciprocal } >= maxReciprocal) return@filter false
                    (covered + candidate.combinations).size <= mode.maxTickets
                }
                .maxByOrNull { candidate ->
                    val overlap = candidate.combinations.count { it in covered }.toDouble() / candidate.combinations.size
                    quality(candidate) * (1.0 - overlap * 0.60)
                } ?: break
            selected += next
            covered += next.combinations
        }

        // The cap can occasionally make the greedy pass stop early. Fill with compact
        // fixed-order groups so the UI still has exactly four/five options when possible.
        if (selected.size < mode.optionCount) {
            baseOrder.asSequence()
                .filter { !it.reciprocal && it !in selected }
                .forEach { candidate ->
                    if (selected.size >= mode.optionCount) return@forEach
                    val expanded = linkedSetOf<String>().apply {
                        addAll(covered)
                        addAll(candidate.combinations)
                    }
                    if (expanded.size <= mode.maxTickets) {
                        selected += candidate
                        covered += candidate.combinations
                    }
                }
        }

        if (selected.size != mode.optionCount || covered.isEmpty()) return null
        val orderedCombinations = covered.sortedWith(
            compareByDescending<String> { probabilities.getValue(it) }.thenBy { it }
        )
        return FocusSelection(
            mode = mode,
            patterns = selected,
            combinations = orderedCombinations,
            coverageProbability = orderedCombinations.sumOf(probabilities::getValue).coerceIn(0.0, 1.0)
        )
    }

    internal fun purchasePicksFromProbabilities(
        selection: FocusSelection,
        probabilities: Map<String, Double>,
        budget: Int
    ): List<PredictionPick> {
        val normalizedBudget = (budget.coerceIn(BetStrategy.MIN_BUDGET, BetStrategy.MAX_BUDGET) / 100) * 100
        if (selection.combinations.isEmpty() || selection.minimumStake > normalizedBudget) return emptyList()

        val ordered = selection.combinations.sortedWith(
            compareByDescending<String> { probabilities[it] ?: 0.0 }.thenBy { it }
        )
        val stakes = ordered.associateWith { 100 }.toMutableMap()
        var remaining = normalizedBudget - ordered.size * 100
        var index = 0
        while (remaining >= 100 && ordered.isNotEmpty()) {
            val combination = ordered[index % ordered.size]
            stakes[combination] = stakes.getValue(combination) + 100
            remaining -= 100
            index++
        }

        return ordered.map { combination ->
            val probability = probabilities.getValue(combination)
            PredictionPick(
                combination = combination,
                score = probability,
                recommendedStake = stakes.getValue(combination),
                tier = when {
                    probability >= 0.08 -> BetTier.MAIN
                    probability >= 0.035 -> BetTier.MID
                    else -> BetTier.LONG
                },
                reason = "${selection.mode.label} / Model A確率 ${"%.1f".format(probability * 100.0)}%"
            )
        }
    }

    private fun quality(pattern: FocusPattern): Double =
        pattern.probabilityMass / sqrt(pattern.combinations.size.toDouble())

    private fun allCombinations(): List<String> = buildList(120) {
        for (first in 1..6) {
            for (second in 1..6) {
                if (second == first) continue
                for (third in 1..6) {
                    if (third == first || third == second) continue
                    add("$first-$second-$third")
                }
            }
        }
    }
}
