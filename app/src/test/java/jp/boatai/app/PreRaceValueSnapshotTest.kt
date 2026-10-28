package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PreRaceValueSnapshotTest {
    private fun pick(combo: String, probability: Double?) =
        PredictionPick(combination = combo, score = 0.0, aiProbability = probability)

    @Test
    fun expectedRoiMatchesStakeWeightedProbabilityTimesLiveOdds() {
        val evidence = PreRaceValueEvidence.fromPicks(
            listOf(pick("1-2-3", 0.1), pick("1-3-2", 0.05)),
            listOf(10.0, 30.0),
            listOf(100, 300)
        )!!
        assertEquals(listOf(0.1, 0.05), evidence.pickProbabilities)
        assertEquals(137.5, evidence.expectedRoiPercent, 1e-10)
    }

    @Test
    fun missingOrInvalidInputsNeverInventProbabilityEvidence() {
        val picks = listOf(pick("1-2-3", 0.2), pick("1-3-2", null))
        assertNull(PreRaceValueEvidence.fromPicks(picks, listOf(10.0, 20.0), listOf(100, 100)))
        assertNull(PreRaceValueEvidence.fromPicks(listOf(pick("1-2-3", 0.2)), emptyList(), listOf(100)))
        assertNull(PreRaceValueEvidence.fromPicks(listOf(pick("1-2-3", 0.2)), listOf(10.0), listOf(150)))
        assertNull(PreRaceValueEvidence.fromPicks(
            listOf(pick("1-2-3", 0.8), pick("1-3-2", 0.6)),
            listOf(10.0, 20.0), listOf(100, 100)
        ))
        assertNull(PreRaceValueEvidence.fromPicks(listOf(pick("1-2-3", 0.2)), listOf(Double.NaN), listOf(100)))
    }
}
