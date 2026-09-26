package jp.boatai.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun PurchaseDashboardScreen(ui: BoatUiState, vm: BoatViewModel) {
    val dateText = ui.date.toString()
    val todayRecords = ui.records.filter { it.date == dateText }
    val raceGroups = todayRecords
        .groupBy { Triple(it.stadiumNumber, it.raceNumber, it.date) }
        .toList()
        .sortedWith(compareBy({ it.first.first }, { it.first.second }))

    val totalStake = todayRecords.sumOf { it.stake }
    val settled = todayRecords.filter { it.settled }
    val settledStake = settled.sumOf { it.stake }
    val settledPayout = settled.sumOf { it.payout }
    val pendingStake = todayRecords.filterNot { it.settled }.sumOf { it.stake }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item { CompactDateSelector(ui, vm) }

        ui.pendingPurchase?.let { pending ->
            item { PendingPurchaseCard(pending, vm) }
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text("本日の購入", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(8.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        DashboardMetric("購入", compactMoney(totalStake), Modifier.weight(1f))
                        DashboardMetric("結果待ち", compactMoney(pendingStake), Modifier.weight(1f))
                        DashboardMetric("確定損益", signedCompactMoney(settledPayout - settledStake), Modifier.weight(1f))
                    }
                }
            }
        }

        if (ui.pendingPurchase == null) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
                ) {
                    Column(Modifier.padding(14.dp)) {
                        Text("一括購入", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                        Text("予想タブで「購入推奨のみ」を選ぶと、複数レースをまとめて公式投票へ送れます。", style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.height(8.dp))
                        Button(onClick = { vm.setTab(0) }, modifier = Modifier.fillMaxWidth()) {
                            Text("予想から一括購入を選ぶ")
                        }
                    }
                }
            }
        }

        item {
            Text("購入履歴", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        }

        if (raceGroups.isEmpty()) {
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Text("この日の実購入記録はまだありません。", Modifier.padding(14.dp))
                }
            }
        } else {
            items(raceGroups, key = { "${it.first.third}-${it.first.first}-${it.first.second}" }) { (key, records) ->
                val stake = records.sumOf { it.stake }
                val payout = records.sumOf { it.payout }
                val isSettled = records.all { it.settled }
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text("${Venues.name(key.first)} ${key.second}R", fontWeight = FontWeight.Bold)
                            Text(if (isSettled) signedCompactMoney(payout - stake) else "結果待ち", fontWeight = FontWeight.SemiBold)
                        }
                        Text(records.joinToString(" / ") { "${it.combination} ${compactMoney(it.stake)}" }, style = MaterialTheme.typography.bodySmall)
                        if (isSettled) {
                            Text("購入 ${compactMoney(stake)} / 払戻 ${compactMoney(payout)}", style = MaterialTheme.typography.bodySmall)
                        } else {
                            Text("購入 ${compactMoney(stake)}", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun CompactResultsScreen(ui: BoatUiState, vm: BoatViewModel) {
    val results = ui.races.filter { it.hasResult }.sortedWith(compareBy<RaceData> { it.stadiumNumber }.thenBy { it.raceNumber })
    val predictionByRace = ui.predictionHistory.associateBy { it.id } + ui.modelARecentVirtualRecords.associateBy { it.id }
    val venues = results.groupBy { it.stadiumNumber }.toSortedMap()
    val expanded = remember { mutableStateMapOf<Int, Boolean>() }
    val captured = results.count { predictionByRace[it.id] != null }
    val hits = results.count { predictionByRace[it.id]?.hit == true }
    val boughtRaces = results.count { race ->
        ui.records.any { it.date == race.date && it.stadiumNumber == race.stadiumNumber && it.raceNumber == race.raceNumber }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        item { CompactDateSelector(ui, vm) }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DashboardMetric("確定", "${results.size}R", Modifier.weight(1f))
                DashboardMetric("AI予想", "$captured R", Modifier.weight(1f))
                DashboardMetric("的中", "$hits R", Modifier.weight(1f))
                DashboardMetric("実購入", "$boughtRaces R", Modifier.weight(1f))
            }
        }

        if (results.isEmpty() && !ui.loading) {
            item { Card { Text("この日はまだ確定結果がありません。", Modifier.padding(14.dp)) } }
        }

        venues.forEach { (stadium, stadiumRaces) ->
            item(key = "venue-$stadium") {
                val isExpanded = expanded[stadium] == true
                val venueHits = stadiumRaces.count { predictionByRace[it.id]?.hit == true }
                Card(
                    onClick = { expanded[stadium] = !isExpanded },
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(Modifier.padding(12.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Column {
                                Text(Venues.name(stadium), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                                Text("${stadiumRaces.size}レース確定 / 的中 $venueHits", style = MaterialTheme.typography.bodySmall)
                            }
                            Text(if (isExpanded) "閉じる ▲" else "詳細 ▼", fontWeight = FontWeight.SemiBold)
                        }

                        if (isExpanded) {
                            Spacer(Modifier.height(6.dp))
                            stadiumRaces.forEachIndexed { index, race ->
                                val prediction = predictionByRace[race.id]
                                val purchases = ui.records.filter { it.date == race.date && it.stadiumNumber == race.stadiumNumber && it.raceNumber == race.raceNumber }
                                val stake = purchases.sumOf { it.stake }
                                val payout = purchases.sumOf { it.payout }
                                Card(onClick = { vm.selectRace(race) }, modifier = Modifier.fillMaxWidth()) {
                                    Column(Modifier.padding(horizontal = 10.dp, vertical = 8.dp)) {
                                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                            Text("${race.raceNumber}R  ${race.result?.trifectaCombination ?: "-"}", fontWeight = FontWeight.Bold)
                                            Text(race.result?.trifectaPayout?.let(::compactMoney) ?: "-", fontWeight = FontWeight.SemiBold)
                                        }
                                        Text(
                                            when {
                                                prediction == null -> "事前予想：記録なし"
                                                prediction.hit -> "✓ 的中  ${prediction.combinations.joinToString(" / ")}"
                                                !prediction.recommended && prediction.combinations.isEmpty() -> "AI見送り：${prediction.recommendationReason ?: prediction.autoSkipReason ?: "購入条件を満たさず"}"
                                                else -> "予想  ${prediction.combinations.joinToString(" / ")}"
                                            },
                                            maxLines = 1,
                                            overflow = TextOverflow.Ellipsis,
                                            style = MaterialTheme.typography.bodySmall
                                        )
                                        if (prediction?.strategyId == ModelARecentVirtualRepository.STRATEGY_ID) {
                                            Text("Model A仮想 ${compactMoney(prediction.simulatedStake)} → ${compactMoney(prediction.simulatedPayout)} / ${signedCompactMoney(prediction.simulatedProfit)}", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
                                        }
                                        prediction?.liveOddsFetchedAt?.let { fetchedAt ->
                                            val fetchedTime = java.time.Instant.ofEpochMilli(fetchedAt)
                                                .atZone(ZoneId.of("Asia/Tokyo"))
                                                .format(DateTimeFormatter.ofPattern("HH:mm:ss"))
                                            val source = prediction.liveOddsSource ?: "取得元不明"
                                            val countText = if (prediction.liveOddsCount > 0) " / ${prediction.liveOddsCount}点" else ""
                                            Text("ライブ判定 $fetchedTime / $source$countText", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
                                            if (prediction.livePickOdds.size == prediction.combinations.size && prediction.livePickOdds.isNotEmpty()) {
                                                Text(
                                                    prediction.combinations.zip(prediction.livePickOdds).joinToString(" / ") { (combination, odds) ->
                                                        "$combination @${String.format(Locale.US, "%.1f", odds)}倍"
                                                    },
                                                    style = MaterialTheme.typography.labelSmall,
                                                    maxLines = 2,
                                                    overflow = TextOverflow.Ellipsis
                                                )
                                            }
                                        }
                                        if (purchases.isNotEmpty()) {
                                            Text("実購入 ${compactMoney(stake)} / 払戻 ${compactMoney(payout)} / ${signedCompactMoney(payout - stake)}", style = MaterialTheme.typography.labelSmall)
                                        }
                                    }
                                }
                                if (index < stadiumRaces.lastIndex) Spacer(Modifier.height(5.dp))
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun CompactProfitScreen(ui: BoatUiState, vm: BoatViewModel) {
    var period by remember { mutableIntStateOf(0) }
    var showAiDetails by remember { mutableStateOf(false) }

    val dateText = ui.date.toString()
    val weekStart = ui.date.minusDays(6).toString()
    val monthPrefix = String.format(Locale.US, "%04d-%02d", ui.date.year, ui.date.monthValue)

    val settledPredictions = ui.predictionHistory.filter { it.settled && it.evaluationEligible }
    val retrospectivePredictions = ui.modelARecentVirtualRecords.filter { it.settled && it.evaluationEligible }
    val selectedRetrospective = when (period) {
        0 -> retrospectivePredictions.filter { it.date == dateText }
        1 -> retrospectivePredictions.filter { it.date >= weekStart && it.date <= dateText }
        2 -> retrospectivePredictions.filter { it.date.startsWith(monthPrefix) }
        else -> retrospectivePredictions
    }
    val selectedPredictions = when (period) {
        0 -> settledPredictions.filter { it.date == dateText }
        1 -> settledPredictions.filter { it.date >= weekStart && it.date <= dateText }
        2 -> settledPredictions.filter { it.date.startsWith(monthPrefix) }
        else -> settledPredictions
    }
    val selectedActual = when (period) {
        0 -> ui.records.filter { it.date == dateText }
        1 -> ui.records.filter { it.date >= weekStart && it.date <= dateText }
        2 -> ui.records.filter { it.date.startsWith(monthPrefix) }
        else -> ui.records
    }

    val recommended = ProfitAnalytics.summarize(selectedPredictions.filter { it.recommended })
    val all = ProfitAnalytics.summarize(selectedPredictions)
    val retrospective = ProfitAnalytics.summarize(selectedRetrospective)
    val actualSettled = selectedActual.filter { it.settled }
    val actualStake = actualSettled.sumOf { it.stake }
    val actualPayout = actualSettled.sumOf { it.payout }
    val actualRoi = if (actualStake > 0) actualPayout * 100.0 / actualStake else 0.0
    val pendingStake = selectedActual.filterNot { it.settled }.sumOf { it.stake }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item { CompactDateSelector(ui, vm) }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Row(Modifier.fillMaxWidth().padding(4.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
                    listOf("今日", "7日", "月", "全期間").forEachIndexed { index, label ->
                        TextButton(onClick = { period = index }) {
                            Text(label, fontWeight = if (period == index) FontWeight.Bold else FontWeight.Normal)
                        }
                    }
                }
            }
        }

        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
            ) {
                Column(Modifier.padding(14.dp)) {
                    Text("実購入", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text(signedCompactMoney(actualPayout - actualStake), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineMedium)
                    Text("購入 ${compactMoney(actualStake)} / 払戻 ${compactMoney(actualPayout)} / 回収率 ${compactPercent(actualRoi)}")
                    if (pendingStake > 0) Text("結果待ち ${compactMoney(pendingStake)}", style = MaterialTheme.typography.bodySmall)
                }
            }
        }

        item {
            Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Column(Modifier.padding(14.dp)) {
                    Text("Model A 過去仮想損益（確定払戻）", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text(signedCompactMoney(retrospective.profit), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineMedium)
                    Text("${retrospective.hits}/${retrospective.races}的中 / 購入 ${compactMoney(retrospective.stake)} / 払戻 ${compactMoney(retrospective.payout)} / 回収率 ${compactPercent(retrospective.roi)}")
                    Text("対象日前日までの履歴だけで市場非入力Model Aを再現。4〜8点・1R 1,000〜3,000円（100円単位）の配分は終了後オッズを使う研究用仮想配分です。締切前に同じ価格で買えたことを示すROIではなく、自動BUYには使用しません。", style = MaterialTheme.typography.bodySmall)
                    ui.modelARecentVirtualThroughDate?.let { through ->
                        Text("期間: ${ui.modelARecentVirtualWindowStart ?: "-"} 〜 $through / 直近30日", style = MaterialTheme.typography.labelSmall)
                    }
                    ui.modelARecentVirtualError?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.error) }
                }
            }
        }

        ui.modelARecentVirtualSummary?.let { summary ->
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp)) {
                        Text("Model A 点数別30日診断", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                        Text("全体 ${summary.hits}/${summary.races}的中 / 回収率 ${compactPercent(summary.roi)} / ${signedCompactMoney(summary.profit)}", fontWeight = FontWeight.SemiBold)
                        Text("平均 ${String.format(Locale.US, "%.2f", summary.averagePoints)}点 / ${compactMoney(summary.averageStake.toInt())}", style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.height(6.dp))
                        summary.pointBreakdown.forEach { row ->
                            Text("${row.points}点　${row.hits}/${row.races}的中（${compactPercent(row.hitRate)}）　ROI ${compactPercent(row.roi)}　${signedCompactMoney(row.profit)}", style = MaterialTheme.typography.bodySmall)
                        }
                        Spacer(Modifier.height(4.dp))
                        Text("点数別数値は診断用です。結果を見て点数を後付け選択する用途には使いません。", style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }

        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AnalyticsMiniCard("AI購入推奨", recommended, Modifier.weight(1f))
                AnalyticsMiniCard("全予想", all, Modifier.weight(1f))
            }
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("予想保存状況", fontWeight = FontWeight.Bold)
                    val captured = ui.predictionHistory.count { it.date == dateText && it.evaluationEligible }
                    val results = ui.races.count { it.date.take(10) == dateText && it.hasResult }
                    Text("締切前保存 $captured / 当日結果 $results", fontWeight = FontWeight.SemiBold)
                    Text("学習済み ${ui.learnedRaceCount}レース", style = MaterialTheme.typography.bodySmall)
                }
            }
        }

        item {
            OutlinedButton(onClick = { showAiDetails = !showAiDetails }, modifier = Modifier.fillMaxWidth()) {
                Text(if (showAiDetails) "AI分析を閉じる ▲" else "AI分析・検証を見る ▼")
            }
        }
        if (showAiDetails) {
            item { HistoricalBacktestCard() }
            item { PerformanceFeedbackCard(ui) }
            item { AdvancedAnalyticsCard(ui) }
        }

    }
}

@Composable
private fun CompactDateSelector(ui: BoatUiState, vm: BoatViewModel) {
    val formatter = DateTimeFormatter.ofPattern("M月d日(E)", Locale.JAPANESE)
    val today = LocalDate.now(ZoneId.of("Asia/Tokyo"))
    val earliest = today.minusDays(ModelARecentVirtualRepository.WINDOW_DAYS.toLong())
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 5.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            TextButton(onClick = vm::previousDay, enabled = ui.date.isAfter(earliest)) { Text("‹ 前日") }
            Text(ui.date.format(formatter), fontWeight = FontWeight.Bold)
            TextButton(onClick = vm::nextDay, enabled = ui.date.isBefore(today)) { Text("翌日 ›") }
        }
    }
}

@Composable
private fun DashboardMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier) {
        Column(Modifier.fillMaxWidth().padding(vertical = 10.dp, horizontal = 6.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(label, style = MaterialTheme.typography.labelSmall)
            Text(value, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun AnalyticsMiniCard(title: String, summary: AnalyticsSummary, modifier: Modifier = Modifier) {
    Card(modifier = modifier) {
        Column(Modifier.padding(12.dp)) {
            Text(title, fontWeight = FontWeight.Bold)
            Text("${summary.hits}/${summary.races} 的中", style = MaterialTheme.typography.bodySmall)
            Text("回収 ${compactPercent(summary.roi)}", fontWeight = FontWeight.Bold)
            Text(signedCompactMoney(summary.profit), style = MaterialTheme.typography.bodySmall)
        }
    }
}

private fun compactMoney(value: Int): String = String.format(Locale.JAPAN, "%,d円", value)
private fun signedCompactMoney(value: Int): String = if (value >= 0) "+${compactMoney(value)}" else "-${compactMoney(-value)}"
private fun compactPercent(value: Double): String = String.format(Locale.US, "%.1f%%", value)
