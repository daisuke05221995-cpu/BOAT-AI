package jp.boatai.app

import android.content.Context
import java.time.LocalDate

/** Coordinates the released Model A forecast and its live recommendation probability source. */
internal object ModelAProduction {
    @Volatile private var runtime: ModelAAssetRuntime? = null

    fun install(context: Context) {
        runtime = ModelAAssetRuntime.load(context.applicationContext)
    }

    fun installed(): Boolean = runtime != null
    fun historyLastDate(): LocalDate? = runtime?.historyLastDate

    /** Full frozen Model A 120-way probabilities. Market odds are never inputs here. */
    fun probabilities(race: RaceData): Map<String, Double>? {
        val result = runtime?.forecast(race) ?: return null
        val forecast = result.forecast ?: return null
        if (forecast.combinations.size != 120 || forecast.probabilities.size != 120) return null
        return forecast.combinations.indices.associate { index ->
            forecast.combinations[index].text to forecast.probabilities[index]
        }
    }

    fun forecast(race: RaceData, maxPicks: Int): List<PredictionPick>? {
        val probabilities = probabilities(race) ?: return null
        val count = maxPicks.coerceIn(1, AverageRoiReferenceStrategy.FORECAST_POINTS)
        return probabilities.entries
            .asSequence()
            .sortedWith(compareByDescending<Map.Entry<String, Double>> { it.value }.thenBy { it.key })
            .take(count)
            .map { (combination, probability) ->
                PredictionPick(
                    combination = combination,
                    score = probability,
                    reason = "Model A 3連単確率 ${"%.1f".format(probability * 100.0)}%"
                )
            }
            .toList()
    }

    fun commitFetchedDay(date: LocalDate, races: List<RaceData>): ModelAHistoryDayUpdater.Summary? =
        runtime?.commitFetchedDay(date, races)
}
