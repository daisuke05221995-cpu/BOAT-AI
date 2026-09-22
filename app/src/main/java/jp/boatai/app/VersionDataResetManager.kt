package jp.boatai.app

import android.content.Context

class VersionDataResetManager(private val context: Context) {
    fun resetIfVersionChanged(): Boolean {
        val meta = context.getSharedPreferences(META_PREFS, Context.MODE_PRIVATE)
        val previousVersionCode = meta.getInt(KEY_LAST_VERSION_CODE, -1)
        if (previousVersionCode == BuildConfig.VERSION_CODE) return false

        // 予想成績と実購入履歴は予想ロジックのバージョンごとに評価する。
        // 学習プロファイルと5年分ベースラインは品質向上の土台なので保持する。
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
