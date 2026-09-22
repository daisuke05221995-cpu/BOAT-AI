package jp.boatai.app

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@Composable
fun NotificationSettingsCard(ui: BoatUiState, vm: BoatViewModel) {
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) vm.setNotificationsEnabled(true) else vm.setNotificationsEnabled(false)
    }
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text("通知", fontWeight = FontWeight.Bold)
            Text("締切10分前・購入結果反映・アプリ更新を通知")
            OutlinedButton(onClick = {
                if (ui.notificationsEnabled) vm.setNotificationsEnabled(false)
                else if (Build.VERSION.SDK_INT >= 33) permission.launch(Manifest.permission.POST_NOTIFICATIONS)
                else vm.setNotificationsEnabled(true)
            }) {
                Text(if (ui.notificationsEnabled) "通知をオフ" else "通知をオン")
            }
        }
    }
}
