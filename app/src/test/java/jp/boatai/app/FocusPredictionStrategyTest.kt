package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FocusPredictionStrategyTest {
    @Test
    fun focusFourBuildsFourGroupsWithinTicketCap() {
        val selection = FocusPredictionStrategy.selectionFromProbabilities(probabilities(), FocusMode.FOUR)
        assertNotNull(selection)
        selection!!
        assertEquals(4, selection.patterns.size)
        assertTrue(selection.combinations.size <= FocusMode.FOUR.maxTickets)
        assertEquals(selection.combinations.size, selection.combinations.distinct().size)
        assertTrue(selection.combinations.all(::validCombination))
        assertTrue(selection.patterns.any { it.notation.startsWith("1⇔2") })
    }

    @Test
    fun focusFiveBuildsFiveGroupsWithinTicketCap() {
        val selection = FocusPredictionStrategy.selectionFromProbabilities(probabilities(), FocusMode.FIVE)
        assertNotNull(selection)
        selection!!
        assertEquals(5, selection.patterns.size)
        assertTrue(selection.combinations.size <= FocusMode.FIVE.maxTickets)
        assertEquals(selection.combinations.size, selection.combinations.distinct().size)
        assertTrue(selection.coverageProbability in 0.0..1.0)
    }

    @Test
    fun allocationNeverUsesLessThanHundredYenAndKeepsBudget() {
        val probabilities = probabilities()
        val selection = FocusPredictionStrategy.selectionFromProbabilities(probabilities, FocusMode.FOUR)!!
        val budget = 3_000
        val picks = FocusPredictionStrategy.purchasePicksFromProbabilities(selection, probabilities, budget)
        assertEquals(selection.combinations.size, picks.size)
        assertEquals(budget, picks.sumOf { it.recommendedStake })
        assertTrue(picks.all { it.recommendedStake >= 100 && it.recommendedStake % 100 == 0 })
    }

    @Test
    fun insufficientBudgetDoesNotPartiallyBreakAGroupSelection() {
        val probabilities = probabilities()
        val selection = FocusPredictionStrategy.selectionFromProbabilities(probabilities, FocusMode.FIVE)!!
        val tooSmall = (selection.minimumStake - 100).coerceAtLeast(BetStrategy.MIN_BUDGET)
        if (tooSmall < selection.minimumStake) {
            assertTrue(
                FocusPredictionStrategy.purchasePicksFromProbabilities(selection, probabilities, tooSmall).isEmpty()
            )
        }
    }

    private fun probabilities(): Map<String, Double> {
        val raw = linkedMapOf<String, Double>()
        for (first in 1..6) {
            for (second in 1..6) {
                if (second == first) continue
                for (third in 1..6) {
                    if (third == first || third == second) continue
                    val combination = "$first-$second-$third"
                    val weight = when {
                        first == 1 && second == 2 -> 18.0
                        first == 2 && second == 1 -> 14.0
                        first == 1 && second == 3 -> 11.0
                        first == 1 && second == 4 -> 9.0
                        first == 2 && second == 3 -> 7.0
                        else -> 1.0
                    } + (7 - third) * 0.01
                    raw[combination] = weight
                }
            }
        }
        val total = raw.values.sum()
        return raw.mapValues { (_, value) -> value / total }
    }

    private fun validCombination(value: String): Boolean {
        val lanes = value.split('-').mapNotNull(String::toIntOrNull)
        return lanes.size == 3 && lanes.all { it in 1..6 } && lanes.toSet().size == 3
    }
}
