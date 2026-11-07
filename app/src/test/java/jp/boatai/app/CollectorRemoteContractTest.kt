package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Test
import java.time.Instant
import java.util.UUID

class CollectorRemoteContractTest {
    private val now = Instant.parse("2026-11-08T05:00:00Z").toEpochMilli()

    @Test fun onlyAllowlistedRefreshIsDecoded() {
        val id = UUID.randomUUID().toString()
        val expiry = Instant.ofEpochMilli(now + 120_000L).toString()
        assertEquals(id, CollectorRemoteContract.parseNext("""{
            "schema_version":1,"action":"REFRESH_NOW","command_id":"$id","expires_at":"$expiry"
        }""", now)?.id)
        assertNull(CollectorRemoteContract.parseNext("""{
            "schema_version":1,"action":null,"command_id":null,"expires_at":null
        }""", now))
        assertEquals(id, CollectorRemoteContract.parseQueued("""{
            "schema_version":1,"queued":true,"command_id":"$id","action":"REFRESH_NOW"
        }"""))
    }

    @Test fun purchaseAndStaleCommandsAreRejected() {
        val id = UUID.randomUUID().toString()
        val expiry = Instant.ofEpochMilli(now + 120_000L).toString()
        assertThrows(IllegalArgumentException::class.java) {
            CollectorRemoteContract.parseNext("""{
                "schema_version":1,"action":"BUY","command_id":"$id","expires_at":"$expiry"
            }""", now)
        }
        assertThrows(IllegalArgumentException::class.java) {
            CollectorRemoteContract.parseNext("""{
                "schema_version":1,"action":"REFRESH_NOW","command_id":"$id",
                "expires_at":"${Instant.ofEpochMilli(now - 1)}"
            }""", now)
        }
    }
}
