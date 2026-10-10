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
}
