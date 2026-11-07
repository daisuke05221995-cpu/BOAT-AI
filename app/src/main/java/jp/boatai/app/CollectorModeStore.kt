package jp.boatai.app

import android.content.Context
import java.time.LocalDate

/** Device-local setting. Never restored from another phone's purchase backup. */
internal class CollectorModeStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun isEnabled(): Boolean = prefs.getBoolean(KEY_ENABLED, false)

    fun setEnabled(enabled: Boolean) {
        prefs.edit().putBoolean(KEY_ENABLED, enabled).apply()
    }

    private companion object {
        const val PREFS = "boat_ai_dedicated_collector_v1"
        const val KEY_ENABLED = "enabled"
    }
}

/** Pure policy shared by the foreground refresh loop and its regression tests. */
internal object CollectorModePolicy {
    fun needsTodayReload(enabled: Boolean, selectedDate: LocalDate, today: LocalDate): Boolean =
        enabled && selectedDate != today
}
