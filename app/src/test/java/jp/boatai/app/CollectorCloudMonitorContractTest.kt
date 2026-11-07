package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class CollectorCloudMonitorContractTest {
    private val base = """{
      "schema_version":1,"mode":"DEVICE_RECEIPT_ONLY","eligible_for_forecast":false,
      "evaluated_at":"2026-11-08T01:00:00.000Z","monitoring_state":"ACTIVE",
      "stale_after_seconds":300,"active_devices_10m":1,
      "last_received_at":"2026-11-08T00:59:00.000Z","last_received_age_seconds":60,
      "last_race_date":"2026-11-08","latest_device_race_count":132
    }""".trimIndent()

    @Test fun acceptsOnlyAnonymousDeviceReceiptAndNoBetStatus() {
        val parsed = CollectorCloudMonitorContract.parse(base)
        assertEquals("ACTIVE", parsed.monitoringState)
        assertEquals(1, parsed.activeDevices)
        assertEquals(132, parsed.lastRaceCount)
    }

    @Test fun detectsStaleButDoesNotCallItAiSkip() {
        val parsed = CollectorCloudMonitorContract.parse(base.replace("\"ACTIVE\"", "\"STALE\"")
            .replace("\"last_received_age_seconds\":60", "\"last_received_age_seconds\":301"))
        assertEquals("STALE", parsed.monitoringState)
    }

    @Test fun distinguishesNeverConnectedFromNetworkError() {
        val parsed = CollectorCloudMonitorContract.parse(base.replace("\"ACTIVE\"", "\"NEVER_CONNECTED\"")
            .replace("\"active_devices_10m\":1", "\"active_devices_10m\":0")
            .replace("\"last_received_at\":\"2026-11-08T00:59:00.000Z\"", "\"last_received_at\":null")
            .replace("\"last_received_age_seconds\":60", "\"last_received_age_seconds\":null"))
        assertEquals("NEVER_CONNECTED", parsed.monitoringState)
        assertNull(parsed.lastReceivedAt)
    }

    @Test(expected = IllegalArgumentException::class)
    fun refusesForecastClassification() {
        CollectorCloudMonitorContract.parse(base.replace("\"eligible_for_forecast\":false", "\"eligible_for_forecast\":true"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun refusesInconsistentActiveStatus() {
        CollectorCloudMonitorContract.parse(base.replace("\"active_devices_10m\":1", "\"active_devices_10m\":0"))
    }
}
