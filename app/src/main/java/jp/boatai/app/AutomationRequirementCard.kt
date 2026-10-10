package jp.boatai.app

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
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

internal object AutomationRequirementPolicy {
    fun shouldShowExactAlarmIssue(
        exactAlarmReady: Boolean,
        hasPurchasableRace: Boolean
    ): Boolean = !exactAlarmReady && hasPurchasableRace
}

@Composable
fun AutomationRequirementCard(ui: BoatUiState) {
    val context = LocalContext.current
    val scheduler = remember { NotificationScheduler(context) }
    var exactAlarmReady by remember { mutableStateOf(scheduler.exactAlarmReady) }
    val hasPurchasableRace = ui.races.any { it.isPurchasable() }

    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        exactAlarmReady = scheduler.exactAlarmReady
        if (exactAlarmReady) {
            PredictionTrackingScheduler(context).apply {
                scheduleDailyBootstrap()
                scheduleBootstrapSoon(1_000L)
            }
        }
    }

    if (!AutomationRequirementPolicy.shouldShowExactAlarmIssue(exactAlarmReady, hasPurchasableRace)) return

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer)
    ) {
        Column(Modifier.padding(12.dp)) {
            Text("締切前予想の端末設定が必要です", fontWeight = FontWeight.Bold)
            Text(
                "このままでも自動処理は試みますが、Androidの省電力制御で直前予想が遅れる可能性があります。",
                style = MaterialTheme.typography.bodySmall
            )
            scheduler.requestExactAlarmPermissionIntent()?.let { intent ->
                OutlinedButton(onClick = { launcher.launch(intent) }) {
                    Text("端末設定を開く")
                }
            }
        }
    }
}
