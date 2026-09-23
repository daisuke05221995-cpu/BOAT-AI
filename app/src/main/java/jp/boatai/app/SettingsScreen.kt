package jp.boatai.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@Composable
fun SettingsScreen(ui: BoatUiState, vm: BoatViewModel) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("BOAT AI 設定", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text("普段の予想・購入・結果・損益から設定を分離しました。", style = MaterialTheme.typography.bodySmall)
                    Text("v${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.labelMedium)
                }
            }
        }

        item {
            Text("通知・自動記録", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        }
        item { NotificationSettingsCard(ui, vm) }

        item {
            Text("データ・バックアップ", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        }
        item { BackupCard(ui, vm) }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("戻る操作", fontWeight = FontWeight.Bold)
                    Text("端末の戻るキーは画面を1段ずつ戻します。予想ホームでは誤操作でアプリを終了しません。", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}
