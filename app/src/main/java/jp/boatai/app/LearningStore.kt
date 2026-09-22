package jp.boatai.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate

data class LearningProfile(
    val observedRaceIds: Set<String> = emptySet(),
    val starts: Map<String, Int> = emptyMap(),
    val wins: Map<String, Int> = emptyMap(),
    val windCourseStarts: Map<String, Int> = emptyMap(),
    val windCourseWins: Map<String, Int> = emptyMap(),
    val historicalRaceCount: Int = 0,
    val trainedThrough: String? = null
) {
    val totalRaceCount: Int get() = historicalRaceCount + observedRaceIds.size

    fun bonus(stadium: Int, lane: Int): Double {
        val safeLane = lane.coerceIn(1, 6)
        val key = "$stadium-$safeLane"
        val baseline = listOf(0.55, 0.15, 0.12, 0.10, 0.05, 0.03)[safeLane - 1]
        val count = starts[key] ?: 0
        val won = wins[key] ?: 0
        val posterior = (won + baseline * 12.0) / (count + 12.0)
        return ((posterior - baseline) * 40.0).coerceIn(-8.0, 8.0)
    }

    fun bonus(race: RaceData, racer: Racer): Double {
        val venueLane = bonus(race.stadiumNumber, racer.lane)
        val wind = race.preview?.windSpeed ?: return venueLane
        val actualCourse = racer.preview?.course?.takeIf { it in 1..6 } ?: racer.lane.coerceIn(1, 6)
        val key = windCourseKey(race.stadiumNumber, wind, actualCourse)
        val count = windCourseStarts[key] ?: 0
        if (count < 4) return venueLane

        val won = windCourseWins[key] ?: 0
        val baseline = listOf(0.55, 0.15, 0.12, 0.10, 0.05, 0.03)[actualCourse - 1]
        val posterior = (won + baseline * 10.0) / (count + 10.0)
        val contextual = ((posterior - baseline) * 30.0).coerceIn(-5.0, 5.0)
        return (venueLane + contextual).coerceIn(-10.0, 10.0)
    }

    companion object {
        internal fun windBucket(windSpeed: Int): String = when {
            windSpeed <= 2 -> "0-2"
            windSpeed <= 4 -> "3-4"
            else -> "5+"
        }

        internal fun windCourseKey(stadium: Int, windSpeed: Int, course: Int): String =
            "$stadium-${windBucket(windSpeed)}-${course.coerceIn(1, 6)}"
    }
}

class LearningStore(context: Context) {
    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences("boat_ai_learning", Context.MODE_PRIVATE)
    private val historicalBaseline: LearningProfile by lazy { loadHistoricalBaseline() }

    init {
        migrateLocalLearningForHistoricalBaseline()
    }

    fun load(): LearningProfile = mergeProfiles(historicalBaseline, loadLocal())

    fun observe(races: List<RaceData>): LearningProfile {
        val baseline = historicalBaseline
        val current = loadLocal()
        val observed = current.observedRaceIds.toMutableSet()
        val starts = current.starts.toMutableMap()
        val wins = current.wins.toMutableMap()
        val windCourseStarts = current.windCourseStarts.toMutableMap()
        val windCourseWins = current.windCourseWins.toMutableMap()
        var changed = false

        races.filter {
            it.hasResult &&
                it.id !in observed &&
                isAfterHistoricalBaseline(it.date, baseline.trainedThrough)
        }.forEach { race ->
            val winnerLane = race.result?.trifectaCombination?.substringBefore("-")?.toIntOrNull()
                ?.takeIf { it in 1..6 } ?: return@forEach

            (1..6).forEach { lane ->
                val key = "${race.stadiumNumber}-$lane"
                starts[key] = (starts[key] ?: 0) + 1
            }
            val winnerKey = "${race.stadiumNumber}-$winnerLane"
            wins[winnerKey] = (wins[winnerKey] ?: 0) + 1

            race.preview?.windSpeed?.let { windSpeed ->
                race.racers.forEach { racer ->
                    val actualCourse = racer.preview?.course?.takeIf { it in 1..6 } ?: racer.lane
                    if (actualCourse in 1..6) {
                        val key = LearningProfile.windCourseKey(race.stadiumNumber, windSpeed, actualCourse)
                        windCourseStarts[key] = (windCourseStarts[key] ?: 0) + 1
                    }
                }
                val winner = race.racers.firstOrNull { it.lane == winnerLane }
                val winningCourse = winner?.preview?.course?.takeIf { it in 1..6 } ?: winnerLane
                val key = LearningProfile.windCourseKey(race.stadiumNumber, windSpeed, winningCourse)
                windCourseWins[key] = (windCourseWins[key] ?: 0) + 1
            }

            observed += race.id
            changed = true
        }

        val nextLocal = LearningProfile(
            observedRaceIds = observed,
            starts = starts,
            wins = wins,
            windCourseStarts = windCourseStarts,
            windCourseWins = windCourseWins
        )
        if (changed) saveLocal(nextLocal)
        return mergeProfiles(baseline, nextLocal)
    }

