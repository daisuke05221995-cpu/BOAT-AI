package jp.boatai.app

import android.content.Context
import org.json.JSONObject

class PerformanceMemoryStore(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun load(): PredictionPerformanceProfile {
        val raw = prefs.getString(KEY, null) ?: return PredictionPerformanceProfile()
        return runCatching { profileFromJson(JSONObject(raw)) }
            .getOrDefault(PredictionPerformanceProfile())
    }

    fun mergeFrom(records: List<PredictionRecord>): PredictionPerformanceProfile {
        val learned = PredictionPerformanceProfile.from(records)
        val merged = load().mergedWith(learned)
        save(merged)
        return merged
    }

    private fun save(profile: PredictionPerformanceProfile) {
        prefs.edit().putString(KEY, profileToJson(profile).toString()).commit()
    }

    private fun profileToJson(profile: PredictionPerformanceProfile) = JSONObject().apply {
        put("overall", statsToJson(profile.overall))
        put("byRank", mapToJson(profile.byRank) { it })
        put("byVenue", mapToJson(profile.byVenue) { it.toString() })
        put("byFirstLane", mapToJson(profile.byFirstLane) { it.toString() })
        put("byContext", mapToJson(profile.byContext) { it })
    }

    private fun profileFromJson(root: JSONObject) = PredictionPerformanceProfile(
        overall = statsFromJson(root.optJSONObject("overall")),
        byRank = statsMap(root.optJSONObject("byRank")) { it },
        byVenue = statsMap(root.optJSONObject("byVenue")) { it.toIntOrNull() },
        byFirstLane = statsMap(root.optJSONObject("byFirstLane")) { it.toIntOrNull() },
        byContext = statsMap(root.optJSONObject("byContext")) { it }
    )

    private fun statsToJson(stats: PredictionPerformanceStats) = JSONObject().apply {
        put("races", stats.races)
        put("hits", stats.hits)
        put("stake", stats.stake)
        put("payout", stats.payout)
    }

    private fun statsFromJson(obj: JSONObject?): PredictionPerformanceStats =
        if (obj == null) PredictionPerformanceStats() else PredictionPerformanceStats(
            races = obj.optInt("races"),
            hits = obj.optInt("hits"),
            stake = obj.optInt("stake"),
            payout = obj.optInt("payout")
        )

    private fun <K> mapToJson(
        values: Map<K, PredictionPerformanceStats>,
        key: (K) -> String
    ) = JSONObject().apply {
        values.forEach { (name, stats) -> put(key(name), statsToJson(stats)) }
    }

    private fun <K : Any> statsMap(
        obj: JSONObject?,
        keyParser: (String) -> K?
    ): Map<K, PredictionPerformanceStats> {
        if (obj == null) return emptyMap()
        return buildMap {
            obj.keys().forEach { rawKey ->
                val key = keyParser(rawKey) ?: return@forEach
                put(key, statsFromJson(obj.optJSONObject(rawKey)))
            }
        }
    }

    companion object {
        private const val PREFS = "boat_ai_performance_memory"
        private const val KEY = "profile"
    }
}
