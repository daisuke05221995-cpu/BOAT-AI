package jp.boatai.app

import java.time.LocalDate
import java.time.LocalDateTime

/** Foreground refresh cadence and deadline priority for live data/odds. */
internal object LiveRefreshPolicy {
    const val INTERVAL_MS = 60_000L
    const val NEAR_DEADLINE_MINUTES = 30

    fun shouldRefresh(
        selectedDate: LocalDate,
        races: List<RaceData>,
        now: LocalDateTime
    ): Boolean = selectedDate == now.toLocalDate() &&
        (races.isEmpty() || races.any { it.isPurchasable(now) })

    fun isNearDeadline(race: RaceData, now: LocalDateTime): Boolean {
        if (!race.isPurchasable(now)) return false
        val closeMinutes = PredictionListOrder.closeMinutes(race.closedAt) ?: return false
        val currentMinutes = now.hour * 60 + now.minute
        return closeMinutes - currentMinutes in 0..NEAR_DEADLINE_MINUTES
    }

    fun oddsCandidates(
        races: List<RaceData>,
        now: LocalDateTime,
        nearDeadlineOnly: Boolean
    ): List<RaceData> = PredictionListOrder.byDeadline(races, now)
        .filter { !nearDeadlineOnly || isNearDeadline(it, now) }
        .filter(PredictionEngine::isDecisionReady)
}
