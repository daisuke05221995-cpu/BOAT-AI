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
    val trainedFrom: String? = null,
    val trainedThrough: String? = null
) {
    val localRaceCount: Int get() = observedRaceIds.size
    val totalRaceCount: Int get() = historicalRaceCount + localRaceCount

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

    fun mergedWith(overlay: LearningProfile): LearningProfile = LearningProfile(
        observedRaceIds = observedRaceIds + overlay.observedRaceIds,
        starts = mergeCountMaps(starts, overlay.starts),
        wins = mergeCountMaps(wins, overlay.wins),
        windCourseStarts = mergeCountMaps(windCourseStarts, overlay.windCourseStarts),
        windCourseWins = mergeCountMaps(windCourseWins, overlay.windCourseWins),
        historicalRaceCount = historicalRaceCount + overlay.historicalRaceCount,
        trainedFrom = trainedFrom ?: overlay.trainedFrom,
        trainedThrough = trainedThrough ?: overlay.trainedThrough
    )

    companion object {
        internal fun windBucket(windSpeed: Int): String = when {
            windSpeed <= 2 -> "0-2"
            windSpeed <= 4 -> "3-4"
            else -> "5+"
        }

        internal fun windCourseKey(stadium: Int, windSpeed: Int, course: Int): String =
            "$stadium-${windBucket(windSpeed)}-${course.coerceIn(1, 6)}"

        private fun mergeCountMaps(first: Map<String, Int>, second: Map<String, Int>): Map<String, Int> =
            buildMap {
                first.forEach { (key, value) -> put(key, value) }
                second.forEach { (key, value) -> put(key, (get(key) ?: 0) + value) }
            }
    }
}

class LearningStore(context: Context) {
    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences("boat_ai_learning", Context.MODE_PRIVATE)
    private val historicalBaseline: LearningProfile by lazy { loadHistoricalBaseline() }

    init {
        migrateLegacyLocalIfNeeded()
    }

    fun load(): LearningProfile = historicalBaseline.mergedWith(loadLocal())

