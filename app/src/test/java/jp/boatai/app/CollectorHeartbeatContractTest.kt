package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class CollectorHeartbeatContractTest {
    private val deviceId = "a4bc0020-16cc-4db5-9448-a709029b2017"

    @Test fun onlyTwelveWhitelistedAuditFieldsAreUploaded() {
        val status = LiveOddsRefreshStatus(
            attempted = 3, succeeded = 2, failed = 1,
            lastCheckedAt = 1_783_485_655_000L,
            lastSuccessAt = 1_783_485_645_000L
        )
        val body = CollectorHeartbeatContract.encode(
            deviceId,
            BoatUiState(date = LocalDate.of(2026, 7, 8), liveOddsRefresh = status),
            1_783_485_659_000L
        )
        assertEquals(12, body.length())
        assertEquals(deviceId, body.getString("device_id"))
        assertEquals(3, body.getInt("odds_attempted"))
        assertEquals(2, body.getInt("odds_succeeded"))
        assertTrue(body.isNull("program_received_at"))
        for (forbidden in listOf("odds", "odds_values", "preview", "forecast", "bets", "purchases", "account")) {
            assertFalse(body.has(forbidden))
        }
    }

    @Test fun emptyCountersHaveNullReceiptTimestamps() {
        val body = CollectorHeartbeatContract.encode(
            deviceId, BoatUiState(date = LocalDate.of(2026, 7, 8)), 1_783_485_659_000L
        )
        assertEquals(0, body.getInt("race_count"))
        assertEquals(0, body.getInt("odds_attempted"))
        assertTrue(body.isNull("odds_last_attempt_at"))
        assertTrue(body.isNull("odds_last_success_at"))
    }
}
