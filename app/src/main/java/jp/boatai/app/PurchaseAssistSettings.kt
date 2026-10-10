package jp.boatai.app

import android.content.Context

class PurchaseAssistSettings(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    val autoPrepareEnabled: Boolean
        get() = prefs.getBoolean(KEY_AUTO_PREPARE, false)

    fun setAutoPrepareEnabled(value: Boolean) {
        prefs.edit().putBoolean(KEY_AUTO_PREPARE, value).apply()
    }

    companion object {
        private const val PREFS = "boat_ai_purchase_assist"
        private const val KEY_AUTO_PREPARE = "auto_prepare_enabled"
    }
}
