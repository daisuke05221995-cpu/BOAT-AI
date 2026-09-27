package jp.boatai.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
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
import java.util.Locale

@Composable
fun FocusPredictionCard(
    race: RaceData,
    raceBudget: Int,
    purchased: Boolean,
    pendingPurchaseExists: Boolean
) {
    val context = LocalContext.current
    var mode by remember(race.id) { mutableStateOf(FocusMode.FOUR) }
    var actionMessage by remember(race.id) { mutableStateOf<String?>(null) }
    val selection = remember(race.id, mode) { FocusPredictionStrategy.selection(race, mode) }
    val picks = remember(race.id, mode, raceBudget) {
        FocusPredictionStrategy.purchasePicks(race, mode, raceBudget)
    }
    val focusStore = remember(context) { FocusPredictionHistoryStore(context.applicationContext) }
    val fourSummary = remember(race.id) { focusStore.summary(FocusMode.FOUR) }
    val fiveSummary = remember(race.id) { focusStore.summary(FocusMode.FIVE) }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("フォーカス予想", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text(
                "Model Aの120通り確率を、競輪アプリのような『軸＋相手広げ』の形へまとめた別戦略です。従来のAI購入判断は変更しません。",
                style = MaterialTheme.typography.bodySmall
            )
            Spacer(Modifier.height(6.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                FocusMode.values().forEach { option ->
                    TextButton(
                        onClick = { mode = option; actionMessage = null },
                        modifier = Modifier.weight(1f)
                    ) {
                        Text(option.label, fontWeight = if (mode == option) FontWeight.Bold else FontWeight.Normal)
                    }
                }
            }

            if (selection == null) {
                Text("Model Aの120通り確率が揃うと表示されます。", style = MaterialTheme.typography.bodySmall)
                return@Column
            }

            selection.patterns.forEachIndexed { index, pattern ->
                if (index > 0) HorizontalDivider(Modifier.padding(vertical = 6.dp))
                Text("${index + 1}. ${pattern.notation}", fontWeight = FontWeight.SemiBold)
                Text(pattern.combinations.joinToString(" / "), style = MaterialTheme.typography.bodySmall)
            }

            Spacer(Modifier.height(8.dp))
            Text(
                "実買い目 ${selection.combinations.size}点 / Model A合計確率 ${String.format(Locale.US, "%.1f", selection.coverageProbability * 100.0)}%",
                fontWeight = FontWeight.Bold
            )
            Text(
                "最低 ${focusMoney(selection.minimumStake)}。現在予算 ${focusMoney(raceBudget)}" +
                    if (picks.isEmpty()) "（予算不足または予想未確定）" else " / 配分 ${focusMoney(picks.sumOf { it.recommendedStake })}",
                style = MaterialTheme.typography.bodySmall
            )

            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("フォーカス累計（この機能導入後）", fontWeight = FontWeight.SemiBold)
            FocusSummaryLine("4択", fourSummary)
            FocusSummaryLine("5択", fiveSummary)
            Text(
                "4択・5択は締切前に別々に固定保存し、既存value-v1の監査済み成績には混ぜません。",
                style = MaterialTheme.typography.bodySmall
            )

            Spacer(Modifier.height(8.dp))
            Button(
                onClick = {
                    val existing = PendingPurchaseStore(context).load()
                    if (existing != null) {
                        actionMessage = "未確定の投票待ちがあります。先に実購入として確定するか、購入しなかった場合は破棄してください"
                    } else {
                        val session = PendingPurchaseSession.create(listOf(race to picks), mode.strategyId)
                        if (session == null) {
                            actionMessage = "100円単位のフォーカス買い目を作成できませんでした"
                        } else {
                            PendingPurchaseStore(context).save(session)
                            runCatching { OfficialBetLauncher.launch(context, session) }
                                .onSuccess { actionMessage = it.message }
                                .onFailure { actionMessage = it.message ?: "公式投票画面を開けませんでした" }
                        }
                    }
                },
                enabled = race.isPurchasable() && picks.isNotEmpty() && !purchased && !pendingPurchaseExists,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    when {
                        purchased -> "このレースは購入済み"
                        pendingPurchaseExists -> "投票待ちを先に確定してください"
                        else -> "${mode.label}を公式投票へ"
                    }
                )
            }
            actionMessage?.let {
                Spacer(Modifier.height(6.dp))
                Text(it, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun FocusSummaryLine(label: String, summary: AnalyticsSummary) {
    if (summary.races == 0) {
        Text("$label：まだ確定データなし", style = MaterialTheme.typography.bodySmall)
        return
    }
    Text(
        "$label：${summary.hits}/${summary.races}的中　回収率 ${String.format(Locale.US, "%.1f", summary.roi)}%　損益 ${focusSignedMoney(summary.profit)}",
        style = MaterialTheme.typography.bodySmall,
        fontWeight = FontWeight.SemiBold
    )
}

private fun focusMoney(value: Int): String = String.format(Locale.JAPAN, "%,d円", value)
private fun focusSignedMoney(value: Int): String = if (value >= 0) "+${focusMoney(value)}" else "-${focusMoney(-value)}"
