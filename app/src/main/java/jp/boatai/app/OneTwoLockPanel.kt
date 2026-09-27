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
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import java.util.Locale

@Composable
fun OneTwoLockCandidateList(ui: BoatUiState, vm: BoatViewModel) {
    val candidates = ui.races.mapNotNull { race ->
        val selection = OneTwoLockStrategy.selection(race) ?: return@mapNotNull null
        if (!selection.eligible) null else race to selection
    }.sortedWith(
        compareByDescending<Pair<RaceData, OneTwoLockSelection>> { it.second.pairProbability }
            .thenBy { it.first.closedAt }
    )

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
    ) {
        Column(Modifier.padding(14.dp)) {
            Text("1→2鉄板候補", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text(
                "Model Aで1→2の推定確率が90%以上のレースだけ表示。3着は確率上位3艇、3点均等買いで全3点が3.1倍以上のときだけ購入条件OKにします。",
                style = MaterialTheme.typography.bodySmall
            )
            Spacer(Modifier.height(6.dp))
            if (ui.oneTwoStats.settledCandidates > 0) {
                Text(
                    "導入後の実測1→2：${ui.oneTwoStats.pairHits}/${ui.oneTwoStats.settledCandidates}R（${oneTwoPercent(ui.oneTwoStats.pairHitRate)}）",
                    fontWeight = FontWeight.SemiBold
                )
                if (ui.oneTwoStats.qualifiedSettled > 0) {
                    Text(
                        "オッズ条件通過の仮想3点：${oneTwoMoney(ui.oneTwoStats.simulatedStake)} → ${oneTwoMoney(ui.oneTwoStats.simulatedPayout)} / 回収率 ${oneTwoPercent(ui.oneTwoStats.simulatedRoi)}",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            } else {
                Text("実測データはこの機能の導入後から蓄積します。90%は現時点ではModel Aの推定値です。", style = MaterialTheme.typography.bodySmall)
            }
        }
    }

    if (ui.oneTwoLoading && candidates.isEmpty()) {
        Card(modifier = Modifier.fillMaxWidth()) {
            Row(
                Modifier.fillMaxWidth().padding(16.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                CircularProgressIndicator()
                Text("1→2候補を判定中…")
            }
        }
    }

    if (!ui.oneTwoLoading && candidates.isEmpty()) {
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("本日該当なし", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                Text("推定1→2確率90%以上に届くレースはありません。条件を下げて無理に買うことはしません。", style = MaterialTheme.typography.bodySmall)
            }
        }
    }

    candidates.forEach { (race, selection) ->
        val quote = ui.oneTwoQuotes[race.id] ?: OneTwoLockQuote(selection)
        OneTwoLockRaceCard(
            race = race,
            quote = quote,
            pendingPurchaseExists = ui.pendingPurchase != null,
            onDetail = { vm.selectRace(race) },
            onBuy = {
                if (vm.prepareOneTwoLockPurchase(race)) vm.openOfficialPurchase()
            }
        )
    }
}

@Composable
private fun OneTwoLockRaceCard(
    race: RaceData,
    quote: OneTwoLockQuote,
    pendingPurchaseExists: Boolean,
    onDetail: () -> Unit,
    onBuy: () -> Unit
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("${race.venueName} ${race.raceNumber}R", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                Text(race.closedAt, fontWeight = FontWeight.SemiBold)
            }
            Text(
                "1→2 推定 ${oneTwoPercent(quote.selection.pairProbability * 100.0)}",
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.headlineSmall
            )
            Text(
                "3着候補 ${quote.selection.thirdLanes.joinToString("・")} / 3点カバー ${oneTwoPercent(quote.selection.conditionalThirdCoverage * 100.0)}",
                style = MaterialTheme.typography.bodySmall
            )
            Text(quote.selection.combinations.joinToString(" / "), fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(6.dp))

            when {
                quote.error != null -> Text("オッズ取得失敗：${quote.error}", style = MaterialTheme.typography.bodySmall)
                !race.isPurchasable() -> Text("締切済み", style = MaterialTheme.typography.bodySmall)
                !quote.oddsComplete -> Text("公式オッズ判定中…", style = MaterialTheme.typography.bodySmall)
                else -> {
                    Text(
                        quote.selection.combinations.joinToString(" / ") { combination ->
                            "$combination @${String.format(Locale.US, "%.1f", quote.odds[combination])}倍"
                        },
                        style = MaterialTheme.typography.bodySmall
                    )
                    Text(
                        if (quote.purchaseQualified) {
                            "購入条件OK：最低 ${String.format(Locale.US, "%.1f", quote.minOdds)}倍"
                        } else {
                            "見送り：3点すべて3.1倍以上の条件を満たしません"
                        },
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            Spacer(Modifier.height(8.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = onDetail, modifier = Modifier.weight(1f)) { Text("詳細") }
                Button(
                    onClick = onBuy,
                    enabled = quote.purchaseQualified && race.isPurchasable() && !pendingPurchaseExists,
                    modifier = Modifier.weight(1f)
                ) {
                    Text(if (pendingPurchaseExists) "投票待ちあり" else "3点で投票へ")
                }
            }
        }
    }
}

private fun oneTwoMoney(value: Int): String = String.format(Locale.JAPAN, "%,d円", value)
private fun oneTwoPercent(value: Double): String = String.format(Locale.US, "%.1f%%", value)