    fun observe(races: List<RaceData>): LearningProfile {
        val current = loadLocal()
        val observed = current.observedRaceIds.toMutableSet()
        val starts = current.starts.toMutableMap()
        val wins = current.wins.toMutableMap()
        val windCourseStarts = current.windCourseStarts.toMutableMap()
        val windCourseWins = current.windCourseWins.toMutableMap()
        var changed = false

        races.filter { race ->
            race.hasResult && race.id !in observed && !isCoveredByHistoricalBaseline(race.date)
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
        return historicalBaseline.mergedWith(nextLocal)
    }

    fun exportLocalBackup(): String {
        val root = JSONObject().apply {
            put("type", BACKUP_TYPE)
            put("schemaVersion", 1)
            put("historicalBaselineThrough", historicalBaseline.trainedThrough)
            put("profile", profileToJson(loadLocal()))
        }
        return root.toString(2)
    }

    fun importLocalBackup(raw: String): LearningProfile {
        val root = JSONObject(raw)
        require(root.optString("type") == BACKUP_TYPE) { "BOAT AIの学習バックアップではありません" }
        require(root.optInt("schemaVersion") == 1) { "未対応のバックアップ形式です" }
        val profile = profileFromJson(root.getJSONObject("profile"), includeHistoricalMetadata = false)
        validateLocalProfile(profile)
        saveLocal(profile)
        return historicalBaseline.mergedWith(profile)
    }

    fun clearLocal(): LearningProfile {
        prefs.edit().remove(KEY).apply()
        return historicalBaseline
    }

    private fun loadLocal(): LearningProfile = runCatching {
        profileFromJson(JSONObject(prefs.getString(KEY, "{}") ?: "{}"), includeHistoricalMetadata = false)
    }.getOrDefault(LearningProfile())

    private fun loadHistoricalBaseline(): LearningProfile = runCatching {
        val raw = appContext.assets.open(HISTORICAL_ASSET).bufferedReader(Charsets.UTF_8).use { it.readText() }
        profileFromJson(JSONObject(raw), includeHistoricalMetadata = true)
    }.getOrDefault(LearningProfile())

    private fun profileFromJson(root: JSONObject, includeHistoricalMetadata: Boolean): LearningProfile = LearningProfile(
        observedRaceIds = root.optJSONArray("observed")?.stringSet().orEmpty(),
        starts = root.optJSONObject("starts").intMap(),
        wins = root.optJSONObject("wins").intMap(),
        windCourseStarts = root.optJSONObject("windCourseStarts").intMap(),
        windCourseWins = root.optJSONObject("windCourseWins").intMap(),
        historicalRaceCount = if (includeHistoricalMetadata) root.optInt("historicalRaceCount") else 0,
        trainedFrom = if (includeHistoricalMetadata) root.optString("trainedFrom").takeIf(String::isNotBlank) else null,
        trainedThrough = if (includeHistoricalMetadata) root.optString("trainedThrough").takeIf(String::isNotBlank) else null
    )

    private fun profileToJson(profile: LearningProfile): JSONObject = JSONObject().apply {
        put("observed", JSONArray(profile.observedRaceIds.toList()))
        put("starts", JSONObject(profile.starts))
        put("wins", JSONObject(profile.wins))
        put("windCourseStarts", JSONObject(profile.windCourseStarts))
        put("windCourseWins", JSONObject(profile.windCourseWins))
    }

    private fun saveLocal(profile: LearningProfile) {
        prefs.edit().putString(KEY, profileToJson(profile).toString()).apply()
    }

    private fun isCoveredByHistoricalBaseline(rawDate: String): Boolean {
        val from = historicalBaseline.trainedFrom?.let(::parseDateOrNull) ?: return false
        val through = historicalBaseline.trainedThrough?.let(::parseDateOrNull) ?: return false
        val day = parseDateOrNull(rawDate.take(10)) ?: return false
        return !day.isBefore(from) && !day.isAfter(through)
    }

    private fun migrateLegacyLocalIfNeeded() {
        if (prefs.getBoolean(BASELINE_MIGRATION_DONE, false)) return
        if (historicalBaseline.historicalRaceCount <= 0) return

        val local = loadLocal()
        val through = historicalBaseline.trainedThrough?.let(::parseDateOrNull)
        val hasOverlap = through != null && local.observedRaceIds.any { id ->
            parseDateOrNull(id.take(10))?.let { !it.isAfter(through) } == true
        }
        val editor = prefs.edit()
        if (hasOverlap) editor.remove(KEY)
        editor.putBoolean(BASELINE_MIGRATION_DONE, true).apply()
    }

    private fun validateLocalProfile(profile: LearningProfile) {
        require(profile.starts.values.all { it >= 0 }) { "学習開始数が不正です" }
        require(profile.wins.values.all { it >= 0 }) { "学習勝利数が不正です" }
        require(profile.windCourseStarts.values.all { it >= 0 }) { "風・進入開始数が不正です" }
        require(profile.windCourseWins.values.all { it >= 0 }) { "風・進入勝利数が不正です" }
        profile.wins.forEach { (key, wins) -> require(wins <= (profile.starts[key] ?: 0)) { "勝利数が開始数を超えています" } }
        profile.windCourseWins.forEach { (key, wins) ->
            require(wins <= (profile.windCourseStarts[key] ?: 0)) { "風・進入勝利数が開始数を超えています" }
        }
    }

    private fun parseDateOrNull(value: String): LocalDate? = runCatching { LocalDate.parse(value) }.getOrNull()

    private fun JSONArray.stringSet(): Set<String> = buildSet {
        for (index in 0 until length()) optString(index).takeIf(String::isNotBlank)?.let(::add)
    }

    private fun JSONObject?.intMap(): Map<String, Int> {
        if (this == null) return emptyMap()
        return keys().asSequence().associateWith { optInt(it) }.filterValues { it >= 0 }
    }

    companion object {
        private const val KEY = "profile"
        private const val HISTORICAL_ASSET = "historical_learning.json"
        private const val BACKUP_TYPE = "boat-ai-local-learning-backup"
        private const val BASELINE_MIGRATION_DONE = "historical_baseline_migration_v1"
    }
}
