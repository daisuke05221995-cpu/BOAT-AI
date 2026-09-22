package jp.boatai.app

import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier

@Composable
fun ConfirmPurchaseButton(
    label: String,
    summary: String,
    enabled: Boolean,
    modifier: Modifier = Modifier,
    outlined: Boolean = false,
    onConfirm: () -> Unit
) {
    var open by remember { mutableStateOf(false) }
    if (outlined) {
        OutlinedButton(onClick = { open = true }, enabled = enabled, modifier = modifier) { Text(label) }
    } else {
        Button(onClick = { open = true }, enabled = enabled, modifier = modifier) { Text(label) }
    }
    if (open) {
        AlertDialog(
            onDismissRequest = { open = false },
            title = { Text("購入記録の確認") },
            text = { Text(summary) },
            confirmButton = {
                TextButton(onClick = { open = false; onConfirm() }) { Text("この内容で登録") }
            },
            dismissButton = { TextButton(onClick = { open = false }) { Text("戻る") } }
        )
    }
}
