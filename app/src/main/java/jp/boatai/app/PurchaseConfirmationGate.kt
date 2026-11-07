package jp.boatai.app

/** Represents a parsed review screen, never a speculative or cached prediction. */
internal data class OfficialPurchaseReview(
    val sourcePackage: String,
    val observedAtMs: Long,
    val lines: List<OfficialPurchaseLine>,
    val displayedTotal: Int
)

internal data class OfficialPurchaseLine(
    val stadiumNumber: Int,
    val raceNumber: Int,
    val combination: String,
    val amount: Int
)

internal data class PurchaseConfirmationDecision(val allowed: Boolean, val reason: String)

/**
 * This gate must pass immediately before a future submission tap can be considered.
 * The caller must independently check the official app window and a one-shot local authorization.
 */
internal object PurchaseConfirmationGate {
    fun checkReview(
        session: PendingPurchaseSession,
        review: OfficialPurchaseReview,
        nowMs: Long,
        maxObservationAgeMs: Long = 15_000L
    ): PurchaseConfirmationDecision {
        if (review.sourcePackage != BoatPurchaseAccessibilityService.OFFICIAL_APP_PACKAGE) {
            return reject("公式アプリの画面ではありません")
        }
        if (review.observedAtMs > nowMs || nowMs - review.observedAtMs > maxObservationAgeMs) {
            return reject("投票内容の画面照合が古い状態です")
        }
        val selected = session.selectedRaces
        if (selected.isEmpty()) return reject("買い目がありません")
        val expected = selected.flatMap { race ->
            race.tickets.map { ticket ->
                OfficialPurchaseLine(race.stadiumNumber, race.raceNumber, ticket.combination, ticket.amount)
            }
        }
        // Exact multiset equality rejects any extra/omitted/duplicate bet, not just total amount.
        if (review.lines.size != expected.size || review.lines.groupingBy { it }.eachCount() !=
            expected.groupingBy { it }.eachCount()) return reject("公式画面とAI買い目の組番・金額・点数が一致しません")
        if (expected.sumOf { it.amount } != session.selectedStake ||
            review.displayedTotal != session.selectedStake) return reject("公式画面の合計金額が一致しません")
        return PurchaseConfirmationDecision(true, "組番・点数・金額がすべて一致")
    }

    private fun reject(reason: String) = PurchaseConfirmationDecision(false, reason)
}
