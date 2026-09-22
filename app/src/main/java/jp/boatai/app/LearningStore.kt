package jp.boatai.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

data class LearningProfile(
    val observedRaceIds: Set<String> = emptySet(),
    val starts: Map<String, Int> = emptyMap(),
    val wins: Map<String, Int> = emptyMap()
) {
    fun bonus(stadium: Int, lane: Int): Double {
        val key = "$stadium-$lane"
        val baseline = listOf(0.55, 0.15, 0.12, 0.10, 0.05, 0.03)[lane - 1]
        val count = starts[key] ?: 0
        val won = wins[key] ?: 0
        val posterior = (won + baseline * 12.0) / (count + 12.0)
        return ((posterior - baseline) * 40.0).coerceIn(-8.0, 8.0)
    }
}

class LearningStore(context: Context) {
    private val prefs = context.getSharedPreferences("boat_ai_learning", Context.MODE_PRIVATE)

    fun load(): LearningProfile = runCatching {
        val root = JSONObject(prefs.getString(KEY, "{}") ?: "{}")
        LearningProfile(
            observedRaceIds = root.optJSONArray("observed")?.stringSet().orEmpty(),
            starts = root.optJSONObject("starts").intMap(),
            wins = root.optJSONObject("wins").intMap()
        )
    }.getOrDefault(LearningProfile())

    fun observe(races: List<RaceData>): LearningProfile {
        val current = load()
        val observed = current.observedRaceIds.toMutableSet()
        val starts = current.starts.toMutableMap()
        val wins = current.wins.toMutableMap()
        var changed = false
        races.filter { it.hasResult && it.id !in observed }.forEach { race ->
            val winner = race.result?.trifectaCombination?.substringBefore("-")?.toIntOrNull()
                ?: return@forEach
            (1..6).forEach { lane ->
                val key = "${race.stadiumNumber}-$lane"
                starts[key] = (starts[key] ?: 0) + 1
            }
            val winnerKey = "${race.stadiumNumber}-$winner"
            wins[winnerKey] = (wins[winnerKey] ?: 0) + 1
            observed += race.id
            changed = true
        }
        val next = LearningProfile(observed, starts, wins)
        if (changed) save(next)
        return next
    }

    private fun save(profile: LearningProfile) {
        val root = JSONObject().apply {
            put("observed", JSONArray(profile.observedRaceIds.toList()))
            put("starts", JSONObject(profile.starts))
            put("wins", JSONObject(profile.wins))
        }
        prefs.edit().putString(KEY, root.toString()).apply()
    }

    private fun JSONArray.stringSet(): Set<String> = buildSet {
        for (index in 0 until length()) optString(index).takeIf(String::isNotBlank)?.let(::add)
    }

    private fun JSONObject?.intMap(): Map<String, Int> {
        if (this == null) return emptyMap()
        return keys().asSequence().associateWith { optInt(it) }
    }

    companion object { private const val KEY = "profile" }
}
