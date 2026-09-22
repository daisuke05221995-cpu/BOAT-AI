package jp.boatai.app

import java.time.LocalDate
import java.time.YearMonth

enum class AnalyticsPeriod(val label: String) {
    SEVEN_DAYS("7日"), MONTH("今月"), ALL("全期間")
}

data class AnalyticsSummary(
    val races: Int,
    val hits: Int,
    val stake: Int,
    val payout: Int
) {
    val profit: Int get() = payout - stake
    val hitRate: Double get() = if (races > 0) hits * 100.0 / races else 0.0
    val roi: Double get() = if (stake > 0) payout * 100.0 / stake else 0.0
}

data class ProfitPoint(val label: String, val profit: Int)
data class GroupPerformance(val label: String, val summary: AnalyticsSummary)
data class StreakSummary(val current: Int, val longestWin: Int, val longestLoss: Int)

data class AdvancedAnalytics(
    val summary: AnalyticsSummary,
    val daily: List<ProfitPoint>,
    val monthly: List<ProfitPoint>,
    val byVenue: List<GroupPerformance>,
    val byRank: List<GroupPerformance>,
    val byRecommendation: List<GroupPerformance>,
    val byFirstLane: List<GroupPerformance>,
    val streak: StreakSummary,
    val baseline: AnalyticsSummary,
    val adjusted: AnalyticsSummary,
    val hitFocused: AnalyticsSummary,
    val returnFocused: AnalyticsSummary,
    val avoidedLoss: Int,
    val weekRecommended: AnalyticsSummary,
    val monthRecommended: AnalyticsSummary,
    val monthAll: AnalyticsSummary,
    val monthCumulativeRecommended: List<ProfitPoint>
)

object ProfitAnalytics {
    fun build(
        records: List<PredictionRecord>,
        period: AnalyticsPeriod,
        today: LocalDate = LocalDate.now()
    ): AdvancedAnalytics {
        val settled = records.filter { it.settled }
            .filter { inPeriod(it.date, period, today) }
            .sortedWith(compareBy<PredictionRecord> { it.date }.thenBy { it.raceNumber })
        val eligible = settled.filter { it.evaluationEligible }
        val baseline = summarize(eligible)
        val recommendedRecords = eligible.filter { it.recommended }
        val recommended = summarize(recommendedRecords)
        val skipped = eligible.filterNot { it.recommended }
        val skippedLoss = skipped.sumOf { it.simulatedProfit }

        val allEligible = records.filter { it.settled && it.evaluationEligible }
        val weekStart = today.minusDays(6)
        val monthStart = YearMonth.from(today).atDay(1)
        val weekRecommended = summarize(
            allEligible.filter { it.recommended && inRange(it.date, weekStart, today) }
        )
        val monthRecommendedRecords = allEligible.filter {
            it.recommended && inRange(it.date, monthStart, today)
        }
        val monthRecommended = summarize(monthRecommendedRecords)
        val monthAll = summarize(allEligible.filter { inRange(it.date, monthStart, today) })

        return AdvancedAnalytics(
            summary = summarize(settled),
            daily = settled.groupBy { it.date }.map { (date, values) ->
                ProfitPoint(date.takeLast(5), values.sumOf { it.simulatedProfit })
            }.takeLast(31),
            monthly = settled.groupBy { it.date.take(7) }.map { (month, values) ->
                ProfitPoint(month, values.sumOf { it.simulatedProfit })
            }.takeLast(12),
            byVenue = group(settled) { Venues.name(it.stadiumNumber) },
            byRank = group(settled) { "AI${it.rank}" },
            byRecommendation = group(settled) { it.recommendation.label },
            byFirstLane = group(settled) { "${it.firstLane ?: 0}号艇軸" },
            streak = streak(settled),
            baseline = baseline,
            adjusted = recommended,
            hitFocused = recommended,
            returnFocused = summarize(skipped),
            avoidedLoss = (-skippedLoss).coerceAtLeast(0),
            weekRecommended = weekRecommended,
            monthRecommended = monthRecommended,
            monthAll = monthAll,
            monthCumulativeRecommended = cumulativeByDay(monthRecommendedRecords, monthStart, today)
        )
    }

    fun summarize(records: List<PredictionRecord>) = AnalyticsSummary(
        races = records.size,
        hits = records.count { it.hit },
        stake = records.sumOf { it.simulatedStake },
        payout = records.sumOf { it.simulatedPayout }
    )

    private fun cumulativeByDay(
        records: List<PredictionRecord>,
        start: LocalDate,
        end: LocalDate
    ): List<ProfitPoint> {
        val dailyProfit = records.groupBy { it.date.take(10) }
            .mapValues { (_, values) -> values.sumOf { it.simulatedProfit } }
        var running = 0
        val points = mutableListOf<ProfitPoint>()
        var day = start
        while (!day.isAfter(end)) {
            running += dailyProfit[day.toString()] ?: 0
            points += ProfitPoint(day.dayOfMonth.toString(), running)
            day = day.plusDays(1)
        }
        return points
    }

    private fun group(
        records: List<PredictionRecord>,
        key: (PredictionRecord) -> String
    ): List<GroupPerformance> = records.groupBy(key)
        .map { (label, values) -> GroupPerformance(label, summarize(values)) }
        .sortedWith(compareByDescending<GroupPerformance> { it.summary.roi }.thenByDescending { it.summary.races })

    private fun streak(records: List<PredictionRecord>): StreakSummary {
        var current = 0
        var longestWin = 0
        var longestLoss = 0
        var run = 0
        var lastHit: Boolean? = null
        records.forEach { record ->
            if (lastHit == record.hit) run++ else run = 1
            lastHit = record.hit
            if (record.hit) longestWin = maxOf(longestWin, run) else longestLoss = maxOf(longestLoss, run)
        }
        if (records.isNotEmpty()) {
            val latestHit = records.last().hit
            current = records.asReversed().takeWhile { it.hit == latestHit }.count() * if (latestHit) 1 else -1
        }
        return StreakSummary(current, longestWin, longestLoss)
    }

    private fun inPeriod(dateText: String, period: AnalyticsPeriod, today: LocalDate): Boolean {
        val date = runCatching { LocalDate.parse(dateText.take(10)) }.getOrNull() ?: return false
        return when (period) {
            AnalyticsPeriod.SEVEN_DAYS -> !date.isBefore(today.minusDays(6)) && !date.isAfter(today)
            AnalyticsPeriod.MONTH -> YearMonth.from(date) == YearMonth.from(today)
            AnalyticsPeriod.ALL -> true
        }
    }

    private fun inRange(dateText: String, start: LocalDate, end: LocalDate): Boolean {
        val date = runCatching { LocalDate.parse(dateText.take(10)) }.getOrNull() ?: return false
        return !date.isBefore(start) && !date.isAfter(end)
    }
}
