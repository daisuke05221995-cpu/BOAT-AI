package jp.boatai.app

import java.time.LocalDate

/**
 * Applies one fully fetched calendar day's settled results to Model A history.
 *
 * All race feature snapshots are built before history.commitDay() is called, so
 * no race on the day can observe another race result from the same day.
 */
internal class ModelAHistoryDayUpdater(
    private val history: ModelAPlayerHistory
) {
    data class Summary(
        val dayOrdinal: Int,
        val sourceRaces: Int,
        val settledSixBoatRaces: Int,
        val featureUsableRaces: Int,
        val committedRaces: Int,
        val skippedResultRaces: Int,
        val skippedFeatureRaces: Int,
        val historyLastDay: Int
    )

    fun commitFetchedDay(date: LocalDate, races: List<RaceData>): Summary {
        val day = ModelAFeatureBuilder.pythonOrdinal(date)
        require(history.lastDay == day - 1) {
            "Model A history must be continuous through the previous day: last=${history.lastDay}, day=$day"
        }
        require(races.isNotEmpty()) { "Refusing to advance Model A history with an empty day" }
        require(races.all { runCatching { LocalDate.parse(it.date.take(10)) }.getOrNull() == date }) {
            "History day batch contains another calendar date"
        }

        val builder = ModelAFeatureBuilder(history)
        val pending = mutableListOf<ModelAPlayerHistory.OutcomeUpdate>()
        var settledSixBoat = 0
        var featureUsable = 0
        var skippedResult = 0
        var skippedFeature = 0

        for (race in races.sortedWith(compareBy<RaceData> { it.stadiumNumber }.thenBy { it.raceNumber })) {
            val finishOrder = race.result?.finishOrder.orEmpty()
            if (finishOrder.size != 6 || finishOrder.toSet() != (1..6).toSet()) {
                skippedResult += 1
                continue
            }
            settledSixBoat += 1

            val features = builder.build(race)
            if (!features.usable || !features.historyFreshForDay || features.laneHistory.size != 6) {
                skippedFeature += 1
                continue
            }
            featureUsable += 1

            val first = finishOrder[0]
            val top2 = finishOrder.take(2).toSet()
            val top3 = finishOrder.take(3).toSet()
            features.laneHistory.forEachIndexed { index, lane ->
                val laneNumber = index + 1
                pending += ModelAPlayerHistory.OutcomeUpdate(
                    player = lane.player,
                    course = lane.course,
                    racerClass = lane.racerClass,
                    exhibitionTime = lane.exhibitionTime,
                    previewStartTiming = lane.previewStartTiming,
                    win = laneNumber == first,
                    top2 = laneNumber in top2,
                    top3 = laneNumber in top3,
                    flags = lane.flags
                )
            }
        }

        // A stale/partial previous-day response is worse than falling back to the
        // stable v0.15.16 forecaster. Do not permanently advance the history clock
        // unless most scheduled races have a complete six-boat result.
        require(settledSixBoat * 5 >= races.size * 4) {
            "Refusing incomplete Model A history day: settled=$settledSixBoat source=${races.size}"
        }
        require(pending.size % 6 == 0)
        history.commitDay(day, pending)
        return Summary(
            dayOrdinal = day,
            sourceRaces = races.size,
            settledSixBoatRaces = settledSixBoat,
            featureUsableRaces = featureUsable,
            committedRaces = pending.size / 6,
            skippedResultRaces = skippedResult,
            skippedFeatureRaces = skippedFeature,
            historyLastDay = history.lastDay
        )
    }
}
