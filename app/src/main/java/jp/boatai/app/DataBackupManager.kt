package jp.boatai.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.Instant

class DataBackupManager(private val context: Context) {
    fun backupJson(): String {
        val bets = context.getSharedPreferences("boat_ai_bets", Context.MODE_PRIVATE)
            .getString("records", "[]") ?: "[]"
        val predictions = context.getSharedPreferences("boat_ai_predictions", Context.MODE_PRIVATE)
            .getString("prediction_records", "[]") ?: "[]"
        val learningPrefs = context.getSharedPreferences("boat_ai_learning", Context.MODE_PRIVATE)
        val learning = learningPrefs.getString("profile", "{}") ?: "{}"
        return JSONObject().apply {
            put("schemaVersion", 1)
            put("appVersion", BuildConfig.VERSION_NAME)
            put("exportedAt", Instant.now().toString())
            put("bets", JSONArray(bets))
            put("predictions", JSONArray(predictions))
            put("learning", JSONObject(learning))
            put("historicalBaselineMigratedThrough", learningPrefs.getString("historical_baseline_migrated_through", ""))
        }.toString(2)
    }

    fun restore(uri: Uri): RestoreSummary {
        val text = context.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
            ?: error("バックアップを読み込めません")
        val root = JSONObject(text)
        require(root.optInt("schemaVersion") == 1) { "未対応のバックアップ形式です" }
        val bets = root.getJSONArray("bets")
        val predictions = root.getJSONArray("predictions")
        val learning = root.getJSONObject("learning")

        repeat(bets.length()) { BetRecord.fromJson(bets.getJSONObject(it)) }
        repeat(predictions.length()) { PredictionRecord.fromJson(predictions.getJSONObject(it)) }

        context.getSharedPreferences("boat_ai_bets", Context.MODE_PRIVATE)
            .edit().putString("records", bets.toString()).commit()
        context.getSharedPreferences("boat_ai_predictions", Context.MODE_PRIVATE)
            .edit().putString("prediction_records", predictions.toString()).commit()
        context.getSharedPreferences("boat_ai_learning", Context.MODE_PRIVATE).edit()
            .putString("profile", learning.toString())
            .putString("historical_baseline_migrated_through", root.optString("historicalBaselineMigratedThrough"))
            .commit()
        return RestoreSummary(bets.length(), predictions.length())
    }

    fun csv(): String {
        val bets = BetStore(context).load()
        val predictions = PredictionHistoryStore(context).load()
        val rows = mutableListOf(
            listOf("種別", "日付", "場", "R", "買い目", "購入額", "払戻", "収支", "的中", "購入判定", "判定理由")
        )
        bets.forEach { record ->
            rows += listOf(
                "実購入", record.date, record.venueName, record.raceNumber.toString(), record.combination,
                record.stake.toString(), record.payout.toString(), record.profit.toString(),
                if (record.payout > 0) "的中" else if (record.settled) "不的中" else "結果待ち", "", ""
            )
        }
        predictions.forEach { record ->
            rows += listOf(
                "AI予想", record.date, record.venueName, record.raceNumber.toString(), record.combinations.joinToString("/"),
                record.simulatedStake.toString(), record.simulatedPayout.toString(), record.simulatedProfit.toString(),
                if (record.hit) "的中" else if (record.settled) "不的中" else "結果待ち",
                record.recommendation.label,
                record.recommendationReason.orEmpty()
            )
        }
        return "\uFEFF" + rows.joinToString("\r\n") { row -> row.joinToString(",") { csvCell(it) } }
    }

    fun shareBackup() = share("BOAT-AI-backup.json", "application/json", backupJson())
    fun shareCsv() = share("BOAT-AI-history.csv", "text/csv", csv())

    private fun share(name: String, mime: String, contents: String) {
        val directory = File(context.cacheDir, "exports").apply { mkdirs() }
        val file = File(directory, name).apply { writeText(contents, Charsets.UTF_8) }
        val uri = FileProvider.getUriForFile(context, "${BuildConfig.APPLICATION_ID}.fileprovider", file)
        context.startActivity(
            Intent.createChooser(
                Intent(Intent.ACTION_SEND).apply {
                    type = mime
                    putExtra(Intent.EXTRA_STREAM, uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                },
                "保存・共有先を選択"
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }

    private fun csvCell(value: String): String = "\"${value.replace("\"", "\"\"")}\""
}

data class RestoreSummary(val bets: Int, val predictions: Int)
