package jp.boatai.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

data class OneTwoLockRecord(
    val id: String,
    val date: String,
    val stadiumNumber: Int,
    val raceNumber: Int,
    val pairProbability: Double,
    val combinations: List<String>,
    val odds: List<Double> = emptyList(),
    val oddsFetchedAt: Long? = null,
    val oddsSource: String? = null,
    val oddsQualified: Boolean = false,
    val resultCombination: String? = null,
    val trifectaPayout: Int = 0,
    val settled: Boolean = false,
    val createdAt: Long = System.currentTimeMillis()
) {
    val pairHit: Boolean get() = settled && resultCombination?.startsWith("1-2-") == true
    val ticketHit: Boolean get() = settled && resultCombination in combinations
    val simulatedStake: Int get() = if (settled && oddsQualified) combinations.size * 100 else 0
    val simulatedPayout: Int get() = if (settled && oddsQualified && ticketHit) trifectaPayout else 0

    fun toJson(): JSONObject = JSONObject().apply {
        put("id", id)
        put("date", date)
        put("stadiumNumber", stadiumNumber)
        put("raceNumber", raceNumber)
        put("pairProbability", pairProbability)
        put("combinations", JSONArray().apply { combinations.forEach(::put) })
        if (odds.isNotEmpty()) put("odds", JSONArray().apply { odds.forEach(::put) })
        if (oddsFetchedAt != null) put("oddsFetchedAt", oddsFetchedAt)
        if (!oddsSource.isNullOrBlank()) put("oddsSource", oddsSource)
        put("oddsQualified", oddsQualified)
        if (!resultCombination.isNullOrBlank()) put("resultCombination", resultCombination)
        put("trifectaPayout", trifectaPayout)
        put("settled", settled)
        put("createdAt", createdAt)
    }

    companion object {
        fun fromJson(obj: JSONObject): OneTwoLockRecord {
            val combinations = obj.optJSONArray("combinations")?.let { array ->
                List(array.length()) { index -> array.optString(index) }.filter { it.isNotBlank() }
            }.orEmpty()
            val odds = obj.optJSONArray("odds")?.let { array ->
                List(array.length()) { index -> array.optDouble(index) }
                    .takeIf { values -> values.size == combinations.size && values.all { it.isFinite() && it > 0.0 } }
            }.orEmpty()
            return OneTwoLockRecord(
                id = obj.optString("id"),
                date = obj.optString("date"),
                stadiumNumber = obj.optInt("stadiumNumber"),
                raceNumber = obj.optInt("raceNumber"),
                pairProbability = obj.optDouble("pairProbability").coerceIn(0.0, 1.0),
                combinations = combinations,
                odds = odds,
                oddsFetchedAt = if (obj.has("oddsFetchedAt")) obj.optLong("oddsFetchedAt") else null,
                oddsSource = obj.optString("oddsSource").takeIf { it.isNotBlank() },
                oddsQualified = obj.optBoolean("oddsQualified", false),
                resultCombination = obj.optString("resultCombination").takeIf { it.isNotBlank() },
                trifectaPayout = obj.optInt("trifectaPayout", 0),
                settled = obj.optBoolean("settled", false),
                createdAt = obj.optLong("createdAt", 0L)
            )
        }
    }
}

data class OneTwoLockSummary(
    val settledCandidates: Int = 0,
    val pairHits: Int = 0,
    val ticketHits: Int = 0,
    val qualifiedSettled: Int = 0,
    val simulatedStake: Int = 0,
    val simulatedPayout: Int = 0
) {
    val pairHitRate: Double get() = if (settledCandidates > 0) pairHits * 100.0 / settledCandidates else 0.0
    val ticketHitRate: Double get() = if (settledCandidates > 0) ticketHits * 100.0 / settledCandidates else 0.0
    val simulatedProfit: Int get() = simulatedPayout - simulatedStake
    val simulatedRoi: Double get() = if (simulatedStake > 0) simulatedPayout * 100.0 / simulatedStake else 0.0
    val pairRateText: String get() = String.format(Locale.US, "%.1f%%", pairHitRate)
}

class OneTwoLockHistoryStore(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun load(): List<OneTwoLockRecord> = decode(prefs.getString(KEY, null)).sortedByDescending { it.createdAt }

    fun captureRace(race: RaceData, selection: OneTwoLockSelection): List<OneTwoLockRecord> {
        if (!selection.eligible) return load()
        val current = load().toMutableList()
        if (current.any { it.id == race.id }) return current
        current += OneTwoLockRecord(
            id = race.id,
            date = race.date.take(10),
            stadiumNumber = race.stadiumNumber,
            raceNumber = race.raceNumber,
            pairProbability = selection.pairProbability,
            combinations = selection.combinations
        )
        save(current)
        return current.sortedByDescending { it.createdAt }
    }

    fun updateOdds(raceId: String, quote: OneTwoLockQuote): List<OneTwoLockRecord> {
        if (!quote.oddsComplete) return load()
        var changed = false
        val current = load().map { record ->
            if (record.id != raceId || record.settled) return@map record
            changed = true
            record.copy(
                odds = record.combinations.mapNotNull { quote.odds[it] },
                oddsFetchedAt = quote.fetchedAt,
                oddsSource = quote.source,
                oddsQualified = quote.purchaseQualified
            )
        }
        if (changed) save(current)
        return current.sortedByDescending { it.createdAt }
    }

    fun settle(races: List<RaceData>): List<OneTwoLockRecord> {
        if (races.isEmpty()) return load()
        val results = races.filter { it.hasResult }.associateBy { it.id }
        var changed = false
        val settled = load().map { record ->
            if (record.settled) return@map record
            val result = results[record.id]?.result ?: return@map record
            val combination = result.trifectaCombination ?: return@map record
            changed = true
            record.copy(
                resultCombination = combination,
                trifectaPayout = result.trifectaPayout ?: 0,
                settled = true
            )
        }
        if (changed) save(settled)
        return settled.sortedByDescending { it.createdAt }
    }

    fun pendingDates(): Set<String> = load().asSequence()
        .filterNot { it.settled }
        .map { it.date.take(10) }
        .filter { it.isNotBlank() }
        .toSet()

    fun hasPending(raceId: String): Boolean = load().any { !it.settled && it.id == raceId }

    fun summary(): OneTwoLockSummary {
        val settled = load().filter { it.settled }
        val qualified = settled.filter { it.oddsQualified }
        return OneTwoLockSummary(
            settledCandidates = settled.size,
            pairHits = settled.count { it.pairHit },
            ticketHits = settled.count { it.ticketHit },
            qualifiedSettled = qualified.size,
            simulatedStake = qualified.sumOf { it.simulatedStake },
            simulatedPayout = qualified.sumOf { it.simulatedPayout }
        )
    }

    private fun save(records: List<OneTwoLockRecord>) {
        val array = JSONArray()
        records.forEach { array.put(it.toJson()) }
        prefs.edit().putString(KEY, array.toString()).apply()
    }

    private fun decode(raw: String?): List<OneTwoLockRecord> {
        if (raw.isNullOrBlank()) return emptyList()
        return runCatching {
            val array = JSONArray(raw)
            buildList {
                for (i in 0 until array.length()) {
                    val obj = array.optJSONObject(i) ?: continue
                    add(OneTwoLockRecord.fromJson(obj))
                }
            }
        }.getOrElse { emptyList() }
    }

    companion object {
        private const val PREFS = "boat_ai_one_two_lock"
        private const val KEY = "records_v2"
    }
}
