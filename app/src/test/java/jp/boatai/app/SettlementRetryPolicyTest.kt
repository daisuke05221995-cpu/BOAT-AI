package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SettlementRetryPolicyTest {
    @Test
    fun retriesPendingSettlementOnlyWithinBound() {
        assertTrue(SettlementRetryPolicy.shouldRetry(0, true))
        assertTrue(SettlementRetryPolicy.shouldRetry(1, true))
        assertTrue(SettlementRetryPolicy.shouldRetry(2, true))
        assertFalse(SettlementRetryPolicy.shouldRetry(3, true))
    }

    @Test
    fun doesNotRetryWhenNothingIsPending() {
        assertFalse(SettlementRetryPolicy.shouldRetry(0, false))
        assertFalse(SettlementRetryPolicy.shouldRetry(2, false))
    }

    @Test
    fun nextAttemptIsCapped() {
        assertEquals(1, SettlementRetryPolicy.nextAttempt(0))
        assertEquals(3, SettlementRetryPolicy.nextAttempt(2))
        assertEquals(3, SettlementRetryPolicy.nextAttempt(3))
    }
}
