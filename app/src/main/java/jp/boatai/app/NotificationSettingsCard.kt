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
import androidx.compose.material3.Switch
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
    val purchaseAssist = PurchaseAssistSettings(context)
    var autoPrepare by remember { mutableStateOf(purchaseAssist.autoPrepareEnabled) }

    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        vm.setNotificationsEnabled(granted)
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column(Modifier.weight(1f)) {
                    Text("購入推奨通知", fontWeight = FontWeight.Bold)
                    Text(
                        if (ui.notificationsEnabled) "購入推奨が出たレースだけ通知します。" else "通知はOFFです。",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                Switch(
                    checked = ui.notificationsEnabled,
                    onCheckedChange = { enabled ->
                        if (!enabled) {
                            vm.setNotificationsEnabled(false)
                        } else if (Build.VERSION.SDK_INT >= 33) {
                            permission.launch(Manifest.permission.POST_NOTIFICATIONS)
                        } else {
                            vm.setNotificationsEnabled(true)
                        }
                    }
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Column(Modifier.weight(1f)) {
                    Text("AI購入準備", fontWeight = FontWeight.Bold)
                    Text(
                        if (autoPrepare) {
                            "購入推奨の買い目・金額を投票待ちへ自動保存します。"
                        } else {
                            "投票待ちの自動作成はOFFです。"
                        },
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                Switch(
                    checked = autoPrepare,
                    onCheckedChange = { enabled ->
                        purchaseAssist.setAutoPrepareEnabled(enabled)
                        autoPrepare = enabled
                    }
                )
            }

            Text(
                "実際の投票送信は自動実行しません。公式画面で最終確認して投票します。",
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}
