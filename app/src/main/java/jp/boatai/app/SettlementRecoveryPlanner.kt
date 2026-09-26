package jp.boatai.app

import java.time.LocalDate

object SettlementRecoveryPlanner {
    const val LOOKBACK_DAYS = 30L
    const val MAX_DATES_PER_RUN = 7

    fun selectDates(dateTexts: Collection<String>, today: LocalDate): List<LocalDate> {
        val oldest = today.minusDays(LOOKBACK_DAYS)
        return dateTexts.asSequence()
            .mapNotNull { text -> runCatching { LocalDate.parse(text.take(10)) }.getOrNull() }
            .filter { date -> !date.isAfter(today) && !date.isBefore(oldest) }
            .distinct()
            .sortedDescending()
            .take(MAX_DATES_PER_RUN)
            .toList()
    }
}
