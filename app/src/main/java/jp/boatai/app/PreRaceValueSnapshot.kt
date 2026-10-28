package jp.boatai.app

/**
 * Immutable numerical evidence to accompany a pre-race BUY decision.
 *
 * This is an observation-only calculation. It must not alter BUY/SKIP, picks,
 * allocations or the underlying frozen Model A forecast.
 */
internal data class PreRaceValueSnapshot(
    val pickProbabilities: List<Double>,
    val expectedRoiPercent: Double
)

internal object PreRaceValueEvidence {
    fun fromPicks(
        picks: List<PredictionPick>,
        pickOdds: List<Double>,
        stakes: List<Int>
    ): PreRaceValueSnapshot? {
        if (picks.isEmpty() || picks.size != pickOdds.size || picks.size != stakes.size) return null
        val probabilities = picks.map { it.aiProbability ?: return null }
        if (probabilities.any { !it.isFinite() || it <= 0.0 || it > 1.0 }) return null
        if (probabilities.sum() > 1.0 + 1e-6) return null
        if (pickOdds.any { !it.isFinite() || it <= 0.0 }) return null
        if (stakes.any { it < 100 || it % 100 != 0 }) return null
        val budget = stakes.sum().toDouble()
        if (budget <= 0.0) return null
        val expectedPayout = probabilities.indices.sumOf { index ->
            probabilities[index] * pickOdds[index] * stakes[index]
        }
        val expectedRoiPercent = 100.0 * expectedPayout / budget
        if (!expectedRoiPercent.isFinite() || expectedRoiPercent <= 0.0) return null
        return PreRaceValueSnapshot(probabilities, expectedRoiPercent)
    }
}
