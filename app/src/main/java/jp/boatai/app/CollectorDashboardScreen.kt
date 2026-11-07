package jp.boatai.app

import android.content.Intent
import android.provider.Settings
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.input.PasswordVisualTransformation
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
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    Text("1台目からの購入準備", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    val handoff = ui.collectorPurchaseInbox
                    if (handoff == null) {
                        Text("買い目の受信待機中。1台目の『買い目を2台目へ送る』で転送できます。",
                            style = MaterialTheme.typography.bodySmall)
                    } else {
                        Text("${handoff.session.selectedRaces.size}レース / ${handoff.session.selectedTicketCount}点 / 合計${handoff.session.selectedStake}円",
                            fontWeight = FontWeight.Bold)
                        handoff.session.selectedRaces.forEach { race ->
                            Text("${race.venueName} ${race.raceNumber}R：" +
                                race.tickets.joinToString(" / ") { "${it.combination} ${it.amount}円" },
                                style = MaterialTheme.typography.bodySmall)
                        }
                        Button(onClick = vm::openCollectorPurchaseHandoff, modifier = Modifier.fillMaxWidth()) {
                            Text("買い目をコピーして公式投票へ")
                        }
                        OutlinedButton(onClick = vm::startCollectorPurchaseAutomationTest,
                            modifier = Modifier.fillMaxWidth()) {
                            Text("公式Androidアプリの操作検証")
                        }
                        OutlinedButton(onClick = vm::copyOfficialAppControlMap,
                            modifier = Modifier.fillMaxWidth()) {
                            Text("公式アプリ画面の操作項目をコピー")
                        }
                        Text("操作検証は締切まで2分以上・合計5,000円以内で開始できます。現段階で買い目入力や投票確定は自動実行しません。",
                            style = MaterialTheme.typography.bodySmall)
                        Text("注意：これは購入準備です。公式サイトでご自身が投票を確定してください。投票結果は1台目で記録します。",
                            style = MaterialTheme.typography.bodySmall)
                        OutlinedButton(onClick = vm::dismissCollectorPurchaseHandoff, modifier = Modifier.fillMaxWidth()) {
                            Text("この買い目を閉じる")
                        }
                    }
                    ui.purchaseHandoff.message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                    ui.purchaseHandoff.error?.let { Text(it, color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall) }
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
                    Text("取得監査の送信：${if (!ui.collectorUpload.configured) "共有キー未設定" else if (ui.collectorUpload.uploading) "送信中" else "待機中"}")
                    Text("最後の受信確認 ${collectorTime(ui.collectorUpload.lastAcceptedAt)}", style = MaterialTheme.typography.bodySmall)
                    Text("件数・端末受信時刻のみを送信。オッズ値・展示値・購入履歴は送らず、クラウド予想にも採用しません。", style = MaterialTheme.typography.bodySmall)
                    ui.collectorUpload.error?.let { Text("送信エラー：$it", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                    ui.cloudForecast.error?.let { Text("クラウド読取エラー：$it", style = MaterialTheme.typography.bodySmall) }
                    Text("遠隔再取得指示：${collectorTime(ui.collectorRemote.lastAcceptedAt)}", style = MaterialTheme.typography.bodySmall)
                    ui.collectorRemote.error?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
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
internal fun CollectorModeSettingsCard(ui: BoatUiState, vm: BoatViewModel) {
    var tokenInput by remember { mutableStateOf("") }
    val context = LocalContext.current
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Column(Modifier.weight(1f)) {
                    Text("2台目スマホ：常時取得モード", fontWeight = FontWeight.Bold)
                    Text("この端末でのみ有効。通常の購入記録やもう1台の設定は変更しません。", style = MaterialTheme.typography.bodySmall)
                }
                Switch(checked = ui.collectorModeEnabled, onCheckedChange = vm::setCollectorModeEnabled)
            }
            Text("画面点灯維持・本日データへの自動切替・取得状況の表示。予想や実購入履歴は別管理です。", style = MaterialTheme.typography.bodySmall)
            OutlinedTextField(
                value = tokenInput,
                onValueChange = { tokenInput = it.take(200) },
                label = { Text("クラウド接続の共有キー") },
                visualTransformation = PasswordVisualTransformation(),
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { vm.configureCollectorToken(tokenInput); tokenInput = "" }, enabled = tokenInput.length >= 32) {
                    Text("共有キーを保存")
                }
                OutlinedButton(onClick = vm::clearCollectorToken, enabled = ui.collectorUpload.configured) {
                    Text("キー削除")
                }
            }
            Text("保存状況：${if (ui.collectorUpload.configured) "設定済み（端末内で暗号化）" else "未設定"}", style = MaterialTheme.typography.bodySmall)
            ui.collectorUpload.error?.let { Text("設定／送信エラー：$it", style = MaterialTheme.typography.bodySmall) }
            Text("2台目は監査送信・指示受信、1台目は遠隔再取得に使います。両端末でクラウド側のCOLLECTOR_INGEST_TOKENと同じキーを保存してください。チャットやGitHubには貼らないでください。", style = MaterialTheme.typography.bodySmall)
            OutlinedButton(onClick = {
                context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }, modifier = Modifier.fillMaxWidth()) { Text("Androidのユーザー補助でBOAT AIを有効にする") }
            Text("画面操作機能は2台目でのみ有効にしてください。表示中の公式アプリの画面を読み取れる権限です。確認作業が終わったら無効にできます。",
                style = MaterialTheme.typography.bodySmall)
        }
    }
}

private fun collectorTime(timestamp: Long?): String = timestamp?.let {
    Instant.ofEpochMilli(it).atZone(ZoneId.of("Asia/Tokyo"))
        .format(DateTimeFormatter.ofPattern("MM/dd HH:mm:ss"))
} ?: "まだありません"
