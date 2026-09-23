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
            // 成績検証へ残すのは、締切前に実際に取得できたレースだけ。
            // 終了済み・過去日を後から開いた際の後付け予想は作成しない。
            if (race.racers.size < 3 || race.id in existing || !race.isPurchasable()) return@forEach

            // 展示・進入が揃う前に購入判断を固定しない。
            if (!PredictionEngine.isDecisionReady(race)) return@forEach

            val valueSelection = if (PredictionEngine.hasValueStrategyModel()) {
                // Promoted value strategy decisions are only valid after the full official
                // trifecta market has been fetched. Never persist the temporary WAIT/SKIP
                // state or legacy picks while official odds are still pending.
                PredictionEngine.cachedValueSelection(race) ?: return@forEach
            } else {
                null
            }

            val decision = valueSelection?.let {
                RecommendationDecision(it.recommendation, it.reason)
            } ?: PredictionEngine.recommendation(race)
            val picks = if (valueSelection != null) {
                if (valueSelection.recommendation == RaceRecommendation.BUY) valueSelection.picks else emptyList()
            } else {
                PredictionEngine.predict(race)
            }

            // Legacy engine always has prediction combinations. A validated value SKIP is
            // intentionally stored with zero hypothetical stake rather than inventing old
            // four-point bets that the new strategy explicitly rejected.
            if (valueSelection == null && picks.isEmpty()) return@forEach

            val confidence = PredictionEngine.confidence(race)
            val rawConfidence = PredictionEngine.rawConfidence(race)
            val strategyStakePerPick = picks.map { it.recommendedStake }
                .filter { it >= 100 && it % 100 == 0 }
                .distinct()
                .singleOrNull()
            val simulationStake = when {
                valueSelection != null && !decision.recommended -> 0
                strategyStakePerPick != null -> strategyStakePerPick
                else -> stakePerPick
            }
            current += PredictionRecord(
                id = race.id,
                date = race.date,
                stadiumNumber = race.stadiumNumber,
                raceNumber = race.raceNumber,
                combinations = picks.map { it.combination },
                stakePerPick = simulationStake,
                resultCombination = null,
                trifectaPayout = 0,
                settled = false,
                createdAt = now,
                confidence = confidence,
                rank = PredictionPerformanceProfile.rankFor(rawConfidence),
                firstLane = picks.firstOrNull()?.combination?.substringBefore("-")?.toIntOrNull(),
                evaluationEligible = true,
                autoSkipped = !decision.recommended,
                autoSkipReason = decision.reason.takeIf { !decision.recommended },
                recommended = decision.recommended,
                recommendationReason = decision.reason,
                stakes = if (valueSelection?.recommendation == RaceRecommendation.BUY) {
                    picks.map { it.recommendedStake }
                } else {
                    emptyList()
                },
                strategyId = if (valueSelection != null) "value-v1" else null
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
