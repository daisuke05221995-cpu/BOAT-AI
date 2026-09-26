package jp.boatai.app

import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Test

class SettlementRecoveryPlannerTest {
    private val today = LocalDate.of(2026, 9, 27)

    @Test
    fun keepsRecentPastAndTodayButDropsFutureAndTooOld() {
        val selected = SettlementRecoveryPlanner.selectDates(
            listOf("2026-09-27", "2026-09-26", "2026-08-28", "2026-08-27", "2026-09-28", "bad"),
            today
        )

        assertEquals(
            listOf(
                LocalDate.of(2026, 9, 27),
                LocalDate.of(2026, 9, 26),
                LocalDate.of(2026, 8, 28)
            ),
            selected
        )
    }

    @Test
    fun removesDuplicatesAndCapsNetworkDates() {
        val dates = (0L..12L).flatMap { offset ->
            listOf(today.minusDays(offset).toString(), today.minusDays(offset).toString())
        }

        val selected = SettlementRecoveryPlanner.selectDates(dates, today)

        assertEquals(SettlementRecoveryPlanner.MAX_DATES_PER_RUN, selected.size)
        assertEquals(today, selected.first())
        assertEquals(today.minusDays(6), selected.last())
    }
}
