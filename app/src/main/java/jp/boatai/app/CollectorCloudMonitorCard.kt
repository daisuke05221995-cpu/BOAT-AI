package jp.boatai.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** Shown on the normal-use Android; this is not a prompt to buy a race. */
@Composable
internal fun CollectorCloudMonitorCard(
    status: CollectorCloudMonitorState,
    onRefresh: () -> Unit,
    remote: CollectorRemoteState = CollectorRemoteState(),
    remoteConfigured: Boolean = false,
    collectorMode: Boolean = false,
    onRemoteRefresh: () -> Unit = {}
) {
    val title = when (status.monitoringState) {
        "ACTIVE" -> "2台目の取得監視：正常"
        "STALE" -> "2台目の取得監視：通信停止の可能性"
        "NEVER_CONNECTED" -> "2台目の取得監視：受信履歴なし"
        else -> "2台目の取得監視：確認待ち"
    }
    val warning = status.monitoringState == "STALE" || status.error != null
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(title, modifier = Modifier.weight(1f), fontWeight = FontWeight.Bold,
                    color = if (warning) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface)
                OutlinedButton(onClick = onRefresh, enabled = !status.loading) { Text("再確認") }
            }
            if (status.monitoringState != "UNKNOWN") {
                Text("直近10分の受信端末：${status.activeDevices}台 / 最終受信：${monitorTime(status.lastReceivedAt)}")
                Text("前回の端末受信から ${status.lastReceivedAgeSeconds?.let { "${it / 60}分${it % 60}秒" } ?: "不明"} / 取得した開催 ${status.lastRaceCount ?: 0}R",
                    style = MaterialTheme.typography.bodySmall)
            }
            if (status.monitoringState == "STALE") {
                Text("5分以上受信できていません。2台目の画面・通信・充電状態を確認してください。",
                    color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
            if (status.monitoringState == "NEVER_CONNECTED") {
                Text("2台目からまだ受信していません。共有キーの保存と常時取得モードを確認してください。",
                    style = MaterialTheme.typography.bodySmall)
            }
            status.error?.let {
                Text("監視APIに接続できません：$it（稼働・停止の判定は保留）",
                    color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
            Text("確認：${monitorTime(status.lastCheckedAt)} / この表示は取得状況のみ。予想の推奨・見送りには使用しません。",
                style = MaterialTheme.typography.bodySmall)
            if (!collectorMode) {
                Button(onClick = onRemoteRefresh,
                    enabled = remoteConfigured && !remote.submitting,
                    modifier = Modifier.fillMaxWidth()) {
                    Text(if (remote.submitting) "指示を送信中" else "2台目に今すぐ再取得を指示")
                }
                if (remoteConfigured && status.monitoringState != "ACTIVE") {
                    Text("2台目の監視が正常ではありません。送信は試せますが、クラウド側で拒否された場合は理由を表示します。2台目が受信した保証はありません。",
                        style = MaterialTheme.typography.bodySmall)
                }
                if (!remoteConfigured) Text("遠隔再取得には、設定で1台目にも同じ共有キーを保存してください。",
                    style = MaterialTheme.typography.bodySmall)
                remote.message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                remote.error?.let { Text("遠隔指示：$it", color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall) }
                Text("BOAT AI内のデータ更新のみ実行します。投票・購入・他アプリの操作は行いません。",
                    style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

private fun monitorTime(timestamp: Long?): String = timestamp?.let {
    Instant.ofEpochMilli(it).atZone(ZoneId.of("Asia/Tokyo"))
        .format(DateTimeFormatter.ofPattern("MM/dd HH:mm:ss"))
} ?: "未受信"
