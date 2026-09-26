package jp.boatai.app

object SettlementRetryPolicy {
    const val MAX_RETRY_ATTEMPTS = 3
    const val RETRY_DELAY_MINUTES = 15L

    fun shouldRetry(currentAttempt: Int, hasPendingRecord: Boolean): Boolean =
        hasPendingRecord && currentAttempt in 0 until MAX_RETRY_ATTEMPTS

    fun nextAttempt(currentAttempt: Int): Int = (currentAttempt + 1).coerceAtMost(MAX_RETRY_ATTEMPTS)
}
