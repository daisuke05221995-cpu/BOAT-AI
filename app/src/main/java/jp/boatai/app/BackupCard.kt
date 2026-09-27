package jp.boatai.app

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
fun BackupCard(ui: BoatUiState, vm: BoatViewModel) {
    val context = LocalContext.current
    var confirmClear by remember { mutableStateOf(false) }
    var localMessage by remember { mutableStateOf<String?>(null) }

    val saveLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")
    ) { uri ->
        if (uri != null) {
            runCatching { DataBackupManager(context).writeBackup(uri) }
                .onSuccess { localMessage = "BOAT-AI-backup.json を保存しました" }
                .onFailure { error -> localMessage = "保存失敗：${error.message ?: "保存先を確認してください"}" }
        }
    }
    val restoreLauncher = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) vm.importBackup(context, uri)
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("データ管理", fontWeight = FontWeight.Bold)
            Text("購入履歴・AI予想履歴・端末学習を1つのバックアップに保存します。")
            Text(
                "累計収支の検証に使う場合は「ファイルに保存」で BOAT-AI-backup.json を保存してください。実購入履歴を含むため、公開場所にはアップロードしないでください。"
            )
            Button(
                onClick = { saveLauncher.launch("BOAT-AI-backup.json") },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("BOAT-AI-backup.json をファイルに保存")
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedButton(onClick = { vm.shareBackup(context) }) { Text("バックアップを共有") }
                OutlinedButton(onClick = { restoreLauncher.launch(arrayOf("application/json", "text/plain")) }) { Text("復元") }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedButton(onClick = { vm.shareCsv(context) }) { Text("CSV出力") }
                if (ui.records.isNotEmpty()) {
                    OutlinedButton(onClick = { confirmClear = true }) { Text("実購入を削除") }
                }
            }
            localMessage?.let { Text(it, fontWeight = FontWeight.SemiBold) }
            ui.actionMessage?.let { Text(it, fontWeight = FontWeight.SemiBold) }
        }
    }

    if (confirmClear) {
        AlertDialog(
            onDismissRequest = { confirmClear = false },
            title = { Text("実購入記録を削除") },
            text = { Text("実購入記録をすべて削除します。先にバックアップすることをおすすめします。") },
            confirmButton = {
                TextButton(onClick = { confirmClear = false; vm.clearRecords() }) { Text("削除する") }
            },
            dismissButton = { TextButton(onClick = { confirmClear = false }) { Text("キャンセル") } }
        )
    }
}
