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
    fun penalty(stadiumNumber: Int, rawConfidence: Int, firstLane: Int?): Int {
        val rank = rankFor(rawConfidence)
        val values = listOf(
            poorPenalty(byVenue[stadiumNumber], 24),
            poorPenalty(byRank[rank], 30),
            poorPenalty(firstLane?.let(byFirstLane::get), 30),
            poorPenalty(firstLane?.let { byContext[contextKey(stadiumNumber, rank, it)] }, 16)
        )
        return values.sum().coerceIn(-12, 0)
    }

    fun autoSkipReason(stadiumNumber: Int, rawConfidence: Int, firstLane: Int?): String? {
        val lane = firstLane ?: return null
        val rank = rankFor(rawConfidence)
        val exact = byContext[contextKey(stadiumNumber, rank, lane)]
        if (isSevere(exact, 24)) {
            return "${Venues.name(stadiumNumber)}・AI$rank・${lane}号艇1着軸の実績が低迷"
        }

        val venue = byVenue[stadiumNumber]
        if (isSevere(venue, 60)) {
            return "${Venues.name(stadiumNumber)}の蓄積実績が低迷"
        }

        val rankStats = byRank[rank]
        if (isSevere(rankStats, 80)) {
            return "AI$rank帯の蓄積実績が低迷"
        }

        val laneStats = byFirstLane[lane]
        if (isSevere(laneStats, 60)) {
            return "${lane}号艇1着軸の蓄積実績が低迷"
        }
        return null
    }

    fun weakConditions(limit: Int = 5): List<PredictionWeakCondition> {
        val candidates = buildList {
            byVenue.forEach { (venue, stats) ->
                condition("${Venues.name(venue)}", stats, 24)?.let(::add)
            }
            byRank.forEach { (rank, stats) ->
                condition("AI$rank帯", stats, 30)?.let(::add)
            }
            byFirstLane.forEach { (lane, stats) ->
                condition("${lane}号艇1着軸", stats, 30)?.let(::add)
            }
            byContext.forEach { (key, stats) ->
                if (stats.races < 16 || stats.roi >= 90.0) return@forEach
                val parts = key.split(":")
                if (parts.size != 3) return@forEach
                val venue = parts[0].toIntOrNull() ?: return@forEach
                val rank = parts[1]
                val lane = parts[2].toIntOrNull() ?: return@forEach
                add(
                    PredictionWeakCondition(
                        label = "${Venues.name(venue)}・AI$rank・${lane}号艇軸",
                        stats = stats,
                        penalty = poorPenalty(stats, 16),
                        autoSkip = isSevere(stats, 24)
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
        if (stats.races < minSamples || stats.roi >= 90.0) return null
        return PredictionWeakCondition(
            label = label,
            stats = stats,
            penalty = poorPenalty(stats, minSamples),
            autoSkip = isSevere(stats, maxOf(minSamples, 24))
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
                stats.roi < 55.0 && stats.hitRate < 8.0 -> -5
                stats.roi < 70.0 -> -4
                stats.roi < 85.0 -> -2
                stats.roi < 90.0 -> -1
                else -> 0
            }
        }

        private fun isSevere(stats: PredictionPerformanceStats?, minSamples: Int): Boolean =
            stats != null && stats.races >= minSamples && stats.roi < 55.0 && stats.hitRate < 8.0

        private fun accumulator() = MutableStats()
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
