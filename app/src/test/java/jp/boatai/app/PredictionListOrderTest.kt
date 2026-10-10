package jp.boatai.app

import java.time.LocalDateTime
import org.junit.Assert.assertEquals
import org.junit.Test

class PredictionListOrderTest {
    private fun race(
        idDate: String = "2026-10-11",
        stadium: Int,
        raceNumber: Int,
        close: String
    ) = RaceData(
        date = idDate,
        stadiumNumber = stadium,
        raceNumber = raceNumber,
        closedAt = close,
        gradeNumber = null,
        title = "",
        subtitle = "",
        distance = null,
        dayNumber = null,
        racers = List(6) { index ->
            Racer(
                lane = index + 1,
                name = "R" + (index + 1),
                registrationNumber = 1000 + index,
                rank = "B1",
                branch = null,
                age = null,
                weight = null,
                averageStart = null,
                nationalWinRate = null,
                nationalTop2 = null,
                nationalTop3 = null,
                localWinRate = null,
                localTop2 = null,
                localTop3 = null,
                motorNumber = null,
                motorTop2 = null,
                motorTop3 = null,
                boatNumber = null,
                boatTop2 = null,
                boatTop3 = null,
                preview = null
            )
        },
        preview = null,
        result = null
    )

    @Test
    fun deadlineModeSortsIndividualOpenRacesAcrossVenues() {
        val now = LocalDateTime.of(2026, 10, 11, 10, 0)
        val races = listOf(
            race(stadium = 2, raceNumber = 1, close = "11:20"),
            race(stadium = 1, raceNumber = 4, close = "10:40"),
            race(stadium = 3, raceNumber = 2, close = "10:55")
        )

        assertEquals(
            listOf("2026-10-11-01-4", "2026-10-11-03-2", "2026-10-11-02-1"),
            PredictionListOrder.byDeadline(races, now).map { it.id }
        )
    }

    @Test
    fun deadlineModeDropsAlreadyClosedRaces() {
        val now = LocalDateTime.of(2026, 10, 11, 10, 50)
        val races = listOf(
            race(stadium = 1, raceNumber = 1, close = "10:40"),
            race(stadium = 1, raceNumber = 2, close = "11:00")
        )

        assertEquals(listOf(2), PredictionListOrder.byDeadline(races, now).map { it.raceNumber })
    }
}
