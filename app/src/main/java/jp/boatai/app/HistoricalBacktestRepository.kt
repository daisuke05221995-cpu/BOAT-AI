package jp.boatai.app

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class HistoricalBacktestPeriod(
    val year: Int,
    val month: Int?,
    val purchaseRaces: Int,
    val skippedRaces: Int,
    val unavailableRaces: Int,
    val purchaseHits: Int,
    val stake: Int,
    val payout: Int,
    val profit: Int,
    val roi: Double,
    val hitRate: Double,
    val purchaseRate: Double,
    val evaluatedRaces: Int,
    val phase: String,
    val statsAvailable: Boolean
)

data class HistoricalBacktestData(
    val year: Int,
    val generatedAt: String,
    val dataFrom: String,
    val dataThrough: String,
    val simulationBudget: Int,
    val oddsFinalGateIncluded: Boolean,
    val method: String,
    val months: List<HistoricalBacktestPeriod>,
    val yearSummary: HistoricalBacktestPeriod,
    val historicalCriteriaMet: Boolean,
    val releaseDeferredForIndependentValidation: Boolean
)

data class HistoricalBacktestLoadResult(
    val data: HistoricalBacktestData?,
    val error: String? = null,
    val fromCache: Boolean = false
)

class HistoricalBacktestRepository(context: Context) {
    private val prefs = context.applicationContext
        .getSharedPreferences("boat_ai_historical_backtest_v15_stable", Context.MODE_PRIVATE)

    suspend fun load(): HistoricalBacktestLoadResult = withContext(Dispatchers.IO) {
        val remote = runCatching {
            val text = httpGet("$REMOTE_URL?ts=${System.currentTimeMillis()}")
            parse(text).also {
                prefs.edit().putString(KEY_CACHE, text).putLong(KEY_FETCHED_AT, System.currentTimeMillis()).apply()
            }
        }
        remote.getOrNull()?.let { return@withContext HistoricalBacktestLoadResult(it) }

        val cached = prefs.getString(KEY_CACHE, null)
        if (!cached.isNullOrBlank()) {
            runCatching { parse(cached) }.getOrNull()?.let {
                return@withContext HistoricalBacktestLoadResult(
                    data = it,
                    error = "最新データの取得に失敗したため端末キャッシュを表示しています",
                    fromCache = true
                )
            }
        }

        HistoricalBacktestLoadResult(
            data = null,
            error = remote.exceptionOrNull()?.message ?: "過去バックテストデータを取得できませんでした"
        )
    }

    private fun parse(text: String): HistoricalBacktestData {
        val root = JSONObject(text)
        require(root.optInt("schemaVersion") >= 1) { "バックテストデータ形式が不正です" }
        val year = root.optInt("year", 2026)
        val monthsJson = root.optJSONArray("months")
            ?: throw IllegalArgumentException("months がありません")

        val months = buildList {
            for (index in 0 until monthsJson.length()) {
                val stats = monthsJson.getJSONObject(index)
                add(periodFromJson(stats, stats.optInt("month"), "現行予想ロジック参考検証"))
            }
        }

        val summary = root.optJSONObject("yearSummary")
            ?: throw IllegalArgumentException("yearSummary がありません")
        val yearSummary = periodFromJson(summary, null, "現行予想ロジック 2026年参考合計")

        return HistoricalBacktestData(
            year = year,
            generatedAt = root.optString("generatedAt"),
            dataFrom = root.optString("dataFrom"),
            dataThrough = root.optString("dataThrough"),
            simulationBudget = root.optInt("simulationBudget", BetStrategy.DEFAULT_BUDGET),
            oddsFinalGateIncluded = root.optBoolean("oddsFinalGateIncluded", false),
            method = root.optString("method"),
            months = months,
            yearSummary = yearSummary,
            historicalCriteriaMet = false,
            releaseDeferredForIndependentValidation = false
        )
    }

    private fun periodFromJson(stats: JSONObject, month: Int?, phase: String): HistoricalBacktestPeriod {
        return HistoricalBacktestPeriod(
            year = stats.optInt("year", 2026),
            month = month,
            purchaseRaces = stats.optInt("purchaseRaces"),
            skippedRaces = stats.optInt("skippedRaces"),
            unavailableRaces = stats.optInt("unavailableRaces"),
            purchaseHits = stats.optInt("purchaseHits"),
            stake = stats.optInt("stake"),
            payout = stats.optInt("payout"),
            profit = stats.optInt("profit"),
            roi = stats.optDouble("roi"),
            hitRate = stats.optDouble("hitRate"),
            purchaseRate = stats.optDouble("purchaseRate"),
            evaluatedRaces = stats.optInt("evaluatedRaces"),
            phase = phase,
            statsAvailable = true
        )
    }

    private fun httpGet(url: String): String {
        val connection = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 12_000
            readTimeout = 20_000
            useCaches = false
            setRequestProperty("User-Agent", "BOAT-AI-Android/${BuildConfig.VERSION_NAME}")
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Cache-Control", "no-cache")
        }
        return try {
            val status = connection.responseCode
            if (status !in 200..299) throw IllegalStateException("HTTP $status")
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    companion object {
        private const val KEY_CACHE = "latest_json"
        private const val KEY_FETCHED_AT = "fetched_at"
        private const val REMOTE_URL =
            "https://raw.githubusercontent.com/daisuke05221995-cpu/BOAT-AI/main/data/historical_backtest_2026.json"
    }
}
