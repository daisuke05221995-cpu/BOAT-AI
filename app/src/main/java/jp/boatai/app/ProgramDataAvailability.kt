package jp.boatai.app

import java.time.LocalDate

internal object ProgramDataAvailability {
    fun isTodayPublicationWait(
        requestedDate: LocalDate,
        today: LocalDate,
        statusCode: Int
    ): Boolean = requestedDate == today && statusCode == 404

    fun keepRequestedDate(
        races: List<RaceData>,
        requestedDate: LocalDate
    ): List<RaceData> = races.filter { race ->
        race.date.take(10) == requestedDate.toString()
    }

    /** A transient empty/wrong-day response must not replace a usable saved day. */
    fun shouldCache(races: List<RaceData>): Boolean = races.isNotEmpty()

    /** Keep the already displayed day if today's source temporarily says "not published". */
    fun shouldRetainVisibleRaces(
        visibleDate: LocalDate,
        requestedDate: LocalDate,
        visibleRaces: List<RaceData>,
        fetchedRaces: List<RaceData>,
        waitingForPublication: Boolean
    ): Boolean = visibleDate == requestedDate &&
        visibleRaces.isNotEmpty() && fetchedRaces.isEmpty() && waitingForPublication
}
