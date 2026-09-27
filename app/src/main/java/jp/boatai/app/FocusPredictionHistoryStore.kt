package jp.boatai.app

import android.content.Context
import org.json.JSONArray

/**
 * Dedicated ledger for the Focus 4/5 experiments.
 *
 * It intentionally does not share keys with PredictionHistoryStore so focus performance
 * can never be mixed into the audited value-v1/live Model A ledger.
 */
class FocusPredictionHistoryStore(context: Context) {
    private val prefs = context.getSharedPreferences("boat_ai_focus_predictions", Context.MODE_PRIVATE)

    fun load(mode: FocusMode): List<PredictionRecord> = decode(prefs.getString(key(mode), null))
        .orEmpty()
        .filter { it.strategyId == mode.strategyId }
        .sortedByDescending { it.createdAt }

    fun captureRace(
        race: RaceData,
        mode: FocusMode,
        budget: Int = BetStrategy.DEFAULT_BUDGET
    ): List<PredictionRecord> {
        if (!race.isPurchasable() || !PredictionEngine.isDecisionReady(race)) return load(mode)
        val picks = FocusPredictionStrategy.purchasePicks(race, mode, budget)
        if (picks.isEmpty()) return load(mode)

        val current = load(mode).toMutableList()
        val index = current.indexOfFirst { it.id == race.id }
        val previous = current.getOrNull(index)
        if (previous?.settled == true) return current

        // Freeze the first valid pre-close focus selection. Unlike value-v1 this strategy
        // does not consume odds, so refreshing it later would only create avoidable drift.
        if (previous != null) return current

        val record = PredictionRecord(
            id = race.id,
            date = race.date.take(10),
            stadiumNumber = race.stadiumNumber,
            raceNumber = race.raceNumber,
            combinations = picks.map { it.combination },
            stakePerPick = 0,
            resultCombination = null,
            trifectaPayout = 0,
            settled = false,
            createdAt = System.currentTimeMillis(),
            confidence = PredictionEngine.confidence(race),
            rank = PredictionPerformanceProfile.rankFor(PredictionEngine.rawConfidence(race)),
            firstLane = picks.firstOrNull()?.combination?.substringBefore("-")?.toIntOrNull(),
            evaluationEligible = true,
            autoSkipped = false,
            recommended = true,
            recommendationReason = "${mode.label}：締切前Model A確率から固定した別戦略",
            stakes = picks.map { it.recommendedStake },
            strategyId = mode.strategyId
        )
        current += record
        save(mode, current)
        return current.sortedByDescending { it.createdAt }
    }

    fun settle(races: List<RaceData>): Map<FocusMode, List<PredictionRecord>> {
        if (races.isEmpty()) return FocusMode.values().associateWith(::load)
        val resultMap = races.filter { it.hasResult }.associateBy { it.id }
        return FocusMode.values().associateWith { mode ->
            val current = load(mode)
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
            if (changed) save(mode, settled)
            settled.sortedByDescending { it.createdAt }
        }
    }

    fun pendingDates(): Set<String> = buildSet {
        FocusMode.values().forEach { mode ->
            load(mode).asSequence()
                .filterNot { it.settled }
                .map { it.date.take(10) }
                .filter { it.isNotBlank() }
                .forEach(::add)
        }
    }

    fun summary(mode: FocusMode): AnalyticsSummary =
        ProfitAnalytics.summarize(load(mode).filter { it.settled && it.evaluationEligible })

    private fun save(mode: FocusMode, records: List<PredictionRecord>) {
        val array = JSONArray()
        records.forEach { array.put(it.toJson()) }
        prefs.edit().putString(key(mode), array.toString()).apply()
    }

    private fun decode(raw: String?): List<PredictionRecord>? {
        if (raw == null) return emptyList()
        return runCatching {
            val array = JSONArray(raw)
            buildList {
                for (i in 0 until array.length()) {
                    array.optJSONObject(i)?.let(PredictionRecord::fromJson)?.let(::add)
                }
            }
        }.getOrNull()
    }

    private fun key(mode: FocusMode): String = when (mode) {
        FocusMode.FOUR -> "focus_4_records_v1"
        FocusMode.FIVE -> "focus_5_records_v1"
    }
}
