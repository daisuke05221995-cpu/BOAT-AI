package jp.boatai.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant

/** Informational cloud receipt monitor. Not AI forecast availability or verified odds. */
data class CollectorCloudMonitorState(
    val loading: Boolean = false,
    val monitoringState: String = "UNKNOWN",
    val activeDevices: Int = 0,
    val lastReceivedAt: Long? = null,
    val lastReceivedAgeSeconds: Long? = null,
    val lastRaceCount: Int? = null,
    val lastCheckedAt: Long? = null,
    val error: String? = null
)

internal object CollectorCloudMonitorContract {
    fun parse(body: String): CollectorCloudMonitorState {
        val root = JSONObject(body)
        require(root.getInt("schema_version") == 1 &&
            root.getString("mode") == "DEVICE_RECEIPT_ONLY" &&
            !root.getBoolean("eligible_for_forecast")) { "端末監視データの種類が不正です" }
        val checked = Instant.parse(root.getString("evaluated_at")).toEpochMilli()
        val status = root.getString("monitoring_state")
        require(status in setOf("ACTIVE", "STALE", "NEVER_CONNECTED")) { "監視状態が不明です" }
        val activeDevices = root.getInt("active_devices_10m")
        require(activeDevices in 0..20) { "接続端末数が不正です" }
        val lastTime = if (root.isNull("last_received_at")) null else
            Instant.parse(root.getString("last_received_at")).toEpochMilli()
        val age = if (root.isNull("last_received_age_seconds")) null else
            root.getLong("last_received_age_seconds")
        val threshold = root.getInt("stale_after_seconds")
        require(threshold in 120..3_600 && (age == null || age >= 0)) { "監視時刻が不正です" }
        require(when (status) {
            "ACTIVE" -> lastTime != null && age != null && age <= threshold && activeDevices > 0
            "STALE" -> lastTime != null && age != null && age > threshold
            else -> lastTime == null && age == null && activeDevices == 0
        }) { "監視状態と時刻が一致しません" }
        val raceCount = if (root.isNull("latest_device_race_count")) null else
            root.getInt("latest_device_race_count")
        require(raceCount == null || raceCount in 0..288) { "開催件数が不正です" }
        return CollectorCloudMonitorState(
            monitoringState = status,
            activeDevices = activeDevices,
            lastReceivedAt = lastTime,
            lastReceivedAgeSeconds = age,
            lastRaceCount = raceCount,
            lastCheckedAt = checked
        )
    }
}

internal class CollectorCloudMonitorRepository {
    suspend fun load(): CollectorCloudMonitorState = withContext(Dispatchers.IO) {
        val connection = URL(ENDPOINT).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "GET"
            connection.connectTimeout = 6_000
            connection.readTimeout = 8_000
            connection.setRequestProperty("Accept", "application/json")
            require(connection.responseCode == 200) { "端末監視API応答 HTTP ${connection.responseCode}" }
            val body = connection.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            CollectorCloudMonitorContract.parse(body)
        } finally {
            connection.disconnect()
        }
    }

    private companion object {
        const val ENDPOINT = "https://boat-ai-forecast.daisuke05221995.workers.dev/v1/device-collector/health"
    }
}
