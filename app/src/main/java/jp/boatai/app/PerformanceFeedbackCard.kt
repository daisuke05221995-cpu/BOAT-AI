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
    val eligible = ui.predictionHistory.filter { it.settled && it.evaluationEligible }
    val recommended = ProfitAnalytics.summarize(eligible.filter { it.recommended })
    val skipped = ProfitAnalytics.summarize(eligible.filterNot { it.recommended })

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text(
                "AI検証・購入判定学習",
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleMedium
            )
            Text(
                "結果が出る前に保存した予想だけを使い、購入推奨と見送りの判定を検証します。",
                style = MaterialTheme.typography.bodySmall
            )
            Spacer(Modifier.height(8.dp))

            if (overall.races == 0) {
                Text("検証対象はまだ0レースです。事前予想から自動で蓄積します。")
            } else {
                Text(
                    "検証 ${overall.races}レース / 的中 ${overall.hits} / 的中率 ${performancePercent(overall.hitRate)}",
                    fontWeight = FontWeight.SemiBold
                )
                Text(
                    "仮想購入 ${performanceMoney(overall.stake)} / 払戻 ${performanceMoney(overall.payout)} / 損益 ${performanceSignedMoney(overall.profit)}"
                )

                Spacer(Modifier.height(8.dp))
                HorizontalDivider()
                Spacer(Modifier.height(8.dp))
                Text("購入判定別", fontWeight = FontWeight.Bold)
                Text(
                    "購入推奨：${recommended.hits}/${recommended.races}的中　的中率 ${performancePercent(recommended.hitRate)}　回収率 ${performancePercent(recommended.roi)}",
                    style = MaterialTheme.typography.bodySmall
                )
                Text(
                    "見送り：${skipped.hits}/${skipped.races}的中　的中率 ${performancePercent(skipped.hitRate)}　回収率 ${performancePercent(skipped.roi)}",
                    style = MaterialTheme.typography.bodySmall
                )

                Spacer(Modifier.height(8.dp))
                Text("1着軸別", fontWeight = FontWeight.Bold)
                (1..6).forEach { lane ->
                    profile.byFirstLane[lane]?.takeIf { it.races > 0 }?.let { stats ->
                        Text(
                            "${lane}号艇軸：${stats.hits}/${stats.races}的中　回収率 ${performancePercent(stats.roi)}",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }

                Spacer(Modifier.height(8.dp))
                Text("弱い条件", fontWeight = FontWeight.Bold)
                if (weak.isEmpty()) {
                    Text("見送り判定を強めるほど悪い条件はまだありません。", style = MaterialTheme.typography.bodySmall)
                } else {
                    weak.forEach { condition ->
                        Text(
                            "${condition.label}：${condition.stats.races}件 / 回収率 ${performancePercent(condition.stats.roi)} / " +
                                if (condition.autoSkip) "見送り対象" else "内部評価を下方補正",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                }
            }

            Spacer(Modifier.height(8.dp))
            Text(
                "内部では細かな数値を学習に使いますが、画面上の最終判断は「購入推奨 / 見送り」の2択です。十分な実績がたまった弱い条件は自動で見送り側へ寄せます。",
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

private fun performancePercent(value: Double): String = String.format(Locale.US, "%.1f%%", value)
private fun performanceMoney(value: Int): String = String.format(Locale.JAPAN, "%,d円", value)
private fun performanceSignedMoney(value: Int): String =
    if (value >= 0) "+${performanceMoney(value)}" else "-${performanceMoney(-value)}"
