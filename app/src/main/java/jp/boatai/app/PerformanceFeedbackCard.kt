package jp.boatai.app

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.util.Locale

@Composable
fun PerformanceFeedbackCard(ui: BoatUiState) {
    val profile = ui.performance
    val overall = profile.overall
    val weak = profile.weakConditions()
    val skippedCount = ui.predictionHistory.count { it.evaluationEligible && it.autoSkipped }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text(
                "AI検証・自動補正",
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleMedium
            )
            Text(
                "結果が出る前に保存できた予想だけで検証します。過去日を後から開いた予想は補正に使いません。",
                style = MaterialTheme.typography.bodySmall
            )
            Spacer(Modifier.height(8.dp))

            if (overall.races == 0) {
                Text("検証対象はまだ0レースです。v0.10.0以降の事前予想から自動で蓄積します。")
            } else {
                Text(
                    "検証 ${overall.races}レース / 的中 ${overall.hits} / 的中率 ${percent(overall.hitRate)}",
                    fontWeight = FontWeight.SemiBold
                )
                Text(
                    "仮想購入 ${money(overall.stake)} / 払戻 ${money(overall.payout)} / 損益 ${signedMoney(overall.profit)}"
                )
                Text(
                    "回収率 ${percent(overall.roi)} / 自動見送り判定の記録 ${skippedCount}レース",
                    fontWeight = FontWeight.Bold
                )

                Spacer(Modifier.height(8.dp))
                HorizontalDivider()
                Spacer(Modifier.height(8.dp))
                Text("AIランク別", fontWeight = FontWeight.Bold)
                listOf("S", "A", "B", "C", "D").forEach { rank ->
                    profile.byRank[rank]?.takeIf { it.races > 0 }?.let { stats ->
                        Text(
                            "$rank：${stats.hits}/${stats.races}的中　的中率 ${percent(stats.hitRate)}　回収率 ${percent(stats.roi)}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }

                Spacer(Modifier.height(8.dp))
                Text("1着軸別", fontWeight = FontWeight.Bold)
                (1..6).forEach { lane ->
                    profile.byFirstLane[lane]?.takeIf { it.races > 0 }?.let { stats ->
                        Text(
                            "${lane}号艇軸：${stats.hits}/${stats.races}的中　回収率 ${percent(stats.roi)}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }

                Spacer(Modifier.height(8.dp))
                Text("弱い条件", fontWeight = FontWeight.Bold)
                if (weak.isEmpty()) {
                    Text(
                        "補正対象になるほど悪い条件はまだありません。",
                        style = MaterialTheme.typography.bodySmall
                    )
                } else {
                    weak.forEach { condition ->
                        Text(
                            "${condition.label}：${condition.stats.races}件 / 回収率 ${percent(condition.stats.roi)} / " +
                                if (condition.autoSkip) "一括選択から自動見送り" else "期待度 ${condition.penalty}pt補正",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }

            Spacer(Modifier.height(8.dp))
            Text(
                "補正開始の最低件数：会場24件、AIランク30件、1着軸30件、会場×ランク×1着軸16件。期待度は最大-12pt。十分な件数で回収率55%未満かつ的中率8%未満の条件は一括選択から自動見送りにします。個別購入は手動で可能です。",
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

private fun percent(value: Double): String = String.format(Locale.US, "%.1f%%", value)
private fun money(value: Int): String = String.format(Locale.JAPAN, "%,d円", value)
private fun signedMoney(value: Int): String = if (value >= 0) "+${money(value)}" else "-${money(-value)}"
