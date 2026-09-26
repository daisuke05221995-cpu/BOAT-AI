package jp.boatai.app

import java.time.LocalDate

enum class ProfitPeriod(val label: String) {
    TODAY("今日"),
    SEVEN_DAYS("7日"),
    THIRTY_DAYS("30日"),
    MONTH("月"),
    YEAR("年"),
    ALL("全期間")
}

object ProfitPeriodFilter {
    fun includes(period: ProfitPeriod, recordDate: String, anchorDate: LocalDate): Boolean {
        if (period == ProfitPeriod.ALL) return true
        val date = runCatching { LocalDate.parse(recordDate.take(10)) }.getOrNull() ?: return false
        if (date.isAfter(anchorDate)) return false
        return when (period) {
            ProfitPeriod.TODAY -> date == anchorDate
            ProfitPeriod.SEVEN_DAYS -> !date.isBefore(anchorDate.minusDays(6))
            ProfitPeriod.THIRTY_DAYS -> !date.isBefore(anchorDate.minusDays(29))
            ProfitPeriod.MONTH -> date.year == anchorDate.year && date.monthValue == anchorDate.monthValue
            ProfitPeriod.YEAR -> date.year == anchorDate.year
            ProfitPeriod.ALL -> true
        }
    }
}
