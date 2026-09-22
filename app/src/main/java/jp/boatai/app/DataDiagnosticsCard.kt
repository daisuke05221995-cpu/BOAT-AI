package jp.boatai.app

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
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
fun DataDiagnosticsCard(
    diagnostics: List<DataSourceDiagnostic>,
    title: String = "データ取得診断",
    onRetry: (() -> Unit)? = null
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(title, fontWeight = FontWeight.Bold)
                if (onRetry != null) OutlinedButton(onClick = onRetry) { Text("再取得") }
            }
            if (diagnostics.isEmpty()) {
                Text("診断情報はまだありません", style = MaterialTheme.typography.bodySmall)
            }
            diagnostics.forEach { item ->
                val mark = when (item.status) {
                    DiagnosticStatus.OK -> "✓"
                    DiagnosticStatus.WARNING -> "△"
                    DiagnosticStatus.ERROR -> "×"
                    DiagnosticStatus.WAITING -> "…"
                }
                val color = when (item.status) {
                    DiagnosticStatus.ERROR -> MaterialTheme.colorScheme.error
                    DiagnosticStatus.WARNING -> Color(0xFF9A6700)
                    else -> MaterialTheme.colorScheme.onSurface
                }
                Text("$mark ${item.source}：${item.detail}", color = color, style = MaterialTheme.typography.bodySmall)
                Text(
                    Instant.ofEpochMilli(item.checkedAt).atZone(ZoneId.of("Asia/Tokyo")).format(DateTimeFormatter.ofPattern("M/d HH:mm:ss")),
                    style = MaterialTheme.typography.labelSmall
                )
            }
        }
    }
}
