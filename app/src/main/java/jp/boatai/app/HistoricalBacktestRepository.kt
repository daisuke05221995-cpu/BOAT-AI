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
    val totalSettledRaces: Int,
    val evaluatedRaces: Int,
    val purchaseRaces: Int,
    val skippedRaces: Int,
    val unavailableRaces: Int,
    val purchaseHits: Int,
    val allPredictionHits: Int,
    val skippedPredictionHits: Int,
    val stake: Int,
    val payout: Int,
    val profit: Int,
    val roi: Double,
    val hitRate: Double,
    val purchaseRate: Double
)

data class HistoricalBacktestData(
    val year: Int,
    val generatedAt: String,
    val dataFrom: String,
    val dataThrough: String,
    val processedDays: Int,
    val simulationBudget: Int,
    val oddsFinalGateIncluded: Boolean,
    val method: String,
    val months: List<HistoricalBacktestPeriod>,
    val yearSummary: HistoricalBacktestPeriod
)

data class HistoricalBacktestLoadResult(
    val data: HistoricalBacktestData?,
    val error: String? = null,
    val fromCache: Boolean = false
)

class HistoricalBacktestRepository(context: Context) {
    private val prefs = context.applicationContext
        .getSharedPreferences("boat_ai_historical_backtest", Context.MODE_PRIVATE)

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
            error = remote.exceptionOrNull()?.message ?: "過去バックテストを取得できませんでした"
        )
    }

    private fun parse(text: String): HistoricalBacktestData {
        val root = JSONObject(text)
        val year = root.optInt("year")
        val monthsArray = root.optJSONArray("months")
        val months = buildList {
            if (monthsArray != null) {
                for (i in 0 until monthsArray.length()) {
                    val obj = monthsArray.optJSONObject(i) ?: continue
                    add(parsePeriod(obj, year, obj.optInt("month").takeIf { it in 1..12 }))
                }
            }
        }.sortedBy { it.month ?: 0 }
        val summaryObj = root.optJSONObject("yearSummary")
            ?: throw IllegalArgumentException("yearSummary がありません")
        return HistoricalBacktestData(
            year = year,
            generatedAt = root.optString("generatedAt"),
            dataFrom = root.optString("dataFrom"),
            dataThrough = root.optString("dataThrough"),
            processedDays = root.optInt("processedDays"),
            simulationBudget = root.optInt("simulationBudget", BetStrategy.DEFAULT_BUDGET),
            oddsFinalGateIncluded = root.optBoolean("oddsFinalGateIncluded", false),
            method = root.optString("method"),
            months = months,
            yearSummary = parsePeriod(summaryObj, year, null)
        )
    }

    private fun parsePeriod(obj: JSONObject, year: Int, month: Int?): HistoricalBacktestPeriod =
        HistoricalBacktestPeriod(
            year = year,
            month = month,
            totalSettledRaces = obj.optInt("totalSettledRaces"),
            evaluatedRaces = obj.optInt("evaluatedRaces"),
            purchaseRaces = obj.optInt("purchaseRaces"),
            skippedRaces = obj.optInt("skippedRaces"),
            unavailableRaces = obj.optInt("unavailableRaces"),
            purchaseHits = obj.optInt("purchaseHits"),
            allPredictionHits = obj.optInt("allPredictionHits"),
            skippedPredictionHits = obj.optInt("skippedPredictionHits"),
            stake = obj.optInt("stake"),
            payout = obj.optInt("payout"),
            profit = obj.optInt("profit"),
            roi = obj.optDouble("roi"),
            hitRate = obj.optDouble("hitRate"),
            purchaseRate = obj.optDouble("purchaseRate")
        )

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
