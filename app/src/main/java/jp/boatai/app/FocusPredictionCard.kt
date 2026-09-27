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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.util.Locale

@Composable
fun FocusPredictionCard(
    race: RaceData,
    raceBudget: Int,
    purchased: Boolean,
    onPurchase: (FocusMode) -> Unit
) {
    var mode by remember(race.id) { mutableStateOf(FocusMode.FOUR) }
    val selection = remember(race.id, mode) { FocusPredictionStrategy.selection(race, mode) }
    val picks = remember(race.id, mode, raceBudget) {
        FocusPredictionStrategy.purchasePicks(race, mode, raceBudget)
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("フォーカス予想", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text(
                "Model Aの120通り確率を、競輪アプリのような『軸＋相手広げ』の形へまとめた別戦略です。従来のAI購入判断は変更しません。",
                style = MaterialTheme.typography.bodySmall
            )
            Spacer(Modifier.height(6.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                FocusMode.entries.forEach { option ->
                    TextButton(
                        onClick = { mode = option },
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
                Text(
                    pattern.combinations.joinToString(" / "),
                    style = MaterialTheme.typography.bodySmall
                )
            }

            Spacer(Modifier.height(8.dp))
            Text(
                "実買い目 ${selection.combinations.size}点 / Model A合計確率 ${String.format(Locale.US, "%.1f", selection.coverageProbability * 100.0)}%",
                fontWeight = FontWeight.Bold
            )
            Text(
                "最低 ${money(selection.minimumStake)}。現在予算 ${money(raceBudget)}" +
                    if (picks.isEmpty()) "（予算不足または予想未確定）" else " / 配分 ${money(picks.sumOf { it.recommendedStake })}",
                style = MaterialTheme.typography.bodySmall
            )
            Text(
                "このモードは的中範囲を広げる検証枠です。フォーカス4択・5択の成績は既存value-v1と分けて評価します。",
                style = MaterialTheme.typography.bodySmall
            )
            Spacer(Modifier.height(8.dp))
            Button(
                onClick = { onPurchase(mode) },
                enabled = race.isPurchasable() && picks.isNotEmpty() && !purchased,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(if (purchased) "このレースは購入済み" else "${mode.label}を公式投票へ")
            }
        }
    }
}
