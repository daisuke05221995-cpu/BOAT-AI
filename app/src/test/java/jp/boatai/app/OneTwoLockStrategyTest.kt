package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OneTwoLockStrategyTest {
    @Test
    fun selectsOnlyWhenOneTwoMassReachesSeventyPercent() {
        val eligible = OneTwoLockStrategy.selectionFromProbabilities(probabilities(pairMass = 0.71))!!
        val ineligible = OneTwoLockStrategy.selectionFromProbabilities(probabilities(pairMass = 0.69))!!

        assertTrue(eligible.eligible)
        assertFalse(ineligible.eligible)
        assertEquals(listOf(3, 5, 4), eligible.thirdLanes)
        assertEquals(listOf("1-2-3", "1-2-5", "1-2-4"), eligible.combinations)
    }

    @Test
    fun requiresAllThreeOddsAtLeastThreePointOne() {
        val selection = OneTwoLockStrategy.selectionFromProbabilities(probabilities(pairMass = 0.72))!!
        val ok = OneTwoLockQuote(
            selection = selection,
            odds = mapOf("1-2-3" to 3.1, "1-2-5" to 4.0, "1-2-4" to 5.2)
        )
        val no = ok.copy(odds = mapOf("1-2-3" to 3.0, "1-2-5" to 4.0, "1-2-4" to 5.2))

        assertTrue(ok.purchaseQualified)
        assertFalse(no.purchaseQualified)
    }

    @Test
    fun purchaseUsesEqualStakesAndLeavesRemainderUnused() {
        val selection = OneTwoLockStrategy.selectionFromProbabilities(probabilities(pairMass = 0.72))!!
        val quote = OneTwoLockQuote(
            selection = selection,
            odds = selection.combinations.associateWith { 3.5 }
        )
        val picks = OneTwoLockStrategy.purchasePicks(quote, 1_000)

        assertEquals(3, picks.size)
        assertTrue(picks.all { it.recommendedStake == 300 })
        assertEquals(900, picks.sumOf { it.recommendedStake })
    }

    private fun probabilities(pairMass: Double): Map<String, Double> {
        val pairWeights = linkedMapOf(
            "1-2-3" to 0.40,
            "1-2-5" to 0.25,
            "1-2-4" to 0.20,
            "1-2-6" to 0.15
        )
        val result = linkedMapOf<String, Double>()
        val otherCombinations = mutableListOf<String>()
        for (first in 1..6) {
            for (second in 1..6) {
                if (second == first) continue
                for (third in 1..6) {
                    if (third == first || third == second) continue
                    val combination = "$first-$second-$third"
                    if (combination !in pairWeights) otherCombinations += combination
                }
            }
        }
        pairWeights.forEach { (combination, weight) -> result[combination] = pairMass * weight }
        val remainder = (1.0 - pairMass) / otherCombinations.size
        otherCombinations.forEach { result[it] = remainder }
        return result
    }
}
