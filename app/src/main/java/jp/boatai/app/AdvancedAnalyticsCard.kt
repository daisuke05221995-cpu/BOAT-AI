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
import java.util.Locale
import kotlin.math.abs

@Composable
fun AdvancedAnalyticsCard(ui: BoatUiState) {
    var period by remember { mutableStateOf(AnalyticsPeriod.ALL) }
    var grouping by remember { mutableStateOf("会場") }
    val analytics = remember(ui.predictionHistory, period) {
        ProfitAnalytics.build(ui.predictionHistory, period)
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
                listOf("会場", "AI", "1着軸").forEach { label ->
                    OutlinedButton(onClick = { grouping = label }) {
                        Text(if (grouping == label) "● $label" else label)
                    }
                }
            }
            val groups = when (grouping) {
                "AI" -> analytics.byRank
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
            Text("AI補正 A/B比較", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text("同じ事前予想で、自動見送りなし／ありを比較", style = MaterialTheme.typography.bodySmall)
            SummaryLine("補正なし", analytics.baseline)
            SummaryLine("補正あり", analytics.adjusted)
            Text("自動見送りで回避できた損失 ${yen(analytics.avoidedLoss)}", fontWeight = FontWeight.SemiBold)
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("予想スタイル参考比較", fontWeight = FontWeight.Bold)
            Text("的中率重視＝AI S/A帯、回収率重視＝AI B/C帯", style = MaterialTheme.typography.bodySmall)
            SummaryLine("的中率重視", analytics.hitFocused)
            SummaryLine("回収率重視", analytics.returnFocused)
            if (analytics.baseline.races < 30) {
                Text("まだ${analytics.baseline.races}件です。30件以上から参考値として確認してください。", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun SummaryLine(label: String, summary: AnalyticsSummary) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text("$label ${summary.races}R")
        Text("回収${f1(summary.roi)}%　${signed(summary.profit)}")
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

private fun f1(value: Double) = String.format(Locale.US, "%.1f", value)
private fun yen(value: Int) = String.format(Locale.JAPAN, "%,d円", value)
private fun signed(value: Int) = if (value >= 0) "+${yen(value)}" else "-${yen(-value)}"
