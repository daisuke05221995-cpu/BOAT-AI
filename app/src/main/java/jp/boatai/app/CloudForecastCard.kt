package jp.boatai.app

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
internal fun CloudForecastCard(state: CloudForecastSyncState, onRefresh: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("クラウド取得状況", fontWeight = FontWeight.SemiBold)
            val batch = state.batch
            if (batch != null) {
                Text("対象 ${batch.races.size}R / 購入推奨 ${batch.buyCount}R / 見送り ${batch.skipCount}R",
                    style = MaterialTheme.typography.bodySmall)
                Text("待機 ${batch.pendingCount}R / 取得不可 ${batch.unavailableCount}R",
                    style = MaterialTheme.typography.bodySmall)
                val leadingReason = batch.races.values.filter { it.status == "UNAVAILABLE" }
                    .mapNotNull { it.reason }.groupingBy { it }.eachCount()
                    .maxByOrNull { it.value }
                leadingReason?.let { (code, count) ->
                    Text("主な取得不可理由：$code（${count}R）", style = MaterialTheme.typography.labelSmall)
                }
                val syncedTime = state.lastSyncAt?.let {
                    Instant.ofEpochMilli(it).atZone(ZoneId.of("Asia/Tokyo"))
                        .format(DateTimeFormatter.ofPattern("HH:mm:ss"))
                }
                Text("最終同期 ${syncedTime ?: "不明"}", style = MaterialTheme.typography.labelSmall)
            } else {
                Text(if (state.loading) "クラウドを確認中…" else "クラウドの取得結果はまだありません",
                    style = MaterialTheme.typography.bodySmall)
            }
            state.error?.let { error ->
                Text("同期失敗：$error", style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.error)
            }
            Text("スマホを閉じていてもサーバー側で収集。取得不可はAIの見送り・的中率に含めません。",
                style = MaterialTheme.typography.labelSmall)
            TextButton(onClick = onRefresh, enabled = !state.loading) { Text("クラウドを再確認") }
        }
    }
}

@Composable
internal fun CloudRaceDetailCard(forecast: CloudRaceForecast?, loading: Boolean, onRefresh: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("クラウド予想（別枠・読取専用）", fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleMedium)
            if (forecast == null) {
                Text(if (loading) "クラウド同期中…" else "このレースのクラウド記録は未取得です",
                    style = MaterialTheme.typography.bodySmall)
            } else {
                val headline = when (forecast.status) {
                    "READY" -> if (forecast.decision == "BUY") "購入推奨" else "見送り"
                    "UNAVAILABLE" -> "取得不可"
                    else -> "直前情報待ち"
                }
                Text(headline, fontWeight = FontWeight.SemiBold)
                if (forecast.status == "READY" && forecast.decision == "BUY") {
                    forecast.combinations.forEachIndexed { index, combination ->
                        Text("$combination　${String.format(Locale.JAPAN, "%,d", forecast.stakes[index])}円",
                            style = MaterialTheme.typography.bodyMedium)
                    }
                    val total = forecast.stakes.sum()
                    Text("合計 ${String.format(Locale.JAPAN, "%,d", total)}円",
                        style = MaterialTheme.typography.bodySmall)
                }
                forecast.reason?.let { Text("状態理由：$it", style = MaterialTheme.typography.labelSmall) }
                forecast.forecastCompletedAt?.let { stamp ->
                    val time = runCatching {
                        Instant.parse(stamp).atZone(ZoneId.of("Asia/Tokyo"))
                            .format(DateTimeFormatter.ofPattern("HH:mm:ss"))
                    }.getOrNull()
                    if (time != null) Text("確定 $time（日本時間）", style = MaterialTheme.typography.labelSmall)
                }
            }
            Text("クラウド側の判定です。端末内のAI予想・実購入記録とはまだ統合していません。",
                style = MaterialTheme.typography.labelSmall)
            TextButton(onClick = onRefresh, enabled = !loading) { Text("クラウドを再確認") }
        }
    }
}
