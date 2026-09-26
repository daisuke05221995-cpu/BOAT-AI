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
        var changed = false
        val now = System.currentTimeMillis()

        races.forEach { race ->
            if (race.racers.size < 3 || !race.isPurchasable()) return@forEach
            if (!PredictionEngine.isDecisionReady(race)) return@forEach

            val index = current.indexOfFirst { it.id == race.id }
            val previous = current.getOrNull(index)
            if (previous?.settled == true) return@forEach

            val valueSelection = if (PredictionEngine.hasValueStrategyModel()) {
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
            if (valueSelection == null && picks.isEmpty()) return@forEach

            val audit = LiveOddsAuditRegistry.latest(race.id)
            if (previous != null) {
                val previousFetchedAt = previous.liveOddsFetchedAt ?: Long.MIN_VALUE
                if (audit == null || audit.fetchedAt <= previousFetchedAt) return@forEach
            }

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
            val livePickOdds = audit?.let { snapshot ->
                val values = picks.map { pick -> snapshot.odds[pick.combination] }
                if (values.all { it != null && it.isFinite() && it > 0.0 }) values.map { it!! } else emptyList()
            }.orEmpty()
            val record = PredictionRecord(
                id = race.id,
                date = race.date,
                stadiumNumber = race.stadiumNumber,
                raceNumber = race.raceNumber,
                combinations = picks.map { it.combination },
                stakePerPick = simulationStake,
                resultCombination = null,
                trifectaPayout = 0,
                settled = false,
                createdAt = previous?.createdAt ?: now,
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
                strategyId = if (valueSelection != null) "value-v1" else null,
                liveOddsFetchedAt = audit?.fetchedAt,
                liveOddsSource = audit?.source,
                liveOddsCount = audit?.odds?.values?.count { it.isFinite() && it > 0.0 } ?: 0,
                livePickOdds = livePickOdds
            )
            if (index >= 0) current[index] = record else current += record
            changed = true
        }

        if (changed) save(current)
        return current.sortedByDescending { it.createdAt }
    }

    /**
     * 締切直前のバックグラウンド評価結果を、そのレースの最終事前予想として保存する。
     * 画面を先に開いて暫定レコードが存在していても、未確定なら5分前のBUY/SKIP・
     * 公式オッズ反映後の買い目へ置き換える。結果確定後のレコードは上書きしない。
     */
    fun upsertEvaluatedRace(
        race: RaceData,
        picks: List<PredictionPick>,
        decision: RecommendationDecision,
        strategyId: String? = null,
        stakePerPick: Int = DEFAULT_SIMULATION_STAKE,
        oddsResult: OddsFetchResult? = null
    ): List<PredictionRecord> {
        if (!race.isPurchasable() || !PredictionEngine.isDecisionReady(race)) return load()
        val storedPicks = if (!decision.recommended && strategyId == "value-v1") emptyList() else picks
        if (decision.recommended && storedPicks.isEmpty()) return load()

        val current = load().toMutableList()
        val index = current.indexOfFirst { it.id == race.id }
        val previous = current.getOrNull(index)
        if (previous?.settled == true) return current.sortedByDescending { it.createdAt }

        val rawConfidence = PredictionEngine.rawConfidence(race)
        val validStakes = if (
            decision.recommended &&
            storedPicks.isNotEmpty() &&
            storedPicks.all { it.recommendedStake >= 100 && it.recommendedStake % 100 == 0 }
        ) {
            storedPicks.map { it.recommendedStake }
        } else {
            emptyList()
        }
        val livePickOdds = oddsResult?.let { snapshot ->
            val values = storedPicks.map { pick -> snapshot.odds[pick.combination] }
            if (values.all { it != null && it.isFinite() && it > 0.0 }) values.map { it!! } else emptyList()
        }.orEmpty()

        val record = PredictionRecord(
            id = race.id,
            date = race.date,
            stadiumNumber = race.stadiumNumber,
            raceNumber = race.raceNumber,
            combinations = storedPicks.map { it.combination },
            stakePerPick = if (!decision.recommended && strategyId == "value-v1") 0 else stakePerPick,
            resultCombination = null,
            trifectaPayout = 0,
            settled = false,
            createdAt = previous?.createdAt ?: System.currentTimeMillis(),
            confidence = PredictionEngine.confidence(race),
            rank = PredictionPerformanceProfile.rankFor(rawConfidence),
            firstLane = storedPicks.firstOrNull()?.combination?.substringBefore("-")?.toIntOrNull(),
            evaluationEligible = true,
            autoSkipped = !decision.recommended,
            autoSkipReason = decision.reason.takeIf { !decision.recommended },
            recommended = decision.recommended,
            recommendationReason = decision.reason,
            stakes = validStakes,
            strategyId = strategyId,
            liveOddsFetchedAt = oddsResult?.fetchedAt,
            liveOddsSource = oddsResult?.source,
            liveOddsCount = oddsResult?.odds?.values?.count { it.isFinite() && it > 0.0 } ?: 0,
            livePickOdds = livePickOdds
        )

        if (index >= 0) current[index] = record else current += record
        save(current)
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
