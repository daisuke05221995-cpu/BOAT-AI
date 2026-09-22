package jp.boatai.app

import android.content.Context

class VersionDataResetManager(private val context: Context) {
    fun resetIfVersionChanged(): Boolean {
        val meta = context.getSharedPreferences(META_PREFS, Context.MODE_PRIVATE)
        val previousVersionCode = meta.getInt(KEY_LAST_VERSION_CODE, -1)
        val memoryStore = PerformanceMemoryStore(context)

        PredictionEngine.installPersistentPerformanceProfile(memoryStore.load())
        if (previousVersionCode == BuildConfig.VERSION_CODE) return false

        // v0.14.0以降は通常アップデートで予想実績・実購入履歴を削除しない。
        // 週間/月間累計を継続して追えることを優先し、互換性破壊が必要な場合だけ
        // 別の明示的マイグレーションを追加する。
        meta.edit()
            .putInt(KEY_LAST_VERSION_CODE, BuildConfig.VERSION_CODE)
            .putString(KEY_LAST_VERSION_NAME, BuildConfig.VERSION_NAME)
            .putLong(KEY_LAST_RESET_AT, System.currentTimeMillis())
            .commit()
        return false
    }

    companion object {
        private const val META_PREFS = "boat_ai_app_meta"
        private const val KEY_LAST_VERSION_CODE = "history_version_code"
        private const val KEY_LAST_VERSION_NAME = "history_version_name"
        private const val KEY_LAST_RESET_AT = "history_reset_at"
    }
}
