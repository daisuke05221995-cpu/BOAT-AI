package jp.boatai.app

import android.content.Context
import org.json.JSONArray
import java.util.UUID

class BetStore(context: Context) {
    private val prefs = context.getSharedPreferences("boat_ai_bets", Context.MODE_PRIVATE)

    fun load(): List<BetRecord> {
        val raw = prefs.getString(KEY, "[]") ?: "[]"
        return runCatching {
            val array = JSONArray(raw)
            buildList {
                for (i in 0 until array.length()) {
                    val obj = array.optJSONObject(i) ?: continue
                    add(BetRecord.fromJson(obj))
                }
            }.sortedByDescending { it.createdAt }
        }.getOrDefault(emptyList())
    }

    fun addPicks(race: RaceData, picks: List<PredictionPick>, stakePerPick: Int): List<BetRecord> =
        addEntries(listOf(race to picks), stakePerPick)

    fun addRacePicks(races: List<RaceData>, raceBudget: Int): List<BetRecord> =
        addEntries(
            races.filter { it.isPurchasable() }.map { race ->
                race to BetStrategy.allocate(race, PredictionEngine.predict(race), raceBudget)
            },
            300
        )

    private fun addEntries(
        entries: List<Pair<RaceData, List<PredictionPick>>>,
        stakePerPick: Int
    ): List<BetRecord> {
        if (stakePerPick < 100 || stakePerPick % 100 != 0) return load()
        val current = load().toMutableList()
        var changed = false
        var sequence = 0L
        val now = System.currentTimeMillis()

        for ((race, picks) in entries) {
            if (!race.isPurchasable()) continue
            for (pick in picks) {
                val duplicate = current.any {
                    it.date == race.date &&
                        it.stadiumNumber == race.stadiumNumber &&
                        it.raceNumber == race.raceNumber &&
                        it.combination == pick.combination &&
                        !it.settled
                }
                if (!duplicate) {
                    val resolvedStake = pick.recommendedStake.takeIf { it >= 100 && it % 100 == 0 }
                        ?: stakePerPick
                    current += BetRecord(
                        id = UUID.randomUUID().toString(),
                        date = race.date,
                        stadiumNumber = race.stadiumNumber,
                        raceNumber = race.raceNumber,
                        combination = pick.combination,
                        stake = resolvedStake,
                        payout = 0,
                        settled = false,
                        createdAt = now + sequence++
                    )
                    changed = true
                }
            }
        }
        if (changed) save(current)
        return current.sortedByDescending { it.createdAt }
    }

    fun settle(races: List<RaceData>): List<BetRecord> {
        if (races.isEmpty()) return load()
        val resultMap = races.filter { it.hasResult }.associateBy { it.id }
        val current = load()
        var changed = false
        val settled = current.map { bet ->
            if (bet.settled) return@map bet
            val raceId = "${bet.date}-${Venues.code(bet.stadiumNumber)}-${bet.raceNumber}"
            val race = resultMap[raceId] ?: return@map bet
            val result = race.result ?: return@map bet
            val hit = result.trifectaCombination == bet.combination
            val per100 = result.trifectaPayout ?: 0
            changed = true
            bet.copy(
                payout = if (hit) per100 * (bet.stake / 100) else 0,
                settled = true
            )
        }
        if (changed) save(settled)
        return settled.sortedByDescending { it.createdAt }
    }

    fun clear(): List<BetRecord> {
        prefs.edit().remove(KEY).apply()
        return emptyList()
    }

    private fun save(records: List<BetRecord>) {
        val array = JSONArray()
        records.forEach { array.put(it.toJson()) }
        prefs.edit().putString(KEY, array.toString()).apply()
    }

    companion object {
        private const val KEY = "records"
    }
}