    private fun loadHistoricalBaseline(): LearningProfile = runCatching {
        val text = appContext.assets.open(HISTORICAL_ASSET).bufferedReader().use { it.readText() }
        val root = JSONObject(text)
        LearningProfile(
            starts = root.optJSONObject("starts").intMap(),
            wins = root.optJSONObject("wins").intMap(),
            windCourseStarts = root.optJSONObject("windCourseStarts").intMap(),
            windCourseWins = root.optJSONObject("windCourseWins").intMap(),
            historicalRaceCount = root.optInt("historicalRaceCount", 0).coerceAtLeast(0),
            trainedThrough = root.optString("trainedThrough").trim().takeIf { it.isNotBlank() }
        )
    }.getOrDefault(LearningProfile())

    private fun loadLocal(): LearningProfile = runCatching {
        val root = JSONObject(prefs.getString(KEY, "{}") ?: "{}")
        LearningProfile(
            observedRaceIds = root.optJSONArray("observed")?.stringSet().orEmpty(),
            starts = root.optJSONObject("starts").intMap(),
            wins = root.optJSONObject("wins").intMap(),
            windCourseStarts = root.optJSONObject("windCourseStarts").intMap(),
            windCourseWins = root.optJSONObject("windCourseWins").intMap()
        )
    }.getOrDefault(LearningProfile())

    private fun migrateLocalLearningForHistoricalBaseline() {
        val through = historicalBaseline.trainedThrough ?: return
        if (prefs.getString(BASELINE_MIGRATION_KEY, null) == through) return

        val local = loadLocal()
        val overlapsBaseline = local.observedRaceIds.any { raceId ->
            val raceDate = parseDate(raceId.take(10))
            val baselineDate = parseDate(through)
            raceDate != null && baselineDate != null && !raceDate.isAfter(baselineDate)
        }

        val editor = prefs.edit()
        if (overlapsBaseline) editor.remove(KEY)
        editor.putString(BASELINE_MIGRATION_KEY, through).apply()
    }

    private fun mergeProfiles(base: LearningProfile, local: LearningProfile): LearningProfile =
        LearningProfile(
            observedRaceIds = local.observedRaceIds,
            starts = mergeCounts(base.starts, local.starts),
            wins = mergeCounts(base.wins, local.wins),
            windCourseStarts = mergeCounts(base.windCourseStarts, local.windCourseStarts),
            windCourseWins = mergeCounts(base.windCourseWins, local.windCourseWins),
            historicalRaceCount = base.historicalRaceCount,
            trainedThrough = base.trainedThrough
        )

    private fun mergeCounts(base: Map<String, Int>, local: Map<String, Int>): Map<String, Int> {
        if (base.isEmpty()) return local
        if (local.isEmpty()) return base
        return buildMap {
            putAll(base)
            local.forEach { (key, value) -> put(key, (get(key) ?: 0) + value) }
        }
    }

    private fun isAfterHistoricalBaseline(raceDateText: String, trainedThrough: String?): Boolean {
        val through = trainedThrough ?: return true
        val raceDate = parseDate(raceDateText.take(10)) ?: return true
        val baselineDate = parseDate(through) ?: return true
        return raceDate.isAfter(baselineDate)
    }

    private fun parseDate(value: String): LocalDate? = runCatching { LocalDate.parse(value) }.getOrNull()

    private fun saveLocal(profile: LearningProfile) {
        val root = JSONObject().apply {
            put("observed", JSONArray(profile.observedRaceIds.toList()))
            put("starts", JSONObject(profile.starts))
            put("wins", JSONObject(profile.wins))
            put("windCourseStarts", JSONObject(profile.windCourseStarts))
            put("windCourseWins", JSONObject(profile.windCourseWins))
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

    companion object {
        private const val KEY = "profile"
        private const val BASELINE_MIGRATION_KEY = "historical_baseline_migrated_through"
        private const val HISTORICAL_ASSET = "historical_learning.json"
    }
}
