package jp.boatai.app

data class LiveAuditCoverage(
    val liveBuyCount: Int,
    val auditedBuyCount: Int
) {
    val missingAuditCount: Int get() = (liveBuyCount - auditedBuyCount).coerceAtLeast(0)
    val coveragePercent: Double get() = if (liveBuyCount > 0) auditedBuyCount * 100.0 / liveBuyCount else 0.0
}

/**
 * Separates actually observed, auditable live BUY decisions from retrospective
 * simulations and older prediction records.
 *
 * A record is accepted only when the production value strategy decided BUY while
 * the race was still being tracked, the result has settled, and a complete live
 * official trifecta snapshot can be tied to every selected combination.
 */
object LiveAuditedPerformance {
    const val LIVE_STRATEGY_ID = "value-v1"
    const val REQUIRED_TRIFECTA_ODDS = 120

    fun isAuditedBuy(record: PredictionRecord): Boolean {
        if (!record.settled || !record.evaluationEligible) return false
        if (!record.recommended || record.strategyId != LIVE_STRATEGY_ID) return false
        if (record.liveOddsFetchedAt == null || record.liveOddsFetchedAt <= 0L) return false
        if (record.liveOddsSource.isNullOrBlank()) return false
        if (record.liveOddsCount < REQUIRED_TRIFECTA_ODDS) return false
        if (record.combinations.isEmpty()) return false
        if (record.stakes.size != record.combinations.size) return false
        if (record.stakes.any { it < 100 || it % 100 != 0 }) return false
        if (record.livePickOdds.size != record.combinations.size) return false
        if (record.livePickOdds.any { !it.isFinite() || it <= 0.0 }) return false
        return true
    }

    fun eligible(records: List<PredictionRecord>): List<PredictionRecord> =
        records.filter(::isAuditedBuy)

    fun coverage(records: List<PredictionRecord>): LiveAuditCoverage {
        val liveBuys = records.filter {
            it.settled &&
                it.evaluationEligible &&
                it.recommended &&
                it.strategyId == LIVE_STRATEGY_ID
        }
        return LiveAuditCoverage(
            liveBuyCount = liveBuys.size,
            auditedBuyCount = liveBuys.count(::isAuditedBuy)
        )
    }
}
