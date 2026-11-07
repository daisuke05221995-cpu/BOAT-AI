package jp.boatai.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** Displayed only on the deliberately selected collection phone. */
@Composable
internal fun CollectorDashboardScreen(
    ui: BoatUiState,
    vm: BoatViewModel,
    onOpenSettings: () -> Unit
) {
    val odds = ui.liveOddsRefresh
    val available = ui.races.count { it.isPurchasable() }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("常時取得モード：有効", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text("この端末でBOAT AIを前面表示している間、画面消灯を防ぎ、既存の60秒更新を継続します。", style = MaterialTheme.typography.bodyMedium)
                    Text("他のアプリへ切り替えたり強制終了すると前面取得は停止します。充電中の熱や通信切断に注意してください。", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        item {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("開催・展示の取得", fontWeight = FontWeight.Bold)
                    Text("対象日 ${ui.date} / 開催データ ${ui.races.size}R / 締切前 $available R")
                    Text("最終取得（端末時刻） ${collectorTime(ui.programUpdatedAt)}", style = MaterialTheme.typography.bodySmall)
                    Text(if (ui.loading) "現在更新中" else "自動更新待機中（約60秒）", style = MaterialTheme.typography.bodySmall)
                    ui.error?.let { Text("取得エラー：$it", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                    ui.diagnostics.filter { it.status != DiagnosticStatus.OK }.take(2).forEach { diagnostic ->
                        Text("${diagnostic.source}: ${diagnostic.detail}", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
        item {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("公式3連単オッズ取得", fontWeight = FontWeight.Bold)
                    Text("試行 ${odds.attempted}R / 成功 ${odds.succeeded}R / 失敗 ${odds.failed}R")
                    Text("最終試行 ${collectorTime(odds.lastCheckedAt)} / 最終成功 ${collectorTime(odds.lastSuccessAt)}", style = MaterialTheme.typography.bodySmall)
                    Text("締切30分以内を優先。前面取得の対象となるレースのみ試行します。", style = MaterialTheme.typography.bodySmall)
                    odds.lastError?.let { Text("直近エラー：$it", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
        item {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("クラウドとの接続", fontWeight = FontWeight.Bold)
                    Text("クラウド読取 ${collectorTime(ui.cloudForecast.lastSyncAt)}")
                    Text("端末からクラウドへのデータ送信：未接続。取得成功をクラウド予想の成功とは扱いません。", style = MaterialTheme.typography.bodySmall)
                    ui.cloudForecast.error?.let { Text("クラウド読取エラー：$it", style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = vm::refresh, modifier = Modifier.weight(1f)) { Text("今すぐ更新") }
                OutlinedButton(onClick = onOpenSettings, modifier = Modifier.weight(1f)) { Text("設定") }
            }
        }
        item { OutlinedButton(onClick = { vm.setCollectorModeEnabled(false) }, modifier = Modifier.fillMaxWidth()) { Text("常時取得モードを終了") } }
    }
}

@Composable
internal fun CollectorModeSettingsCard(enabled: Boolean, onChanged: (Boolean) -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Column(Modifier.weight(1f)) {
                    Text("2台目スマホ：常時取得モード", fontWeight = FontWeight.Bold)
                    Text("この端末でのみ有効。通常の購入記録やもう1台の設定は変更しません。", style = MaterialTheme.typography.bodySmall)
                }
                Switch(checked = enabled, onCheckedChange = onChanged)
            }
            Text("画面点灯維持・本日データへの自動切替・取得状況の表示。クラウドへの書込や自動投票はまだ行いません。", style = MaterialTheme.typography.bodySmall)
        }
    }
}

private fun collectorTime(timestamp: Long?): String = timestamp?.let {
    Instant.ofEpochMilli(it).atZone(ZoneId.of("Asia/Tokyo"))
        .format(DateTimeFormatter.ofPattern("MM/dd HH:mm:ss"))
} ?: "まだありません"
