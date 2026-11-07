package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test
import java.time.Instant
import java.util.UUID

class CollectorPurchaseHandoffContractTest {
    private val now = Instant.parse("2026-11-08T05:00:00Z").toEpochMilli()
    private val id = UUID.randomUUID().toString()

    private fun response(expiresAt: Long) = """{
      "schema_version":1,
      "handoff_id":"$id",
      "expires_at":"${Instant.ofEpochMilli(expiresAt)}",
      "session":{
        "id":"${UUID.randomUUID()}", "createdAt":$now,
        "races":[{"raceId":"2026-11-08-01-01","date":"2026-11-08",
          "stadiumNumber":1,"raceNumber":1,"venueName":"桐生","recommended":true,
          "tickets":[{"combination":"1-3-5","amount":500}]}],
        "selectedRaceIds":["2026-11-08-01-01"]
      }
    }"""

    @Test fun receivesProposalWithoutRecordingPurchase() {
        val parsed = CollectorPurchaseHandoffContract.parseNext(response(now + 120_000L), now)
        assertEquals(id, parsed?.handoffId)
        assertEquals(500, parsed?.session?.selectedStake)
        assertEquals("1-3-5", parsed?.session?.selectedRaces?.first()?.tickets?.first()?.combination)
        assertNull(CollectorPurchaseHandoffContract.parseNext("""{
          "schema_version":1,"handoff_id":null,"expires_at":null,"session":null
        }""", now))
        assertEquals(id, CollectorPurchaseHandoffContract.parseStaged("""{
          "schema_version":1,"staged":true,"handoff_id":"$id"
        }"""))
    }

    @Test fun refusesExpiredOrMalformedHandoff() {
        assertThrows(IllegalArgumentException::class.java) {
            CollectorPurchaseHandoffContract.parseNext(response(now - 1), now)
        }
        assertThrows(IllegalArgumentException::class.java) {
            CollectorPurchaseHandoffContract.parseNext(response(now + 20 * 60_000L), now)
        }
        assertThrows(IllegalArgumentException::class.java) {
            CollectorPurchaseHandoffContract.parseStaged("""{
              "schema_version":1,"staged":false,"handoff_id":"$id"
            }""")
        }
    }

    @Test fun acceptsOnlyFreshExplicitRemotePurchaseApproval() {
        val json = org.json.JSONObject(response(now + 80_000))
            .put("schema_version", 2)
            .put("purchase_authorized", true)
            .put("approved_at_ms", now - 10_000)
            .put("approved_total_yen", 500)
        val parsed = CollectorPurchaseHandoffContract.parseNext(json.toString(), now)
        assertTrue(parsed?.purchaseAuthorized == true)
        assertEquals(500, parsed?.session?.selectedStake)
        json.put("approved_total_yen", 700)
        assertThrows(IllegalArgumentException::class.java) {
            CollectorPurchaseHandoffContract.parseNext(json.toString(), now)
        }
        json.put("approved_total_yen", 500).put("approved_at_ms", now - 130_000)
        assertThrows(IllegalArgumentException::class.java) {
            CollectorPurchaseHandoffContract.parseNext(json.toString(), now)
        }
    }
}
