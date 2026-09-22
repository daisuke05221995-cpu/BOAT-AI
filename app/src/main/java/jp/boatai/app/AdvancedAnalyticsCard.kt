package jp.boatai.app

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneId
import java.util.Locale
import kotlin.math.abs

@Composable
fun AdvancedAnalyticsCard(ui: BoatUiState) {
    var period by remember { mutableStateOf(AnalyticsPeriod.ALL) }
    var grouping by remember { mutableStateOf("会場") }
    val today = LocalDate.now(ZoneId.of("Asia/Tokyo"))
    val analytics = remember(ui.predictionHistory, period, today) {
        ProfitAnalytics.build(ui.predictionHistory, period, today)
    }
    val monthStart = YearMonth.from(today).atDay(1)
    val actualSettled = ui.records.filter { it.settled }
    val actualWeek = actualSummary(actualSettled, today.minusDays(6), today)
    val actualMonth = actualSummary(actualSettled, monthStart, today)
    val actualCumulative = actualCumulativeByDay(actualSettled, monthStart, today)

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text("週間・月間累計", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text("購入推奨だけ買った場合", fontWeight = FontWeight.SemiBold)
            Text(
                "直近7日 ${signed(analytics.weekRecommended.profit)} / 回収 ${f1(analytics.weekRecommended.roi)}%　" +
                    "今月 ${signed(analytics.monthRecommended.profit)} / 回収 ${f1(analytics.monthRecommended.roi)}%"
            )
            Text(
                "今月 ${analytics.monthRecommended.hits}/${analytics.monthRecommended.races}的中　" +
                    "購入 ${yen(analytics.monthRecommended.stake)} / 払戻 ${yen(analytics.monthRecommended.payout)}",
                style = MaterialTheme.typography.bodySmall
            )
            Spacer(Modifier.height(6.dp))
            Text("実購入", fontWeight = FontWeight.SemiBold)
            Text("直近7日 ${signed(actualWeek.profit)}　今月 ${signed(actualMonth.profit)}")
            Text(
                "今月 購入 ${yen(actualMonth.stake)} / 払戻 ${yen(actualMonth.payout)}",
                style = MaterialTheme.typography.bodySmall
            )

            HorizontalDivider(Modifier.padding(vertical = 10.dp))
            val monthPoints = analytics.monthCumulativeRecommended
            val recentChange = if (monthPoints.size >= 2) {
                val startIndex = (monthPoints.lastIndex - 7).coerceAtLeast(0)
                monthPoints.last().profit - monthPoints[startIndex].profit
            } else 0
            Text("今月の累計推移", fontWeight = FontWeight.Bold)
            Text(
                "現在 ${signed(analytics.monthRecommended.profit)} / 直近7日で ${signed(recentChange)}",
                fontWeight = FontWeight.SemiBold
            )
            Text(
                when {
                    recentChange > 0 -> "月間累計は直近7日で上向き"
                    recentChange < 0 -> "月間累計は直近7日で下向き"
                    else -> "月間累計は直近7日で横ばい"
                },
                style = MaterialTheme.typography.bodySmall
            )
            Spacer(Modifier.height(6.dp))
            CumulativeProfitChart(monthPoints, actualCumulative)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("購入推奨累計", style = MaterialTheme.typography.bodySmall)
                Text("実購入累計", style = MaterialTheme.typography.bodySmall)
            }
        }
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text("詳細分析・収支グラフ", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                AnalyticsPeriod.entries.forEach { item ->
                    OutlinedButton(onClick = { period = item }) {
                        Text(if (period == item) "● ${item.label}" else item.label)
                    }
                }
            }
            Text(
                "${analytics.summary.races}R / 的中率 ${f1(analytics.summary.hitRate)}% / 回収率 ${f1(analytics.summary.roi)}% / ${signed(analytics.summary.profit)}",
                fontWeight = FontWeight.SemiBold
            )
            Spacer(Modifier.height(8.dp))
            ProfitBarChart(analytics.daily)
            Text("日別収支（最大31日）", style = MaterialTheme.typography.bodySmall)

            HorizontalDivider(Modifier.padding(vertical = 10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("会場", "判定", "1着軸").forEach { label ->
                    OutlinedButton(onClick = { grouping = label }) {
                        Text(if (grouping == label) "● $label" else label)
                    }
                }
            }
            val groups = when (grouping) {
                "判定" -> analytics.byRecommendation
                "1着軸" -> analytics.byFirstLane
                else -> analytics.byVenue
            }
            if (groups.isEmpty()) Text("集計できる確定予想がありません")
            groups.take(8).forEach { group ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("${group.label} ${group.summary.races}R")
                    Text("的中${f1(group.summary.hitRate)}%　回収${f1(group.summary.roi)}%　${signed(group.summary.profit)}")
                }
            }

            HorizontalDivider(Modifier.padding(vertical = 10.dp))
            Text("連勝・連敗", fontWeight = FontWeight.Bold)
            Text(
                "現在 ${if (analytics.streak.current >= 0) "${analytics.streak.current}連勝" else "${-analytics.streak.current}連敗"} / " +
                    "最長 ${analytics.streak.longestWin}連勝・${analytics.streak.longestLoss}連敗"
            )
        }
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text("購入推奨フィルター比較", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text("同じ事前予想を、全レース購入した場合と購入推奨だけに絞った場合で比較", style = MaterialTheme.typography.bodySmall)
            SummaryLine("全予想", analytics.baseline)
            SummaryLine("購入推奨のみ", analytics.adjusted)
            SummaryLine("見送り判定", analytics.returnFocused)
            if (analytics.avoidedLoss > 0) {
                Text("見送りで回避できた仮想損失 ${yen(analytics.avoidedLoss)}", fontWeight = FontWeight.SemiBold)
            }
            if (analytics.baseline.races < 30) {
                Text("まだ${analytics.baseline.races}件です。30件以上から傾向を確認してください。", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

private data class ActualSummary(val stake: Int, val payout: Int) {
    val profit: Int get() = payout - stake
}

private fun actualSummary(records: List<BetRecord>, start: LocalDate, end: LocalDate): ActualSummary {
    val filtered = records.filter { record ->
        val date = runCatching { LocalDate.parse(record.date.take(10)) }.getOrNull()
        date != null && !date.isBefore(start) && !date.isAfter(end)
    }
    return ActualSummary(
        stake = filtered.sumOf { it.stake },
        payout = filtered.sumOf { it.payout }
    )
}

private fun actualCumulativeByDay(records: List<BetRecord>, start: LocalDate, end: LocalDate): List<ProfitPoint> {
    val byDay = records.groupBy { it.date.take(10) }
        .mapValues { (_, values) -> values.sumOf { it.profit } }
    var running = 0
    val points = mutableListOf<ProfitPoint>()
    var day = start
    while (!day.isAfter(end)) {
        running += byDay[day.toString()] ?: 0
        points += ProfitPoint(day.dayOfMonth.toString(), running)
        day = day.plusDays(1)
    }
    return points
}

@Composable
private fun SummaryLine(label: String, summary: AnalyticsSummary) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text("$label ${summary.races}R")
        Text("的中${f1(summary.hitRate)}%　回収${f1(summary.roi)}%　${signed(summary.profit)}")
    }
}

@Composable
private fun ProfitBarChart(points: List<ProfitPoint>) {
    val positive = MaterialTheme.colorScheme.primary
    val negative = MaterialTheme.colorScheme.error
    Canvas(Modifier.fillMaxWidth().height(120.dp)) {
        if (points.isEmpty()) return@Canvas
        val max = points.maxOf { abs(it.profit) }.coerceAtLeast(1)
        val center = size.height / 2f
        drawLine(Color.Gray, Offset(0f, center), Offset(size.width, center), strokeWidth = 1f)
        val width = size.width / points.size
        points.forEachIndexed { index, point ->
            val height = abs(point.profit).toFloat() / max * (center - 4f)
            val left = index * width + width * 0.15f
            val right = (index + 1) * width - width * 0.15f
            val top = if (point.profit >= 0) center - height else center
            val bottom = if (point.profit >= 0) center else center + height
            drawRect(if (point.profit >= 0) positive else negative, Offset(left, top), androidx.compose.ui.geometry.Size(right - left, bottom - top))
        }
    }
}

@Composable
private fun CumulativeProfitChart(recommended: List<ProfitPoint>, actual: List<ProfitPoint>) {
    val recommendationColor = MaterialTheme.colorScheme.primary
    val actualColor = MaterialTheme.colorScheme.tertiary
    Canvas(Modifier.fillMaxWidth().height(150.dp)) {
        val count = maxOf(recommended.size, actual.size)
        if (count < 2) return@Canvas
        val values = (recommended + actual).map { it.profit }
        val maxAbs = values.maxOfOrNull { abs(it) }?.coerceAtLeast(1) ?: 1
        val center = size.height / 2f
        drawLine(Color.Gray, Offset(0f, center), Offset(size.width, center), strokeWidth = 1f)

        fun drawSeries(points: List<ProfitPoint>, color: Color) {
            if (points.size < 2) return
            val step = size.width / (count - 1).coerceAtLeast(1)
            points.zipWithNext().forEachIndexed { index, (a, b) ->
                val y1 = center - (a.profit.toFloat() / maxAbs) * (center - 8f)
                val y2 = center - (b.profit.toFloat() / maxAbs) * (center - 8f)
                drawLine(color, Offset(index * step, y1), Offset((index + 1) * step, y2), strokeWidth = 4f)
            }
        }

        drawSeries(recommended, recommendationColor)
        drawSeries(actual, actualColor)
    }
}

private fun f1(value: Double) = String.format(Locale.US, "%.1f", value)
private fun yen(value: Int) = String.format(Locale.JAPAN, "%,d円", value)
private fun signed(value: Int) = if (value >= 0) "+${yen(value)}" else "-${yen(-value)}"
