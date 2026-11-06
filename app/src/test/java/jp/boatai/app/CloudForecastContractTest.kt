package jp.boatai.app

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.LocalDate

class CloudForecastContractTest {
    private val date = LocalDate.of(2026, 11, 6)

    private fun race(id: String = "2026-11-06-05-7", status: String = "READY") = JSONObject()
        .put("race_id", id)
        .put("deadline_at", "2026-11-06T06:00:00Z")
        .put("forecast_completed_at", "2026-11-06T05:53:00Z")
        .put("status", status)
        .put("decision", "BUY")
        .put("model_version", "model-a-0.16")
        .put("preview_source", "authorized-preview")
        .put("preview_observed_at", "2026-11-06T05:52:00Z")
        .put("odds_source", "authorized-odds")
        .put("odds_observed_at", "2026-11-06T05:52:30Z")
        .put("combinations", JSONArray().put("1-3-4"))
        .put("stakes", JSONArray().put(300))
        .put("quality_flags", JSONArray())

    private fun payload(vararg races: JSONObject): String = JSONObject()
        .put("schema_version", 1)
        .put("date", date.toString())
        .put("generated_at", "2026-11-06T05:54:00Z")
        .put("races", JSONArray().also { arr -> races.forEach { row -> arr.put(row) } })
        .toString()

    @Test fun verifiedReadyCanBeDisplayedReadOnly() {
        val batch = CloudForecastContract.parse(payload(race()), date)
        assertEquals(1, batch.buyCount)
        assertEquals(0, batch.skipCount)
        assertEquals("BUY", batch.races.values.single().decision)
    }

    @Test fun missingSourceOrTimestampsCannotBecomeBuy() {
        val missing = race().put("preview_source", JSONObject.NULL)
        val stale = race("2026-11-06-05-8").put("odds_observed_at", "2026-11-06T06:01:00Z")
        val malformedBet = race("2026-11-06-05-9").put("combinations", JSONArray().put("1-1-2"))
        val batch = CloudForecastContract.parse(payload(missing, stale, malformedBet), date)
        assertEquals(0, batch.buyCount)
        assertEquals(3, batch.unavailableCount)
        assertTrue(batch.races.values.all { it.decision == null && it.reason == "CLOUD_READY_INVALID" })
    }

    @Test fun unavailableAndPendingNeverCountAsSkip() {
        val pending = race().put("status", "PENDING").put("decision", JSONObject.NULL)
            .put("forecast_completed_at", JSONObject.NULL)
        val unavailable = race("2026-11-06-05-8").put("status", "UNAVAILABLE")
            .put("quality_flags", JSONArray().put("ODDS_PROVIDER_NOT_CONFIGURED"))
        val batch = CloudForecastContract.parse(payload(pending, unavailable), date)
        assertEquals(0, batch.buyCount)
        assertEquals(0, batch.skipCount)
        assertEquals(1, batch.pendingCount)
        assertEquals(1, batch.unavailableCount)
        assertEquals("ODDS_PROVIDER_NOT_CONFIGURED", batch.races["2026-11-06-05-8"]?.reason)
    }

    @Test fun dateMismatchAndDuplicateRaceFailEntireSync() {
        assertThrows(IllegalArgumentException::class.java) {
            CloudForecastContract.parse(payload(race()), date.minusDays(1))
        }
        assertThrows(IllegalArgumentException::class.java) {
            CloudForecastContract.parse(payload(race(), race()), date)
        }
    }
}
