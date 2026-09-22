package jp.boatai.app

data class PredictionPerformanceStats(
    val races: Int = 0,
    val hits: Int = 0,
    val stake: Int = 0,
    val payout: Int = 0
) {
    val hitRate: Double get() = if (races > 0) hits * 100.0 / races else 0.0
    val roi: Double get() = if (stake > 0) payout * 100.0 / stake else 0.0
    val profit: Int get() = payout - stake

    fun mergedWith(other: PredictionPerformanceStats) = PredictionPerformanceStats(
        races = races + other.races,
        hits = hits + other.hits,
        stake = stake + other.stake,
        payout = payout + other.payout
    )
}

data class PredictionWeakCondition(
    val label: String,
    val stats: PredictionPerformanceStats,
    val penalty: Int,
    val autoSkip: Boolean
)

data class PredictionPerformanceProfile(
    val overall: PredictionPerformanceStats = PredictionPerformanceStats(),
    val byRank: Map<String, PredictionPerformanceStats> = emptyMap(),
    val byVenue: Map<Int, PredictionPerformanceStats> = emptyMap(),
    val byFirstLane: Map<Int, PredictionPerformanceStats> = emptyMap(),
    val byContext: Map<String, PredictionPerformanceStats> = emptyMap()
) {
    fun mergedWith(other: PredictionPerformanceProfile) = PredictionPerformanceProfile(
        overall = overall.mergedWith(other.overall),
        byRank = mergeMaps(byRank, other.byRank),
        byVenue = mergeMaps(byVenue, other.byVenue),
        byFirstLane = mergeMaps(byFirstLane, other.byFirstLane),
        byContext = mergeMaps(byContext, other.byContext)
    )

    fun penalty(stadiumNumber: Int, rawConfidence: Int, firstLane: Int?): Int {
        val rank = rankFor(rawConfidence)
        val values = listOf(
            poorPenalty(byVenue[stadiumNumber], 20),
            poorPenalty(byRank[rank], 24),
            poorPenalty(firstLane?.let { byFirstLane[it] }, 24),
            poorPenalty(firstLane?.let { byContext[contextKey(stadiumNumber, rank, it)] }, 12)
        )
        return values.sum().coerceIn(-18, 0)
    }

    fun autoSkipReason(stadiumNumber: Int, rawConfidence: Int, firstLane: Int?): String? {
        val lane = firstLane ?: return null
        val rank = rankFor(rawConfidence)
        val exact = byContext[contextKey(stadiumNumber, rank, lane)]
        if (shouldSkip(exact, 18)) {
            return "${Venues.name(stadiumNumber)}・AI${rank}・${lane}号艇1着軸の回収実績が購入基準未満"
        }

        val venue = byVenue[stadiumNumber]
        if (shouldSkip(venue, 40)) {
            return "${Venues.name(stadiumNumber)}の蓄積回収実績が購入基準未満"
        }

        val rankStats = byRank[rank]
        if (shouldSkip(rankStats, 50)) {
            return "AI${rank}帯の蓄積回収実績が購入基準未満"
        }

        val laneStats = byFirstLane[lane]
        if (shouldSkip(laneStats, 40)) {
            return "${lane}号艇1着軸の蓄積回収実績が購入基準未満"
        }
        return null
    }

    fun weakConditions(limit: Int = 5): List<PredictionWeakCondition> {
        val candidates = buildList {
            byVenue.forEach { (venue, stats) ->
                condition(Venues.name(venue), stats, 20)?.let { add(it) }
            }
            byRank.forEach { (rank, stats) ->
                condition("AI${rank}帯", stats, 24)?.let { add(it) }
            }
            byFirstLane.forEach { (lane, stats) ->
                condition("${lane}号艇1着軸", stats, 24)?.let { add(it) }
            }
            byContext.forEach { (key, stats) ->
                if (stats.races < 12 || stats.roi >= 95.0) return@forEach
                val parts = key.split(":")
                if (parts.size != 3) return@forEach
                val venue = parts[0].toIntOrNull() ?: return@forEach
                val rank = parts[1]
                val lane = parts[2].toIntOrNull() ?: return@forEach
                add(
                    PredictionWeakCondition(
                        label = "${Venues.name(venue)}・AI${rank}・${lane}号艇軸",
                        stats = stats,
                        penalty = poorPenalty(stats, 12),
                        autoSkip = shouldSkip(stats, 18)
                    )
                )
            }
        }
        return candidates
            .distinctBy { it.label }
            .sortedWith(compareBy<PredictionWeakCondition> { it.stats.roi }.thenByDescending { it.stats.races })
            .take(limit)
    }

    private fun condition(
        label: String,
        stats: PredictionPerformanceStats,
        minSamples: Int
    ): PredictionWeakCondition? {
        if (stats.races < minSamples || stats.roi >= 95.0) return null
        return PredictionWeakCondition(
            label = label,
            stats = stats,
            penalty = poorPenalty(stats, minSamples),
            autoSkip = shouldSkip(stats, maxOf(minSamples, 18))
        )
    }

    companion object {
        fun from(records: List<PredictionRecord>): PredictionPerformanceProfile {
            val eligible = records.filter { it.settled && it.evaluationEligible && it.combinations.isNotEmpty() }
            if (eligible.isEmpty()) return PredictionPerformanceProfile()

            val overall = accumulator()
            val ranks = mutableMapOf<String, MutableStats>()
            val venues = mutableMapOf<Int, MutableStats>()
            val firstLanes = mutableMapOf<Int, MutableStats>()
            val contexts = mutableMapOf<String, MutableStats>()

            eligible.forEach { record ->
                overall.add(record)
                val rank = record.rank.ifBlank { rankFor(record.confidence) }
                ranks.getOrPut(rank) { accumulator() }.add(record)
                venues.getOrPut(record.stadiumNumber) { accumulator() }.add(record)
                record.firstLane?.let { lane ->
                    firstLanes.getOrPut(lane) { accumulator() }.add(record)
                    contexts.getOrPut(contextKey(record.stadiumNumber, rank, lane)) { accumulator() }.add(record)
                }
            }

            return PredictionPerformanceProfile(
                overall = overall.freeze(),
                byRank = ranks.mapValues { it.value.freeze() },
                byVenue = venues.mapValues { it.value.freeze() },
                byFirstLane = firstLanes.mapValues { it.value.freeze() },
                byContext = contexts.mapValues { it.value.freeze() }
            )
        }

        fun rankFor(confidence: Int): String = when (confidence) {
            in 90..100 -> "S"
            in 80..89 -> "A"
            in 70..79 -> "B"
            in 60..69 -> "C"
            else -> "D"
        }

        private fun contextKey(stadiumNumber: Int, rank: String, firstLane: Int): String =
            "$stadiumNumber:$rank:$firstLane"

        private fun poorPenalty(stats: PredictionPerformanceStats?, minSamples: Int): Int {
            if (stats == null || stats.races < minSamples) return 0
            return when {
                stats.roi < 60.0 -> -7
                stats.roi < 75.0 -> -5
                stats.roi < 88.0 -> -3
                stats.roi < 95.0 -> -1
                else -> 0
            }
        }

        private fun shouldSkip(stats: PredictionPerformanceStats?, minSamples: Int): Boolean =
            stats != null && stats.races >= minSamples &&
                (stats.roi < 65.0 || (stats.roi < 80.0 && stats.hitRate < 10.0))

        private fun accumulator() = MutableStats()

        private fun <K> mergeMaps(
            first: Map<K, PredictionPerformanceStats>,
            second: Map<K, PredictionPerformanceStats>
        ): Map<K, PredictionPerformanceStats> = buildMap {
            (first.keys + second.keys).forEach { key ->
                put(
                    key,
                    (first[key] ?: PredictionPerformanceStats())
                        .mergedWith(second[key] ?: PredictionPerformanceStats())
                )
            }
        }
    }

    private data class MutableStats(
        var races: Int = 0,
        var hits: Int = 0,
        var stake: Int = 0,
        var payout: Int = 0
    ) {
        fun add(record: PredictionRecord) {
            races += 1
            if (record.hit) hits += 1
            stake += record.simulatedStake
            payout += record.simulatedPayout
        }

        fun freeze() = PredictionPerformanceStats(races, hits, stake, payout)
    }
}
