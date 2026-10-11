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
            tier = BetTier.MAIN,
            aiProbability = 0.081,
            expectedReturnRate = 100.44
        )
        val restored = PendingPurchaseTicket.fromJson(ticket.toJson())
        requireNotNull(restored)

        assertEquals("1-2-3", restored.combination)
        assertEquals(1800, restored.amount)
        assertEquals(12.4, restored.odds!!, 0.0001)
        assertEquals(BetTier.MAIN, restored.tier)
        assertEquals(0.081, restored.aiProbability!!, 0.0001)
        assertEquals(100.44, restored.expectedReturnRate!!, 0.0001)
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
        assertNull(restored.aiProbability)
        assertNull(restored.expectedReturnRate)
    }
}
