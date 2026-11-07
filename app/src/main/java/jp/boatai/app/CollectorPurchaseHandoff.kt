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

/** A proposed bet list transferred to the second phone. Never a purchase confirmation. */
data class CollectorPurchaseHandoff(
    val handoffId: String,
    val expiresAt: Long,
    val session: PendingPurchaseSession
)

data class PurchaseHandoffStatus(
    val sending: Boolean = false,
    val sentAt: Long? = null,
    val message: String? = null,
    val error: String? = null
)

internal object CollectorPurchaseHandoffContract {
    fun parseStaged(body: String): String {
        val json = JSONObject(body)
        require(json.getInt("schema_version") == 1 && json.getBoolean("staged")) { "買い目の転送が確認できません" }
        val id = json.getString("handoff_id")
        require(validUuid(id)) { "転送IDが不正です" }
        return id
    }

    fun parseNext(body: String, now: Long = System.currentTimeMillis()): CollectorPurchaseHandoff? {
        val json = JSONObject(body)
        require(json.getInt("schema_version") == 1) { "買い目のデータ形式が不正です" }
        if (json.isNull("handoff_id")) {
            require(json.isNull("session") && json.isNull("expires_at")) { "買い目のデータ整合性が不正です" }
            return null
        }
        val id = json.getString("handoff_id")
        require(validUuid(id)) { "転送IDが不正です" }
        val expires = Instant.parse(json.getString("expires_at")).toEpochMilli()
        require(expires > now && expires <= now + 11 * 60_000L) { "買い目の転送期限が切れています" }
        val session = PendingPurchaseSession.fromJson(json.getJSONObject("session"))
            ?: error("買い目を読み込めません")
        require(session.selectedRaces.isNotEmpty()) { "買い目が選択されていません" }
        return CollectorPurchaseHandoff(id, expires, session)
    }

    private fun validUuid(id: String): Boolean =
        runCatching { UUID.fromString(id).toString() == id }.getOrDefault(false)
}

/** Store the inbox locally so a screen rotation or restart does not lose unsubmitted picks. */
internal class CollectorPurchaseInboxStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("boat_ai_collector_purchase_inbox_v1", Context.MODE_PRIVATE)

    fun load(): CollectorPurchaseHandoff? = runCatching {
        val raw = prefs.getString("handoff", null) ?: return null
        val json = JSONObject(raw)
        CollectorPurchaseHandoff(
            handoffId = json.getString("id"),
            expiresAt = json.getLong("expires"),
            session = PendingPurchaseSession.fromJson(json.getJSONObject("session")) ?: return null
        )
    }.getOrNull()

    fun save(handoff: CollectorPurchaseHandoff) {
        prefs.edit().putString("handoff", JSONObject()
            .put("id", handoff.handoffId)
            .put("expires", handoff.expiresAt)
            .put("session", handoff.session.toJson()).toString()).apply()
    }

    fun clear() = prefs.edit().remove("handoff").apply()
}

internal class CollectorPurchaseHandoffRepository {
    suspend fun stage(token: String, session: PendingPurchaseSession): String = withContext(Dispatchers.IO) {
        CollectorPurchaseHandoffContract.parseStaged(call("/stage", "POST", token,
            JSONObject().put("schema_version", 1).put("session", session.toJson())))
    }

    suspend fun next(token: String, deviceId: String): CollectorPurchaseHandoff? = withContext(Dispatchers.IO) {
        CollectorPurchaseHandoffContract.parseNext(call("/next?device_id=" + URLEncoder.encode(deviceId, "UTF-8"), "GET", token))
    }

    suspend fun acknowledge(token: String, deviceId: String, id: String) = withContext(Dispatchers.IO) {
        val json = JSONObject(call("/ack", "POST", token, JSONObject()
            .put("schema_version", 1).put("device_id", deviceId).put("handoff_id", id)))
        require(json.getInt("schema_version") == 1 && json.getBoolean("accepted")) { "買い目の受信確認に失敗しました" }
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
            require(status == if (method == "GET") 200 else 202) { "買い目転送API応答 HTTP $status" }
            return connection.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private companion object {
        const val BASE = "https://boat-ai-forecast.daisuke05221995.workers.dev/v1/device-collector/purchase-handoff"
    }
}
