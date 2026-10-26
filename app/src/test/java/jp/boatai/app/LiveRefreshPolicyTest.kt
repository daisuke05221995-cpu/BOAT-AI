package jp.boatai.app

import java.time.LocalDate
import java.time.LocalDateTime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LiveRefreshPolicyTest {
    private val now = LocalDateTime.of(2026, 10, 26, 10, 23)

    private fun race(stadium: Int, raceNumber: Int, close: String, ready: Boolean = true): RaceData {
        val preview = if (ready) PreviewRacer(1, 0.12, null, null, 6.70, null) else null
        return RaceData(
            date = "2026-10-26",
            stadiumNumber = stadium,
            raceNumber = raceNumber,
            closedAt = "2026-10-26 $close:00",
            gradeNumber = null,
            title = "",
            subtitle = "",
            distance = null,
            dayNumber = null,
            racers = List(6) { index ->
                Racer(
                    lane = index + 1,
                    name = "R${index + 1}",
                    registrationNumber = null,
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
                    preview = preview?.copy(course = index + 1)
                )
            },
            preview = if (ready) PreviewData(null, null, null, null, null, null) else null,
            result = null
        )
    }

    @Test fun liveRefreshOnlyRunsForCurrentDayWithUpcomingRaces() {
        val future = race(11, 1, "10:27")
        assertTrue(LiveRefreshPolicy.shouldRefresh(now.toLocalDate(), listOf(future), now))
        assertTrue(LiveRefreshPolicy.shouldRefresh(now.toLocalDate(), emptyList(), now))
        assertFalse(LiveRefreshPolicy.shouldRefresh(LocalDate.of(2026, 10, 25), listOf(future), now))
        assertFalse(LiveRefreshPolicy.shouldRefresh(now.toLocalDate(), listOf(race(9, 1, "10:20")), now))
    }

    @Test fun oddsEvaluationPrioritizesNearestDeadlineAcrossVenues() {
        val races = listOf(
            race(1, 5, "11:50"),
            race(9, 1, "10:30"),
            race(11, 1, "10:27"),
            race(10, 5, "10:33"),
            race(6, 1, "10:42", ready = false)
        )
        assertEquals(
            listOf("2026-10-26-11-1", "2026-10-26-09-1", "2026-10-26-10-5"),
            LiveRefreshPolicy.oddsCandidates(races, now, nearDeadlineOnly = true).map { it.id }
        )
        assertEquals(4, LiveRefreshPolicy.oddsCandidates(races, now, nearDeadlineOnly = false).size)
    }
}
