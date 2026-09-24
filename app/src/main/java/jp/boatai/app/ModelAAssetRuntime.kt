package jp.boatai.app

import android.content.Context
import java.io.File
import java.time.LocalDate

/** Production asset/persistence boundary for the frozen v0.16 forecast-only Model A. */
internal class ModelAAssetRuntime private constructor(
    private val context: Context,
    private val history: ModelAPlayerHistory,
    private val runtime: ModelAForecastRuntime
) {
    private val updater = ModelAHistoryDayUpdater(history)

    val historyLastDay: Int get() = history.lastDay
    val historyLastDate: LocalDate
        get() = LocalDate.ofEpochDay(history.lastDay.toLong() - PYTHON_ORDINAL_AT_UNIX_EPOCH)

    @Synchronized
    fun forecast(race: RaceData): ModelAForecastRuntime.Result = runtime.forecast(race)

    @Synchronized
    fun commitFetchedDay(date: LocalDate, races: List<RaceData>): ModelAHistoryDayUpdater.Summary {
        val summary = updater.commitFetchedDay(date, races)
        persist()
        return summary
    }

    private fun persist() {
        val target = File(context.filesDir, PERSISTED_HISTORY)
        val tmp = File(context.filesDir, "$PERSISTED_HISTORY.tmp")
        val bytes = ModelAHistoryStateCodec.encode(history.exportState())
        tmp.outputStream().use { output ->
            output.write(bytes)
            output.fd.sync()
        }
        if (target.exists() && !target.delete()) error("Could not replace Model A history state")
        if (!tmp.renameTo(target)) error("Could not atomically install Model A history state")
    }

    companion object {
        private const val HISTORY_ASSET = "model_a_history.bin"
        private const val STAGE0_ASSET = "model_a_stage0.txt"
        private const val STAGE1_ASSET = "model_a_stage1.txt"
        private const val STAGE2_ASSET = "model_a_stage2.txt"
        private const val PERSISTED_HISTORY = "model_a_history.bin"
        private const val PYTHON_ORDINAL_AT_UNIX_EPOCH = 719_163L

        fun load(context: Context): ModelAAssetRuntime? = runCatching {
            val assetBytes = context.assets.open(HISTORY_ASSET).use { it.readBytes() }
            val assetState = ModelAHistoryStateCodec.decode(assetBytes)
            val persisted = File(context.filesDir, PERSISTED_HISTORY)
            val state = if (persisted.isFile) {
                runCatching { ModelAHistoryStateCodec.decode(persisted.readBytes()) }
                    .getOrNull()
                    ?.takeIf { it.lastDay >= assetState.lastDay }
                    ?: assetState
            } else assetState

            val stage0 = LightGbmTextModel.parse(context.assets.open(STAGE0_ASSET).bufferedReader().use { it.readText() })
            val stage1 = LightGbmTextModel.parse(context.assets.open(STAGE1_ASSET).bufferedReader().use { it.readText() })
            val stage2 = LightGbmTextModel.parse(context.assets.open(STAGE2_ASSET).bufferedReader().use { it.readText() })
            val history = ModelAPlayerHistory(state)
            ModelAAssetRuntime(
                context = context.applicationContext,
                history = history,
                runtime = ModelAForecastRuntime(history, stage0, stage1, stage2)
            )
        }.getOrNull()
    }
}
