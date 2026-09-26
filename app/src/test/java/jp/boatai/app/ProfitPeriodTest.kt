package jp.boatai.app

import java.time.LocalDate
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ProfitPeriodTest {
    private val anchor = LocalDate.of(2026, 9, 27)

    @Test
    fun todayMatchesOnlyAnchorDate() {
        assertTrue(ProfitPeriodFilter.includes(ProfitPeriod.TODAY, "2026-09-27", anchor))
        assertFalse(ProfitPeriodFilter.includes(ProfitPeriod.TODAY, "2026-09-26", anchor))
    }

    @Test
    fun sevenDayWindowIsInclusive() {
        assertTrue(ProfitPeriodFilter.includes(ProfitPeriod.SEVEN_DAYS, "2026-09-21", anchor))
        assertFalse(ProfitPeriodFilter.includes(ProfitPeriod.SEVEN_DAYS, "2026-09-20", anchor))
    }

    @Test
    fun thirtyDayWindowIsInclusive() {
        assertTrue(ProfitPeriodFilter.includes(ProfitPeriod.THIRTY_DAYS, "2026-08-29", anchor))
        assertFalse(ProfitPeriodFilter.includes(ProfitPeriod.THIRTY_DAYS, "2026-08-28", anchor))
    }

    @Test
    fun monthAndYearUseCalendarBoundaries() {
        assertTrue(ProfitPeriodFilter.includes(ProfitPeriod.MONTH, "2026-09-01", anchor))
        assertFalse(ProfitPeriodFilter.includes(ProfitPeriod.MONTH, "2026-08-31", anchor))
        assertTrue(ProfitPeriodFilter.includes(ProfitPeriod.YEAR, "2026-01-01", anchor))
        assertFalse(ProfitPeriodFilter.includes(ProfitPeriod.YEAR, "2025-12-31", anchor))
    }

    @Test
    fun futureDatesAreExcludedExceptAllTime() {
        assertFalse(ProfitPeriodFilter.includes(ProfitPeriod.YEAR, "2026-09-28", anchor))
        assertTrue(ProfitPeriodFilter.includes(ProfitPeriod.ALL, "2027-01-01", anchor))
    }
}
