package jp.boatai.app

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PendingPurchaseTicketTest {
    @Test
    fun roundTripKeepsOddsAndTier() {
        val ticket = PendingPurchaseTicket(
            combination = "1-2-3",
            amount = 1800,
            odds = 12.4,
            tier = BetTier.MAIN
        )
        val restored = PendingPurchaseTicket.fromJson(ticket.toJson())
        requireNotNull(restored)

        assertEquals("1-2-3", restored.combination)
        assertEquals(1800, restored.amount)
        assertEquals(12.4, restored.odds!!, 0.0001)
        assertEquals(BetTier.MAIN, restored.tier)
    }

    @Test
    fun legacyTicketWithoutOddsAndTierStillLoads() {
        val restored = PendingPurchaseTicket.fromJson(
            JSONObject()
                .put("combination", "1-3-2")
                .put("amount", 900)
        )
        requireNotNull(restored)

        assertNull(restored.odds)
        assertNull(restored.tier)
    }
}
