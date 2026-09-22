package jp.boatai.app

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.util.Locale

@Composable
fun HistoricalBacktestCard() {
    val context = LocalContext.current
    val repository = remember { HistoricalBacktestRepository(context) }
    var refreshKey by remember { mutableIntStateOf(0) }
    var loading by remember { mutableStateOf(true) }
    var loadResult by remember { mutableStateOf(HistoricalBacktestLoadResult(null)) }
    var selectedMonth by rememberSaveable { mutableStateOf<Int?>(null) }

    LaunchedEffect(refreshKey) {
        loading = true
        loadResult = repository.load()
        loading = false
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text("2026年 AI過去バックテスト", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text("自分で購入していなくても、公式の過去レースで購入価値を検証", style = MaterialTheme.typography.bodySmall)
                }
                OutlinedButton(onClick = { refreshKey++ }, enabled = !loading) { Text("更新") }
            }

            if (loading && loadResult.data == null) {
                Spacer(Modifier.height(12.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(modifier = Modifier.height(22.dp), strokeWidth = 2.dp)
                    Text("　2026年データを取得中…")
                }
                return@Column
            }

            val data = loadResult.data
            if (data == null) {
                Spacer(Modifier.height(8.dp))
                Text(loadResult.error ?: "バックテストデータを取得できません", color = MaterialTheme.colorScheme.error)
                return@Column
            }

            loadResult.error?.let {
                Spacer(Modifier.height(6.dp))
                Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
            }

            Spacer(Modifier.height(10.dp))
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                if (selectedMonth == null) {
                    Button(onClick = { selectedMonth = null }) { Text("${data.year}年") }
                } else {
                    OutlinedButton(onClick = { selectedMonth = null }) { Text("${data.year}年") }
                }
                data.months.forEach { period ->
                    val month = period.month ?: return@forEach
                    if (selectedMonth == month) {
                        Button(onClick = { selectedMonth = month }) { Text("${month}月") }
                    } else {
                        OutlinedButton(onClick = { selectedMonth = month }) { Text("${month}月") }
                    }
                }
            }

            val period = selectedMonth?.let { month -> data.months.firstOrNull { it.month == month } }
                ?: data.yearSummary
            val title = period.month?.let { "${period.year}年${it}月" } ?: "${period.year}年 年間"

            Spacer(Modifier.height(10.dp))
            Text(title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            if (period.month == data.months.lastOrNull()?.month) {
                Text("集計 ${data.dataThrough} まで", style = MaterialTheme.typography.bodySmall)
            }

            Spacer(Modifier.height(8.dp))
            Text("購入推奨 ${period.purchaseRaces}レース / 見送り ${period.skippedRaces}レース", fontWeight = FontWeight.SemiBold)
            Text("判定対象 ${period.evaluatedRaces}レース / 判定対象外 ${period.unavailableRaces}レース")
            Text("購入率 ${pct(period.purchaseRate)}")

            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("購入推奨だけ買った場合", fontWeight = FontWeight.SemiBold)
            Text("的中 ${period.purchaseHits}/${period.purchaseRaces}　的中率 ${pct(period.hitRate)}")
            Text("購入 ${yen(period.stake)} / 払戻 ${yen(period.payout)}")
            Text("損益 ${signedYen(period.profit)}　回収率 ${pct(period.roi)}", fontWeight = FontWeight.Bold)

            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("全予想4点の的中 ${period.allPredictionHits}/${period.evaluatedRaces}", style = MaterialTheme.typography.bodySmall)
            Text("見送りのうち4点予想自体は的中 ${period.skippedPredictionHits}レース", style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(6.dp))
            Text(
                "2025年末までの学習状態から日ごとに予想→結果学習を繰り返したバックテストです。" +
                    "1レース${yen(data.simulationBudget)}を4点に配分。過去の締切オッズが公開データにないため、オッズ取得後の最終見送り判定だけは含みません。",
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

private fun yen(value: Int): String = String.format(Locale.JAPAN, "%,d円", value)
private fun signedYen(value: Int): String = if (value >= 0) "+${yen(value)}" else "-${yen(-value)}"
private fun pct(value: Double): String = String.format(Locale.US, "%.1f%%", value)
