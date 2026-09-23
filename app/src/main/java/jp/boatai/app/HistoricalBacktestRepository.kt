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
        .getSharedPreferences("boat_ai_historical_backtest_v12", Context.MODE_PRIVATE)

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
            error = remote.exceptionOrNull()?.message ?: "過去戦略検証データを取得できませんでした"
        )
    }

    private fun parse(text: String): HistoricalBacktestData {
        val root = JSONObject(text)
        require(root.optInt("schemaVersion") >= 12) { "v12以降の戦略検証データが必要です" }
        val operationMonths = root.optJSONObject("operationMonths")
            ?: throw IllegalArgumentException("operationMonths がありません")
        val oddsCoverage = root.optJSONObject("oddsCoverage")
        val signals = oddsCoverage?.optJSONObject("signals")
        val missing = oddsCoverage?.optJSONObject("missingRaces")
        val dataThrough = root.optString("dataThrough")
        val year = dataThrough.take(4).toIntOrNull() ?: 2026
        val lastMonth = dataThrough.takeIf { it.length >= 7 }?.substring(5, 7)?.toIntOrNull()?.coerceIn(1, 12) ?: 12

        val months = (1..lastMonth).map { month ->
            val key = "%04d-%02d".format(year, month)
            val stats = operationMonths.optJSONObject(key)
            if (stats == null) {
                HistoricalBacktestPeriod(
                    year = year,
                    month = month,
                    purchaseRaces = 0,
                    skippedRaces = 0,
                    unavailableRaces = 0,
                    purchaseHits = 0,
                    stake = 0,
                    payout = 0,
                    profit = 0,
                    roi = 0.0,
                    hitRate = 0.0,
                    purchaseRate = 0.0,
                    evaluatedRaces = 0,
                    phase = if (month <= 4) "学習・校正期間" else "未集計",
                    statsAvailable = false
                )
            } else {
                val evaluated = signals?.optInt(key, 0) ?: 0
                val purchases = stats.optInt("purchaseRaces")
                HistoricalBacktestPeriod(
                    year = year,
                    month = month,
                    purchaseRaces = purchases,
                    skippedRaces = (evaluated - purchases).coerceAtLeast(0),
                    unavailableRaces = missing?.optInt(key, 0) ?: 0,
                    purchaseHits = stats.optInt("hits"),
                    stake = stats.optInt("stake"),
                    payout = stats.optInt("payout"),
                    profit = stats.optInt("profit"),
                    roi = stats.optDouble("roi"),
                    hitRate = stats.optDouble("hitRate"),
                    purchaseRate = if (evaluated > 0) purchases * 100.0 / evaluated else 0.0,
                    evaluatedRaces = evaluated,
                    phase = "運用検証",
                    statsAvailable = true
                )
            }
        }

        val operation = root.optJSONObject("operation")
            ?: throw IllegalArgumentException("operation がありません")
        val validMonths = months.filter { it.statsAvailable }
        val evaluatedTotal = validMonths.sumOf { it.evaluatedRaces }
        val purchaseTotal = operation.optInt("purchaseRaces")
        val yearSummary = HistoricalBacktestPeriod(
            year = year,
            month = null,
            purchaseRaces = purchaseTotal,
            skippedRaces = (evaluatedTotal - purchaseTotal).coerceAtLeast(0),
            unavailableRaces = validMonths.sumOf { it.unavailableRaces },
            purchaseHits = operation.optInt("hits"),
            stake = operation.optInt("stake"),
            payout = operation.optInt("payout"),
            profit = operation.optInt("profit"),
            roi = operation.optDouble("roi"),
            hitRate = operation.optDouble("hitRate"),
            purchaseRate = if (evaluatedTotal > 0) purchaseTotal * 100.0 / evaluatedTotal else 0.0,
            evaluatedRaces = evaluatedTotal,
            phase = "運用検証期間合計",
            statsAvailable = true
        )

        return HistoricalBacktestData(
            year = year,
            generatedAt = root.optString("generatedAt"),
            dataFrom = "%04d-05-01".format(year),
            dataThrough = dataThrough,
            simulationBudget = root.optJSONObject("nextLiveConfig")?.optInt("budget", BetStrategy.DEFAULT_BUDGET)
                ?: BetStrategy.DEFAULT_BUDGET,
            oddsFinalGateIncluded = root.optBoolean("oddsFinalGateIncluded", false),
            method = root.optString("method"),
            months = months,
            yearSummary = yearSummary,
            historicalCriteriaMet = root.optBoolean("historicalCriteriaMet", false),
            releaseDeferredForIndependentValidation = root.optBoolean("releaseDeferredForIndependentValidation", true)
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
            "https://raw.githubusercontent.com/daisuke05221995-cpu/BOAT-AI/main/data/strategy_search_2026.json"
    }
}
