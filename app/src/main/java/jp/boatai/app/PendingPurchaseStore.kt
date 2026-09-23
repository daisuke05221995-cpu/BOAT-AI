package jp.boatai.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class PendingPurchaseTicket(
    val combination: String,
    val amount: Int
) {
    fun toJson(): JSONObject = JSONObject()
        .put("combination", combination)
        .put("amount", amount)

    companion object {
        fun fromJson(json: JSONObject): PendingPurchaseTicket? {
            val combination = json.optString("combination").trim()
            val amount = json.optInt("amount", 0)
            if (combination.isBlank() || amount < 100 || amount % 100 != 0) return null
            return PendingPurchaseTicket(combination, amount)
        }
    }
}

data class PendingPurchaseRace(
    val raceId: String,
    val date: String,
    val stadiumNumber: Int,
    val raceNumber: Int,
    val venueName: String,
    val recommended: Boolean,
    val tickets: List<PendingPurchaseTicket>
) {
    val totalStake: Int get() = tickets.sumOf { it.amount }

    fun toJson(): JSONObject {
        val ticketArray = JSONArray()
        tickets.forEach { ticketArray.put(it.toJson()) }
        return JSONObject()
            .put("raceId", raceId)
            .put("date", date)
            .put("stadiumNumber", stadiumNumber)
            .put("raceNumber", raceNumber)
            .put("venueName", venueName)
            .put("recommended", recommended)
            .put("tickets", ticketArray)
    }

    companion object {
        fun fromJson(json: JSONObject): PendingPurchaseRace? {
            val raceId = json.optString("raceId").trim()
            val date = json.optString("date").trim()
            val stadiumNumber = json.optInt("stadiumNumber", 0)
            val raceNumber = json.optInt("raceNumber", 0)
            if (raceId.isBlank() || date.isBlank() || stadiumNumber !in 1..24 || raceNumber !in 1..12) return null
            val ticketsJson = json.optJSONArray("tickets") ?: return null
            val tickets = buildList {
                for (i in 0 until ticketsJson.length()) {
                    val ticket = ticketsJson.optJSONObject(i)?.let(PendingPurchaseTicket::fromJson) ?: continue
                    add(ticket)
                }
            }
            if (tickets.isEmpty()) return null
            return PendingPurchaseRace(
                raceId = raceId,
                date = date,
                stadiumNumber = stadiumNumber,
                raceNumber = raceNumber,
                venueName = json.optString("venueName").ifBlank { Venues.name(stadiumNumber) },
                recommended = json.optBoolean("recommended", true),
                tickets = tickets
            )
        }
    }
}

data class PendingPurchaseSession(
    val id: String,
    val createdAt: Long,
    val races: List<PendingPurchaseRace>,
    val selectedRaceIds: Set<String>
) {
    val selectedRaces: List<PendingPurchaseRace>
        get() = races.filter { it.raceId in selectedRaceIds }
    val totalStake: Int get() = races.sumOf { it.totalStake }
    val selectedStake: Int get() = selectedRaces.sumOf { it.totalStake }
    val ticketCount: Int get() = races.sumOf { it.tickets.size }
    val selectedTicketCount: Int get() = selectedRaces.sumOf { it.tickets.size }

    fun toJson(): JSONObject {
        val raceArray = JSONArray()
        races.forEach { raceArray.put(it.toJson()) }
        val selectedArray = JSONArray()
        selectedRaceIds.forEach { selectedArray.put(it) }
        return JSONObject()
            .put("id", id)
            .put("createdAt", createdAt)
            .put("races", raceArray)
            .put("selectedRaceIds", selectedArray)
    }

    companion object {
        fun create(entries: List<Pair<RaceData, List<PredictionPick>>>): PendingPurchaseSession? {
            val races = entries.mapNotNull { (race, picks) ->
                val tickets = picks.mapNotNull { pick ->
                    val amount = pick.recommendedStake
                    if (pick.combination.isBlank() || amount < 100 || amount % 100 != 0) null
                    else PendingPurchaseTicket(pick.combination, amount)
                }
                if (tickets.isEmpty()) null else PendingPurchaseRace(
                    raceId = race.id,
                    date = race.date.take(10),
                    stadiumNumber = race.stadiumNumber,
                    raceNumber = race.raceNumber,
                    venueName = race.venueName,
                    recommended = PredictionEngine.isRecommended(race),
                    tickets = tickets
                )
            }
            if (races.isEmpty()) return null
            return PendingPurchaseSession(
                id = UUID.randomUUID().toString(),
                createdAt = System.currentTimeMillis(),
                races = races,
                selectedRaceIds = races.mapTo(linkedSetOf()) { it.raceId }
            )
        }

        fun fromJson(json: JSONObject): PendingPurchaseSession? {
            val racesJson = json.optJSONArray("races") ?: return null
            val races = buildList {
                for (i in 0 until racesJson.length()) {
                    val race = racesJson.optJSONObject(i)?.let(PendingPurchaseRace::fromJson) ?: continue
                    add(race)
                }
            }
            if (races.isEmpty()) return null
            val validIds = races.mapTo(linkedSetOf()) { it.raceId }
            val selectedJson = json.optJSONArray("selectedRaceIds")
            val selected = linkedSetOf<String>()
            if (selectedJson != null) {
                for (i in 0 until selectedJson.length()) {
                    selectedJson.optString(i).takeIf { it in validIds }?.let(selected::add)
                }
            }
            return PendingPurchaseSession(
                id = json.optString("id").ifBlank { UUID.randomUUID().toString() },
                createdAt = json.optLong("createdAt", System.currentTimeMillis()),
                races = races,
                selectedRaceIds = if (selectedJson == null) validIds else selected
            )
        }
    }
}

class PendingPurchaseStore(context: Context) {
    private val prefs = context.getSharedPreferences("boat_ai_pending_purchase", Context.MODE_PRIVATE)

    fun load(): PendingPurchaseSession? {
        val raw = prefs.getString(KEY, null) ?: return null
        return runCatching { PendingPurchaseSession.fromJson(JSONObject(raw)) }.getOrNull()
    }

    fun save(session: PendingPurchaseSession): PendingPurchaseSession {
        prefs.edit().putString(KEY, session.toJson().toString()).apply()
        return session
    }

    fun clear() {
        prefs.edit().remove(KEY).apply()
    }

    companion object {
        private const val KEY = "pending_session"
        const val OFFICIAL_SIMPLE_BET_URL = "https://bu.tbbr.jp/"
    }
}
