package jp.boatai.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.LocalDate

/** Read-only mirror. Never use cloud data to place a bet or rewrite local accounting. */
data class CloudRaceForecast(
    val raceId: String,
    val status: String,
    val decision: String?,
    val reason: String?,
    val forecastCompletedAt: String?
)

data class CloudForecastBatch(
    val date: String,
    val generatedAt: String,
    val races: Map<String, CloudRaceForecast>
) {
    val buyCount: Int get() = races.values.count { it.status == "READY" && it.decision == "BUY" }
    val skipCount: Int get() = races.values.count { it.status == "READY" && it.decision == "SKIP" }
    val pendingCount: Int get() = races.values.count { it.status == "PENDING" }
    val unavailableCount: Int get() = races.values.count { it.status == "UNAVAILABLE" }
}

data class CloudForecastSyncState(
    val loading: Boolean = false,
    val batch: CloudForecastBatch? = null,
    val lastSyncAt: Long? = null,
    val error: String? = null
)

/** Validates the public Worker contract before showing any definitive forecast. */
internal object CloudForecastContract {
    private fun optionalString(objectValue: JSONObject, key: String): String? =
        if (!objectValue.has(key) || objectValue.isNull(key)) null else
            objectValue.optString(key).takeIf { it.isNotBlank() }

    fun parse(body: String, expectedDate: LocalDate): CloudForecastBatch {
        val root = JSONObject(body)
        require(root.optInt("schema_version") == 1) { "クラウドのデータ形式が未対応です" }
        val date = root.optString("date")
        require(date == expectedDate.toString()) { "クラウドの対象日が一致しません" }
        val generated = root.optString("generated_at")
        Instant.parse(generated)
        val rows = root.getJSONArray("races")
        require(rows.length() <= 288) { "クラウドのレース件数が不正です" }
        val forecasts = linkedMapOf<String, CloudRaceForecast>()
        for (index in 0 until rows.length()) {
            val row = rows.getJSONObject(index)
            val id = row.getString("race_id")
            require(id.matches(Regex("${Regex.escape(date)}-\\d{2}-\\d{1,2}"))) { "レースIDが不正です" }
            require(!forecasts.containsKey(id)) { "同じレースが重複しています" }
            val rawStatus = row.getString("status")
            require(rawStatus in setOf("READY", "PENDING", "UNAVAILABLE")) { "クラウドの状態が不明です" }
            val deadline = Instant.parse(row.getString("deadline_at"))
            val completed = optionalString(row, "forecast_completed_at")
            val decision = optionalString(row, "decision")
            val sourceOk = optionalString(row, "preview_source") != null &&
                optionalString(row, "odds_source") != null
            val observedOk = listOf("preview_observed_at", "odds_observed_at").all { key ->
                val stamp = optionalString(row, key)
                stamp != null && runCatching { Instant.parse(stamp).isBefore(deadline) }.getOrDefault(false)
            }
            val timestampsOk = completed != null && runCatching { Instant.parse(completed).isBefore(deadline) }.getOrDefault(false)
            val combinations = row.optJSONArray("combinations")
            val stakes = row.optJSONArray("stakes")
            val betFieldsOk = when (decision) {
                "BUY" -> combinations != null && stakes != null && combinations.length() == stakes.length() &&
                    combinations.length() in 1..120 && (0 until combinations.length()).all { k ->
                        combinations.optString(k).matches(Regex("[1-6]-[1-6]-[1-6]")) &&
                            combinations.optString(k).split('-').distinct().size == 3 && stakes.optInt(k) > 0
                    }
                "SKIP" -> true
                else -> false
            }
            // A malformed READY is not displayed as a decision; it is never
            // silently converted into a valid BUY or into an AI SKIP.
            val verifiedReady = rawStatus == "READY" && decision in setOf("BUY", "SKIP") &&
                optionalString(row, "model_version") != null && sourceOk && observedOk && timestampsOk && betFieldsOk
            val status = if (rawStatus == "READY" && !verifiedReady) "UNAVAILABLE" else rawStatus
            val flags = row.optJSONArray("quality_flags")
            val reason = if (rawStatus == "READY" && !verifiedReady) "CLOUD_READY_INVALID" else
                if (flags != null && flags.length() > 0) flags.optString(0).take(100) else null
            forecasts[id] = CloudRaceForecast(id, status, if (verifiedReady) decision else null,
                reason, if (verifiedReady) completed else null)
        }
        return CloudForecastBatch(date, generated, forecasts)
    }
}

internal class CloudForecastRepository {
    suspend fun load(date: LocalDate): CloudForecastBatch = withContext(Dispatchers.IO) {
        val url = URL("https://boat-ai-forecast.daisuke05221995.workers.dev/v1/forecasts?date=$date")
        val connection = url.openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "GET"
            connection.connectTimeout = 6_000
            connection.readTimeout = 8_000
            connection.setRequestProperty("Accept", "application/json")
            require(connection.responseCode == 200) { "クラウド応答 ${connection.responseCode}" }
            val body = connection.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            CloudForecastContract.parse(body, date)
        } finally {
            connection.disconnect()
        }
    }
}
