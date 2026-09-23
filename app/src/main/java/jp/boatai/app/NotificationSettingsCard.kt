package jp.boatai.app

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@Composable
fun NotificationSettingsCard(ui: BoatUiState, vm: BoatViewModel) {
    val context = LocalContext.current
    val scheduler = NotificationScheduler(context)
    var exactAlarmReady by remember { mutableStateOf(scheduler.exactAlarmReady) }

    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) vm.setNotificationsEnabled(true) else vm.setNotificationsEnabled(false)
    }
    val exactAlarmPermission = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        exactAlarmReady = scheduler.exactAlarmReady
        if (exactAlarmReady) {
            PredictionTrackingScheduler(context).apply {
                scheduleDailyBootstrap()
                scheduleBootstrapSoon(1_000L)
            }
        }
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("事前予想の自動記録", fontWeight = FontWeight.Bold)
            Text("購入推奨アラートのON/OFFに関係なく、全レースの締切前予想を結果・損益検証用に保存します。")
            Text(
                if (exactAlarmReady) {
                    "正確な時刻で記録：有効"
                } else {
                    "正確な時刻で記録：要設定（端末都合で締切後まで遅れる場合があります）"
                },
                style = MaterialTheme.typography.bodySmall,
                color = if (exactAlarmReady) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
            )
            if (!exactAlarmReady) {
                OutlinedButton(onClick = {
                    scheduler.requestExactAlarmPermissionIntent()?.let(exactAlarmPermission::launch)
                }) {
                    Text("締切前の自動記録を正確にする")
                }
                Text(
                    "Androidの「アラームとリマインダー」でBOAT AIを許可してください。購入推奨通知を使わない場合でも、この設定は事前予想の保存精度に使います。",
                    style = MaterialTheme.typography.bodySmall
                )
            }

            Text("購入推奨アラート", fontWeight = FontWeight.Bold)
            Text("全国全レースを締切約5分前に再確認し、AI判定＋最新公式3連単オッズの両方を通ったレースだけ通知します。")
            Text("買い目・オッズ・推奨金額も通知に表示。毎朝6:30に当日レースを自動登録し、端末再起動後も復旧します。", style = MaterialTheme.typography.bodySmall)

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = {
                    if (ui.notificationsEnabled) {
                        vm.setNotificationsEnabled(false)
                    } else if (Build.VERSION.SDK_INT >= 33) {
                        permission.launch(Manifest.permission.POST_NOTIFICATIONS)
                    } else {
                        vm.setNotificationsEnabled(true)
                    }
                }) {
                    Text(if (ui.notificationsEnabled) "アラートをオフ" else "アラートをオン")
                }
            }

            if (ui.notificationsEnabled) {
                Text(
                    if (exactAlarmReady) "5分前の正確なアラーム：有効" else "5分前通知も正確なアラーム設定が必要です",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (exactAlarmReady) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                )
            }

            Text("見送りレースは通知しません。購入は自動実行せず、最終判断と投票はユーザーが行います。", style = MaterialTheme.typography.bodySmall)
        }
    }
}
