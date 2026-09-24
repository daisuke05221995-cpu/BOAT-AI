package jp.boatai.app

/**
 * Fail-closed runtime boundary for frozen v0.16 forecast-only Model A.
 *
 * This is intentionally separate from PredictionEngine until the final holdout and
 * deployment gates are complete. A stale player-history state never falls back to a
 * silently different Model A feature vector.
 */
internal class ModelAForecastRuntime(
    private val history: ModelAPlayerHistory,
    stage0: LightGbmTextModel,
    stage1: LightGbmTextModel,
    stage2: LightGbmTextModel
) {
    private val featureBuilder = ModelAFeatureBuilder(history)
    private val predictor = ModelAConditionalPredictor(stage0, stage1, stage2, temperature = 1.0)

    data class Result(
        val forecast: ModelAConditionalPredictor.Forecast?,
        val available: Boolean,
        val reason: String?,
        val historyThroughDayOrdinal: Int,
        val predictionDayOrdinal: Int?
    )

    fun forecast(race: RaceData): Result {
        val built = featureBuilder.build(race)
        if (!built.usable || built.input == null) {
            return Result(
                forecast = null,
                available = false,
                reason = built.reason ?: "Model A features unavailable",
                historyThroughDayOrdinal = built.historyThroughDayOrdinal,
                predictionDayOrdinal = built.predictionDayOrdinal
            )
        }
        if (!built.historyFreshForDay) {
            return Result(
                forecast = null,
                available = false,
                reason = "Model A history is not complete through the previous calendar day",
                historyThroughDayOrdinal = built.historyThroughDayOrdinal,
                predictionDayOrdinal = built.predictionDayOrdinal
            )
        }
        return Result(
            forecast = predictor.predict(built.input),
            available = true,
            reason = null,
            historyThroughDayOrdinal = built.historyThroughDayOrdinal,
            predictionDayOrdinal = built.predictionDayOrdinal
        )
    }
}
