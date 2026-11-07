package jp.boatai.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant

data class CollectorUploadStatus(
    val configured: Boolean = false,
    val uploading: Boolean = false,
    val lastAcceptedAt: Long? = null,
    val error: String? = null
)

/** The uploaded values are monitoring metrics, not pre-close odds or exhibition provenance. */
internal object CollectorHeartbeatContract {
    fun encode(deviceId: String, state: BoatUiState, sentAt: Long): JSONObject {
        val odds = state.liveOddsRefresh
        return JSONObject().apply {
            put("schema_version", 1)
            put("date", state.date.toString())
            put("device_id", deviceId)
            put("app_version", BuildConfig.VERSION_NAME)
            put("sent_at", Instant.ofEpochMilli(sentAt).toString())
            put("program_received_at", state.programUpdatedAt?.let { Instant.ofEpochMilli(it).toString() } ?: JSONObject.NULL)
            put("race_count", state.races.size)
            put("odds_attempted", odds.attempted)
            put("odds_succeeded", odds.succeeded)
            put("odds_failed", odds.failed)
            put("odds_last_attempt_at", odds.lastCheckedAt?.let { Instant.ofEpochMilli(it).toString() } ?: JSONObject.NULL)
            put("odds_last_success_at", odds.lastSuccessAt?.let { Instant.ofEpochMilli(it).toString() } ?: JSONObject.NULL)
        }
    }
}

internal class CollectorHeartbeatUploader {
    suspend fun upload(body: String, token: String): Long = withContext(Dispatchers.IO) {
        val connection = URL(ENDPOINT).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 6_000
            connection.readTimeout = 6_000
            connection.setRequestProperty("Content-Type", "application/json")
            connection.setRequestProperty("Authorization", "Bearer $token")
            connection.doOutput = true
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            val status = connection.responseCode
            if (status != 202) throw IllegalStateException("クラウド受信エラー HTTP $status")
            val response = connection.inputStream.bufferedReader().use { it.readText() }
            val root = JSONObject(response)
            require(root.optString("classification") == "DEVICE_RECEIPT_ONLY" &&
                !root.optBoolean("eligible_for_forecast", true) && root.optBoolean("accepted")) {
                "クラウド応答の確認に失敗しました"
            }
            Instant.parse(root.getString("server_received_at")).toEpochMilli()
        } finally {
            connection.disconnect()
        }
    }

    private companion object {
        const val ENDPOINT = "https://boat-ai-forecast.daisuke05221995.workers.dev/v1/device-collector/heartbeat"
    }
}
