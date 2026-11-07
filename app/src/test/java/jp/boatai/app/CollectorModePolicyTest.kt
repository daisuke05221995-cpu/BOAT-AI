package jp.boatai.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class CollectorModePolicyTest {
    @Test fun onlyDedicatedCollectorRollsOverFromYesterday() {
        val yesterday = LocalDate.of(2026, 11, 6)
        val today = LocalDate.of(2026, 11, 7)
        assertTrue(CollectorModePolicy.needsTodayReload(true, yesterday, today))
        assertFalse(CollectorModePolicy.needsTodayReload(false, yesterday, today))
        assertFalse(CollectorModePolicy.needsTodayReload(true, today, today))
    }

    @Test fun collectorReturnsToTodayEvenIfBrowsingAnotherDate() {
        assertTrue(CollectorModePolicy.needsTodayReload(
            enabled = true,
            selectedDate = LocalDate.of(2026, 11, 3),
            today = LocalDate.of(2026, 11, 7)
        ))
    }
}
