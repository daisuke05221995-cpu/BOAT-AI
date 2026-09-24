package jp.boatai.app

import android.content.Context
import java.time.LocalDate

/** Coordinates the released forecast-only Model A without enabling any purchase policy. */
internal object ModelAProduction {
    @Volatile private var runtime: ModelAAssetRuntime? = null

    fun install(context: Context) {
        runtime = ModelAAssetRuntime.load(context.applicationContext)
    }

    fun installed(): Boolean = runtime != null
    fun historyLastDate(): LocalDate? = runtime?.historyLastDate

    fun forecast(race: RaceData, maxPicks: Int): List<PredictionPick>? {
        val result = runtime?.forecast(race) ?: return null
        val forecast = result.forecast ?: return null
        val count = maxPicks.coerceIn(1, AverageRoiReferenceStrategy.FORECAST_POINTS)
        return forecast.combinations.indices
            .asSequence()
            .map { index -> index to forecast.probabilities[index] }
            .sortedWith(compareByDescending<Pair<Int, Double>> { it.second }.thenBy { it.first })
            .take(count)
            .map { (index, probability) ->
                PredictionPick(
                    combination = forecast.combinations[index].text,
                    score = probability,
                    reason = "Model A 3連単確率 ${"%.1f".format(probability * 100.0)}%"
                )
            }
            .toList()
    }

    fun commitFetchedDay(date: LocalDate, races: List<RaceData>): ModelAHistoryDayUpdater.Summary? =
        runtime?.commitFetchedDay(date, races)
}
