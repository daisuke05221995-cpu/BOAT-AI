package jp.boatai.app

import android.content.Context
import org.json.JSONArray

class PredictionHistoryStore(context: Context) {
    private val prefs = context.getSharedPreferences("boat_ai_predictions", Context.MODE_PRIVATE)

    fun load(): List<PredictionRecord> {
        val raw = prefs.getString(KEY, "[]") ?: "[]"
        return runCatching {
            val array = JSONArray(raw)
            buildList {
                for (i in 0 until array.length()) {
                    val obj = array.optJSONObject(i) ?: continue
                    add(PredictionRecord.fromJson(obj))
                }
            }.sortedByDescending { it.createdAt }
        }.getOrDefault(emptyList())
    }

    fun captureOpenRaces(
        races: List<RaceData>,
        stakePerPick: Int = DEFAULT_SIMULATION_STAKE
    ): List<PredictionRecord> {
        if (races.isEmpty()) return load()
        val current = load().toMutableList()
        val existing = current.mapTo(mutableSetOf()) { it.id }
        var changed = false
        val now = System.currentTimeMillis()

        races.forEach { race ->
            if (!race.isPurchasable() || race.id in existing) return@forEach
            val picks = PredictionEngine.predict(race)
            if (picks.isEmpty()) return@forEach
            current += PredictionRecord(
                id = race.id,
                date = race.date,
                stadiumNumber = race.stadiumNumber,
                raceNumber = race.raceNumber,
                combinations = picks.map { it.combination },
                stakePerPick = stakePerPick,
                resultCombination = null,
                trifectaPayout = 0,
                settled = false,
                createdAt = now
            )
            existing += race.id
            changed = true
        }

        if (changed) save(current)
        return current.sortedByDescending { it.createdAt }
    }

    fun settle(races: List<RaceData>): List<PredictionRecord> {
        if (races.isEmpty()) return load()
        val resultMap = races.filter { it.hasResult }.associateBy { it.id }
        val current = load()
        var changed = false

        val settled = current.map { record ->
            if (record.settled) return@map record
            val race = resultMap[record.id] ?: return@map record
            val result = race.result ?: return@map record
            changed = true
            record.copy(
                resultCombination = result.trifectaCombination,
                trifectaPayout = result.trifectaPayout ?: 0,
                settled = true
            )
        }

        if (changed) save(settled)
        return settled.sortedByDescending { it.createdAt }
    }

    private fun save(records: List<PredictionRecord>) {
        val array = JSONArray()
        records.forEach { array.put(it.toJson()) }
        prefs.edit().putString(KEY, array.toString()).apply()
    }

    companion object {
        const val DEFAULT_SIMULATION_STAKE = 300
        private const val KEY = "prediction_records"
    }
}
