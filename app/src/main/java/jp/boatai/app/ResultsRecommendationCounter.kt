package jp.boatai.app

internal data class RecommendedResultCount(val recommended: Int, val hits: Int)

/**
 * The results screen reports only real, pre-result BUY decisions.
 * Retrospective Model A predictions and SKIP decisions are never part of these counts.
 */
internal object ResultsRecommendationCounter {
    fun count(results: List<RaceData>, livePredictionsByRace: Map<String, PredictionRecord>): RecommendedResultCount {
        val recommendedRaces = results.filter { race ->
            race.hasResult && livePredictionsByRace[race.id]?.let {
                it.evaluationEligible && it.recommended && it.strategyId != ModelARecentVirtualRepository.STRATEGY_ID
            } == true
        }
        return RecommendedResultCount(
            recommended = recommendedRaces.size,
            hits = recommendedRaces.count { race -> isHit(race, livePredictionsByRace[race.id]) }
        )
    }

    fun isHit(race: RaceData, prediction: PredictionRecord?): Boolean =
        prediction != null && prediction.evaluationEligible && prediction.recommended &&
            prediction.strategyId != ModelARecentVirtualRepository.STRATEGY_ID &&
            race.result?.trifectaCombination?.let { it in prediction.combinations } == true
}
