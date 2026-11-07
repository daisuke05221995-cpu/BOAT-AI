package jp.boatai.app

import android.content.Context
import java.security.MessageDigest

/** A durable reservation must be saved before a purchase-confirm tap is attempted. */
internal interface PurchaseAttemptReservation {
    fun reserveAll(deduplicationKeys: List<String>, attemptedAtMs: Long): Boolean
}

internal class AndroidPurchaseAttemptReservation(context: Context) : PurchaseAttemptReservation {
    private val preferences = context.getSharedPreferences("official_purchase_attempts", Context.MODE_PRIVATE)

    @Synchronized
    override fun reserveAll(deduplicationKeys: List<String>, attemptedAtMs: Long): Boolean {
        if (deduplicationKeys.isEmpty() || deduplicationKeys.distinct().size != deduplicationKeys.size ||
            deduplicationKeys.any(preferences::contains)) return false
        // Synchronous commit: a crash/restart must never result in a second tap.
        val edit = preferences.edit()
        deduplicationKeys.forEach { edit.putLong(it, attemptedAtMs) }
        return edit.commit()
    }
}

internal sealed interface PurchaseSubmissionResult {
    data class Rejected(val reason: String) : PurchaseSubmissionResult
    /** Android accepted the tap; only a later official receipt can prove purchase completion. */
    data object TapAttemptedReceiptPending : PurchaseSubmissionResult
    /** Once reserved, no automatic retry even when Android reports a failed tap. */
    data object TapFailedDoNotRetry : PurchaseSubmissionResult
}

internal object PurchaseSubmitGate {
    fun validate(
        session: PendingPurchaseSession,
        review: OfficialPurchaseReview,
        preflight: PurchaseAutomationCheck,
        nowMs: Long,
        liveDataFetchedAtMs: Long
    ): PurchaseConfirmationDecision {
        if (session.id.isBlank() || session.selectedRaces.isEmpty()) return reject("購入セッションがありません")
        if (session.createdAt <= 0 || session.createdAt > nowMs ||
            nowMs - session.createdAt > 10 * 60_000L) return reject("購入指示が古くなっています")
        if (liveDataFetchedAtMs <= 0 || liveDataFetchedAtMs > nowMs ||
            nowMs - liveDataFetchedAtMs > 60_000L) return reject("開催情報の更新が古くなっています")
        if (!preflight.allowed || preflight.sessionStake != session.selectedStake ||
            preflight.selectedTickets != session.selectedTicketCount) return reject("直前の購入条件を満たしていません")
        return PurchaseConfirmationGate.checkReview(session, review, nowMs, maxObservationAgeMs = 10_000L)
    }

    /** Any overlapping ticket on the same day is blocked, even in a different handoff/subset. */
    fun deduplicationKeys(session: PendingPurchaseSession): List<String> =
        session.selectedRaces.flatMap { race ->
            race.tickets.map { ticket ->
                "${race.date}|${race.stadiumNumber}|${race.raceNumber}|${ticket.combination}|${ticket.amount}"
            }
        }.map { canonical ->
            val digest = MessageDigest.getInstance("SHA-256").digest(canonical.toByteArray(Charsets.UTF_8))
            "attempt_" + digest.joinToString("") { "%02x".format(it.toInt() and 0xff) }
        }.sorted()

    private fun reject(reason: String) = PurchaseConfirmationDecision(false, reason)
}

/** The submit callback must be a single, pre-identified official-app ACTION_CLICK. */
internal class PurchaseSubmissionController(private val reservations: PurchaseAttemptReservation) {
    fun submitOnce(
        session: PendingPurchaseSession,
        review: OfficialPurchaseReview,
        preflight: PurchaseAutomationCheck,
        nowMs: Long,
        liveDataFetchedAtMs: Long,
        tap: () -> Boolean
    ): PurchaseSubmissionResult {
        val gate = PurchaseSubmitGate.validate(session, review, preflight, nowMs, liveDataFetchedAtMs)
        if (!gate.allowed) return PurchaseSubmissionResult.Rejected(gate.reason)
        if (!reservations.reserveAll(PurchaseSubmitGate.deduplicationKeys(session), nowMs)) {
            return PurchaseSubmissionResult.Rejected("この買い目の一部または全部がすでに投票操作済みです")
        }
        return if (runCatching(tap).getOrDefault(false)) PurchaseSubmissionResult.TapAttemptedReceiptPending
        else PurchaseSubmissionResult.TapFailedDoNotRetry
    }
}
