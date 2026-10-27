package jp.boatai.app

import java.time.LocalDate
import java.time.LocalDateTime

/** Foreground refresh cadence and deadline priority for live data/odds. */
internal object LiveRefreshPolicy {
    const val INTERVAL_MS = 60_000L
    const val NEAR_DEADLINE_MINUTES = 30
    const val URGENT_DEADLINE_MINUTES = 10
    const val MAX_ODDS_PER_PASS = 4

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

    /**
     * Limit each network pass, rotating through equally urgent races instead of
     * restarting the same first venues on every 60-second refresh.
     */
    fun nextOddsBatch(
        candidates: List<RaceData>,
        now: LocalDateTime,
        lastAttemptAt: Map<String, Long>,
        maxRaces: Int = MAX_ODDS_PER_PASS
    ): List<RaceData> {
        val currentMinutes = now.hour * 60 + now.minute
        val byLeastRecentlyAttempted = compareBy<RaceData> { lastAttemptAt[it.id] ?: Long.MIN_VALUE }
            .thenBy { PredictionListOrder.closeMinutes(it.closedAt) ?: Int.MAX_VALUE }
            .thenBy { it.stadiumNumber }
            .thenBy { it.raceNumber }
        val (urgent, others) = candidates.partition { race ->
            val minutesLeft = (PredictionListOrder.closeMinutes(race.closedAt) ?: Int.MAX_VALUE) - currentMinutes
            minutesLeft in 0..URGENT_DEADLINE_MINUTES
        }
        return (urgent.sortedWith(byLeastRecentlyAttempted) + others.sortedWith(byLeastRecentlyAttempted))
            .take(maxRaces.coerceAtLeast(0))
    }
}
