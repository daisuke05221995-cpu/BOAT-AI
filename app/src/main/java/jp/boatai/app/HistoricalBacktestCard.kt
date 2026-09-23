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
                    Text("2026年 AI値戦略検証", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text("実購入と無関係に、過去レース＋過去3連単オッズで購入価値を検証", style = MaterialTheme.typography.bodySmall)
                }
                OutlinedButton(onClick = { refreshKey++ }, enabled = !loading) { Text("更新") }
            }

            if (loading && loadResult.data == null) {
                Spacer(Modifier.height(12.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(modifier = Modifier.height(22.dp), strokeWidth = 2.dp)
                    Text("　戦略検証データを取得中…")
                }
                return@Column
            }

            val data = loadResult.data
            if (data == null) {
                Spacer(Modifier.height(8.dp))
                Text(loadResult.error ?: "戦略検証データを取得できません", color = MaterialTheme.colorScheme.error)
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
                    Button(onClick = { selectedMonth = null }) { Text("検証合計") }
                } else {
                    OutlinedButton(onClick = { selectedMonth = null }) { Text("検証合計") }
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
            val title = period.month?.let { "${period.year}年${it}月" } ?: "${period.year}年 5〜9月運用検証合計"

            Spacer(Modifier.height(10.dp))
            Text(title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text(period.phase, style = MaterialTheme.typography.bodySmall)
            if (period.month == data.months.lastOrNull()?.month || period.month == null) {
                Text("データ ${data.dataThrough} まで", style = MaterialTheme.typography.bodySmall)
            }

            if (!period.statsAvailable) {
                Spacer(Modifier.height(8.dp))
                Text(
                    if ((period.month ?: 0) <= 4) {
                        "この月はモデル学習・設定校正に使用したため、独立した運用成績としては表示しません。"
                    } else {
                        "この月の運用検証データはまだありません。"
                    },
                    style = MaterialTheme.typography.bodyMedium
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    "成績を後付けで良く見せないため、設定選定に使った期間と運用評価期間を分けています。",
                    style = MaterialTheme.typography.bodySmall
                )
                return@Column
            }

            Spacer(Modifier.height(8.dp))
            Text("購入推奨 ${period.purchaseRaces}レース / 見送り ${period.skippedRaces}レース", fontWeight = FontWeight.SemiBold)
            Text("オッズ判定対象 ${period.evaluatedRaces}レース / オッズ欠損 ${period.unavailableRaces}レース")
            Text("購入率 ${pct(period.purchaseRate)}")

            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("購入推奨だけ1レース${yen(data.simulationBudget)}で買った場合", fontWeight = FontWeight.SemiBold)
            Text("的中 ${period.purchaseHits}/${period.purchaseRaces}　的中率 ${pct(period.hitRate)}")
            Text("購入 ${yen(period.stake)} / 払戻 ${yen(period.payout)}")
            Text("損益 ${signedYen(period.profit)}　回収率 ${pct(period.roi)}", fontWeight = FontWeight.Bold)

            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text(
                if (data.oddsFinalGateIncluded) {
                    "過去3連単オッズを使った期待値判定を含むv12ウォークフォワード検証です。"
                } else {
                    "オッズ最終判定を含まない参考検証です。"
                },
                style = MaterialTheme.typography.bodySmall
            )
            Text(
                "5〜9月は各月の開始前までの情報だけで設定を決めて評価しています。1〜4月は学習・校正期間のため運用ROIには含めません。",
                style = MaterialTheme.typography.bodySmall
            )
            if (data.releaseDeferredForIndependentValidation) {
                Text(
                    "2026年の数値だけでは公開判定にせず、2023〜2025年の独立検証を別途要求しています。",
                    style = MaterialTheme.typography.bodySmall,
                    fontWeight = FontWeight.SemiBold
                )
            }
        }
    }
}

private fun yen(value: Int): String = String.format(Locale.JAPAN, "%,d円", value)
private fun signedYen(value: Int): String = if (value >= 0) "+${yen(value)}" else "-${yen(-value)}"
private fun pct(value: Double): String = String.format(Locale.US, "%.1f%%", value)
