package jp.boatai.app

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.time.Instant
import java.util.UUID

/** Only the BOAT AI in-app refresh action is available. No screen, taps or purchases. */
data class CollectorRemoteState(
    val submitting: Boolean = false,
    val lastRequestedAt: Long? = null,
    val lastAcceptedAt: Long? = null,
    val message: String? = null,
    val error: String? = null
)

internal data class CollectorRemoteCommand(val id: String, val expiresAt: Long)

internal object CollectorRemoteContract {
    fun parseNext(body: String, now: Long = System.currentTimeMillis()): CollectorRemoteCommand? {
        val json = JSONObject(body)
        require(json.getInt("schema_version") == 1) { "操作指示の形式が不正です" }
        if (json.isNull("action")) {
            require(json.isNull("command_id") && json.isNull("expires_at")) { "操作指示の整合性が不正です" }
            return null
        }
        require(json.getString("action") == "REFRESH_NOW") { "許可されていない操作指示です" }
        val id = json.getString("command_id")
        require(runCatching { UUID.fromString(id).toString() == id }.getOrDefault(false)) { "操作指示IDが不正です" }
        val expiry = Instant.parse(json.getString("expires_at")).toEpochMilli()
        require(expiry > now && expiry <= now + 180_000L + 10_000L) { "期限切れの操作指示です" }
        return CollectorRemoteCommand(id, expiry)
    }

    fun parseQueued(body: String): String {
        val json = JSONObject(body)
        require(json.getInt("schema_version") == 1 && json.getBoolean("queued") &&
            json.getString("action") == "REFRESH_NOW") { "遠隔操作の受付を確認できません" }
        val id = json.getString("command_id")
        require(runCatching { UUID.fromString(id).toString() == id }.getOrDefault(false)) { "受付IDが不正です" }
        return id
    }
}

/** A persistent one-time replay fence prevents duplicate refreshes after restarts. */
internal class CollectorRemoteCommandStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("boat_ai_collector_remote_v1", Context.MODE_PRIVATE)
    fun lastProcessed(): String? = prefs.getString("last_processed_command", null)
    fun markProcessed(commandId: String) { prefs.edit().putString("last_processed_command", commandId).apply() }
}

internal class CollectorRemoteRepository {
    suspend fun requestRefresh(token: String): String = withContext(Dispatchers.IO) {
        val body = JSONObject().put("schema_version", 1).put("action", "REFRESH_NOW")
        val response = call("/refresh", "POST", token, body)
        CollectorRemoteContract.parseQueued(response)
    }

    suspend fun next(token: String, deviceId: String): CollectorRemoteCommand? = withContext(Dispatchers.IO) {
        val path = "/next?device_id=" + URLEncoder.encode(deviceId, "UTF-8")
        CollectorRemoteContract.parseNext(call(path, "GET", token))
    }

    suspend fun acknowledge(token: String, deviceId: String, commandId: String) = withContext(Dispatchers.IO) {
        val body = JSONObject()
            .put("schema_version", 1).put("action", "REFRESH_NOW")
            .put("device_id", deviceId).put("command_id", commandId)
        val result = JSONObject(call("/ack", "POST", token, body))
        require(result.getInt("schema_version") == 1 && result.getBoolean("accepted") &&
            result.getString("action") == "REFRESH_NOW") { "操作指示の受付確認に失敗しました" }
    }

    private fun call(path: String, method: String, token: String, body: JSONObject? = null): String {
        val connection = URL(BASE + path).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = 6_000
            connection.readTimeout = 8_000
            connection.setRequestProperty("Authorization", "Bearer $token")
            connection.setRequestProperty("Accept", "application/json")
            if (body != null) {
                connection.setRequestProperty("Content-Type", "application/json")
                connection.doOutput = true
                connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val status = connection.responseCode
            require(status == if (method == "GET") 200 else 202) {
                "遠隔操作API応答 HTTP $status"
            }
            return connection.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private companion object {
        const val BASE = "https://boat-ai-forecast.daisuke05221995.workers.dev/v1/device-collector/remote"
    }
}
