package jp.boatai.app

import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProgramDataAvailabilityTest {
    @Test
    fun todays404IsPublicationWait() {
        val today = LocalDate.of(2026, 10, 11)
        assertTrue(ProgramDataAvailability.isTodayPublicationWait(today, today, 404))
        assertFalse(ProgramDataAvailability.isTodayPublicationWait(today.minusDays(1), today, 404))
        assertFalse(ProgramDataAvailability.isTodayPublicationWait(today, today, 500))
    }

    @Test
    fun todayAliasCannotLeakPreviousDayData() {
        val requested = LocalDate.of(2026, 10, 11)
        val races = listOf(
            race("2026-10-10"),
            race("2026-10-11")
        )

        assertEquals(
            listOf("2026-10-11"),
            ProgramDataAvailability.keepRequestedDate(races, requested).map { it.date }
        )
    }

    private fun race(date: String) = RaceData(
        date = date,
        stadiumNumber = 1,
        raceNumber = 1,
        closedAt = "10:00",
        gradeNumber = null,
        title = "",
        subtitle = "",
        distance = null,
        dayNumber = null,
        racers = emptyList(),
        preview = null,
        result = null
    )
}
