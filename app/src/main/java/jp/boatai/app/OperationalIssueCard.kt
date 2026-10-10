package jp.boatai.app

import androidx.compose.foundation.layout.Column
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
fun OperationalIssueCard(
    issues: List<OperationalIssue>,
    suppressedByDataIssue: Boolean,
    onRetry: () -> Unit
) {
    if (issues.isEmpty() || suppressedByDataIssue) return

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)
    ) {
        Column(Modifier.padding(12.dp)) {
            Text("自動チェックで問題を検知", fontWeight = FontWeight.Bold)
            issues.take(3).forEach { issue ->
                Text(issue.title, fontWeight = FontWeight.SemiBold)
                Text(issue.detail, style = MaterialTheme.typography.bodySmall)
                Text(issue.guidance, style = MaterialTheme.typography.bodySmall)
            }
            OutlinedButton(onClick = onRetry, modifier = Modifier.fillMaxWidth()) {
                Text("今すぐ再取得")
            }
        }
    }
}
