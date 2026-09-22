package jp.boatai.app

import android.content.Context

class VersionDataResetManager(private val context: Context) {
    fun resetIfVersionChanged(): Boolean {
        val meta = context.getSharedPreferences(META_PREFS, Context.MODE_PRIVATE)
        val previousVersionCode = meta.getInt(KEY_LAST_VERSION_CODE, -1)
        val memoryStore = PerformanceMemoryStore(context)

        if (previousVersionCode == BuildConfig.VERSION_CODE) {
            PredictionEngine.installPersistentPerformanceProfile(memoryStore.load())
            return false
        }

        // 表示する実績は予想ロジックのバージョンごとに0から評価する。
        // 一方、旧バージョンで確定した予想成績から得た弱点補正は内部メモリへ退避し、
        // 5年分ベースライン・端末内レース学習と同様に予想品質の土台として引き継ぐ。
        val oldPredictions = PredictionHistoryStore(context).load()
        val persistentProfile = if (oldPredictions.isNotEmpty()) {
            memoryStore.mergeFrom(oldPredictions)
        } else {
            memoryStore.load()
        }
        PredictionEngine.installPersistentPerformanceProfile(persistentProfile)

        context.getSharedPreferences("boat_ai_bets", Context.MODE_PRIVATE)
            .edit()
            .remove("records")
            .commit()
        context.getSharedPreferences("boat_ai_predictions", Context.MODE_PRIVATE)
            .edit()
            .remove("prediction_records")
            .commit()

        meta.edit()
            .putInt(KEY_LAST_VERSION_CODE, BuildConfig.VERSION_CODE)
            .putString(KEY_LAST_VERSION_NAME, BuildConfig.VERSION_NAME)
            .putLong(KEY_LAST_RESET_AT, System.currentTimeMillis())
            .commit()
        return true
    }

    companion object {
        private const val META_PREFS = "boat_ai_app_meta"
        private const val KEY_LAST_VERSION_CODE = "history_version_code"
        private const val KEY_LAST_VERSION_NAME = "history_version_name"
        private const val KEY_LAST_RESET_AT = "history_reset_at"
    }
}
