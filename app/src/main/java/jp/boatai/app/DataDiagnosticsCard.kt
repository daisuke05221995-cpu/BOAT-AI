package jp.boatai.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@Composable
fun DataDiagnosticsCard(
    diagnostics: List<DataSourceDiagnostic>,
    title: String = "データ取得",
    onRetry: (() -> Unit)? = null
) {
    val issue = DataIssuePresenter.present(diagnostics) ?: return
    val container = if (issue.isError) {
        MaterialTheme.colorScheme.errorContainer
    } else {
        MaterialTheme.colorScheme.surfaceVariant
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = container)
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(issue.title, fontWeight = FontWeight.Bold)
                if (onRetry != null) {
                    OutlinedButton(onClick = onRetry) { Text("今すぐ再取得") }
                }
            }
            Text(issue.guidance, style = MaterialTheme.typography.bodySmall)
            issue.diagnostics.forEach { item ->
                val mark = when (item.status) {
                    DiagnosticStatus.ERROR -> "×"
                    DiagnosticStatus.WARNING -> "△"
                    DiagnosticStatus.WAITING -> "…"
                    DiagnosticStatus.OK -> "✓"
                }
                Text(
                    "${mark} ${item.source}：${item.detail}",
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
    }
}
