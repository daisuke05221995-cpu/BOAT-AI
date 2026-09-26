package jp.boatai.app

data class LiveAuditCoverage(
    val liveBuyCount: Int,
    val auditedBuyCount: Int
) {
    val missingAuditCount: Int get() = (liveBuyCount - auditedBuyCount).coerceAtLeast(0)
    val coveragePercent: Double get() = if (liveBuyCount > 0) auditedBuyCount * 100.0 / liveBuyCount else 0.0
}

enum class LiveAuditFailure(val label: String) {
    FETCH_TIME("取得時刻なし"),
    SOURCE("取得元なし"),
    ODDS_COUNT("120通り不足"),
    COMBINATIONS("買い目なし"),
    STAKES("購入配分不備"),
    PICK_ODDS("選択買い目オッズ不足")
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

    fun isLiveBuyCandidate(record: PredictionRecord): Boolean =
        record.settled &&
            record.evaluationEligible &&
            record.recommended &&
            record.strategyId == LIVE_STRATEGY_ID

    fun auditFailures(record: PredictionRecord): List<LiveAuditFailure> {
        if (!isLiveBuyCandidate(record)) return emptyList()
        return buildList {
            if (record.liveOddsFetchedAt == null || record.liveOddsFetchedAt <= 0L) {
                add(LiveAuditFailure.FETCH_TIME)
            }
            if (record.liveOddsSource.isNullOrBlank()) {
                add(LiveAuditFailure.SOURCE)
            }
            if (record.liveOddsCount < REQUIRED_TRIFECTA_ODDS) {
                add(LiveAuditFailure.ODDS_COUNT)
            }
            if (record.combinations.isEmpty()) {
                add(LiveAuditFailure.COMBINATIONS)
            }
            if (
                record.combinations.isNotEmpty() &&
                (record.stakes.size != record.combinations.size || record.stakes.any { it < 100 || it % 100 != 0 })
            ) {
                add(LiveAuditFailure.STAKES)
            }
            if (
                record.combinations.isNotEmpty() &&
                (record.livePickOdds.size != record.combinations.size || record.livePickOdds.any { !it.isFinite() || it <= 0.0 })
            ) {
                add(LiveAuditFailure.PICK_ODDS)
            }
        }
    }

    fun isAuditedBuy(record: PredictionRecord): Boolean =
        isLiveBuyCandidate(record) && auditFailures(record).isEmpty()

    fun eligible(records: List<PredictionRecord>): List<PredictionRecord> =
        records.filter(::isAuditedBuy)

    fun coverage(records: List<PredictionRecord>): LiveAuditCoverage {
        val liveBuys = records.filter(::isLiveBuyCandidate)
        return LiveAuditCoverage(
            liveBuyCount = liveBuys.size,
            auditedBuyCount = liveBuys.count(::isAuditedBuy)
        )
    }

    fun failureCounts(records: List<PredictionRecord>): Map<LiveAuditFailure, Int> =
        records.asSequence()
            .filter(::isLiveBuyCandidate)
            .flatMap { auditFailures(it).asSequence() }
            .groupingBy { it }
            .eachCount()
}
