package jp.boatai.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Small local diagnostic trail included in a user-initiated backup, not uploaded. */
class DataFetchAuditStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    @Synchronized
    fun record(source: String, status: String, detail: String) {
        runCatching {
            val entry = JSONObject().apply {
                put("at", System.currentTimeMillis())
                put("appVersion", BuildConfig.VERSION_NAME)
                put("source", source.take(64))
                put("status", status.take(16))
                put("detail", detail.take(MAX_DETAIL_CHARS))
            }
            val previous = runCatching { JSONArray(prefs.getString(KEY_EVENTS, "[]")) }
                .getOrDefault(JSONArray())
            val updated = DataFetchAuditWindow.append(previous, entry)
            prefs.edit().putString(KEY_EVENTS, updated.toString()).apply()
        }
    }

    fun snapshot(): JSONObject {
        val recent = runCatching { JSONArray(prefs.getString(KEY_EVENTS, "[]")) }
            .getOrDefault(JSONArray())
        return JSONObject().apply {
            put("recent", recent)
            put("windowSize", recent.length())
            put("maxWindowSize", DataFetchAuditWindow.MAX_EVENTS)
        }
    }

    companion object {
        private const val PREFS = "boat_ai_data_fetch_audit"
        private const val KEY_EVENTS = "recent_events"
        private const val MAX_DETAIL_CHARS = 240
    }
}

/** JVM-testable bounded ring; failures retain their original details. */
internal object DataFetchAuditWindow {
    const val MAX_EVENTS = 48

    fun append(previous: JSONArray, event: JSONObject): JSONArray = JSONArray().apply {
        val first = (previous.length() - MAX_EVENTS + 1).coerceAtLeast(0)
        for (index in first until previous.length()) put(previous.getJSONObject(index))
        put(event)
    }
}
