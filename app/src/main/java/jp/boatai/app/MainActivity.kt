package jp.boatai.app

import android.app.Activity
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AccountBalanceWallet
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.OpenInBrowser
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import java.time.format.DateTimeFormatter
import java.util.Locale

class MainActivity : ComponentActivity() {
    private val vm: BoatViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme {
                BoatAiApp(vm)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        vm.resumePendingInstall(this)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BoatAiApp(vm: BoatViewModel) {
    val ui by vm.ui.collectAsStateWithLifecycle()
    val selected = ui.selectedRace
    val selectedVenue = ui.selectedVenue

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        if (selected != null) {
                            "${selected.venueName} ${selected.raceNumber}R"
                        } else if (selectedVenue != null) {
                            "${Venues.name(selectedVenue)} 開催レース"
                        } else {
                            when (ui.tab) {
                                0 -> "予想  v${BuildConfig.VERSION_NAME}"
                                1 -> "結果"
                                else -> "損益"
                            }
                        }
                    )
                },
                navigationIcon = {
                    if (selected != null || selectedVenue != null) {
                        IconButton(onClick = if (selected != null) vm::closeRace else vm::closeVenue) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "戻る")
                        }
                    }
                },
                actions = {
                    if (selected == null && selectedVenue == null && ui.tab in 0..1) {
                        IconButton(onClick = vm::refresh) {
                            Icon(Icons.Default.Refresh, contentDescription = "更新")
                        }
                    }
                }
            )
        },
        bottomBar = {
            if (selected == null && selectedVenue == null) {
                NavigationBar {
                    NavigationBarItem(
                        selected = ui.tab == 0,
                        onClick = { vm.setTab(0) },
                        icon = { Icon(Icons.Default.Home, contentDescription = null) },
                        label = { Text("予想") }
                    )
                    NavigationBarItem(
                        selected = ui.tab == 1,
                        onClick = { vm.setTab(1) },
                        icon = { Icon(Icons.Default.CheckCircle, contentDescription = null) },
                        label = { Text("結果") }
                    )
                    NavigationBarItem(
                        selected = ui.tab == 2,
                        onClick = { vm.setTab(2) },
                        icon = { Icon(Icons.Default.AccountBalanceWallet, contentDescription = null) },
                        label = { Text("損益") }
                    )
                }
            }
        }
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
        ) {
            when {
                selected != null -> RaceDetailScreen(ui, vm)
                selectedVenue != null -> VenueDetailScreen(ui, vm, selectedVenue)
                ui.tab == 0 -> PredictionScreen(ui, vm)
                ui.tab == 1 -> ResultsScreen(ui, vm)
                else -> ProfitScreen(ui, vm)
            }
        }
    }
}

@Composable
private fun PredictionScreen(ui: BoatUiState, vm: BoatViewModel) {
    var sortMode by remember { mutableIntStateOf(0) }
    val venues = (1..24).map { stadium ->
        stadium to ui.races.filter { it.stadiumNumber == stadium }
    }.let { list ->
        when (sortMode) {
            1 -> list.sortedBy { (_, races) -> races.filter { it.isPurchasable() }.minOfOrNull { closeTime(it.closedAt) } ?: "99:99" }
            2 -> list.sortedByDescending { (_, races) -> races.maxOfOrNull(PredictionEngine::confidence) ?: 0 }
            else -> list
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            AppUpdateCard(ui.update, vm)
        }

        item {
            DateSelectorCard(ui, vm)
        }

        item { PredictionModeBar(sortMode, { sortMode = it }) }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(10.dp)) {
                    Text("AI期待度から一括選択", fontWeight = FontWeight.Bold)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(onClick = { vm.selectConfidenceAtLeast(80) }) { Text("80以上") }
                        OutlinedButton(onClick = { vm.selectConfidenceAtLeast(70) }) { Text("70以上") }
                        OutlinedButton(onClick = vm::clearBulkSelection) { Text("解除") }
                    }
                }
            }
        }

        if (ui.loading && ui.races.isEmpty()) {
            item {
                Box(
                    Modifier.fillMaxWidth().padding(32.dp),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
        }

        ui.error?.let { message ->
            item {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    ),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(message, modifier = Modifier.padding(12.dp))
                }
            }
        }

        items(venues.chunked(3), key = { row -> row.joinToString { it.first.toString() } }) { row ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                row.forEach { (stadium, races) ->
                    VenueTile(stadium, races, Modifier.weight(1f)) { vm.selectVenue(stadium) }
                }
                repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }

        if (ui.selectedForBulk.isNotEmpty()) item { BulkPurchaseCard(ui, vm) }

        item {
            Text(
                "一括購入・個別購入は現在「購入記録」の登録です。公式投票サイトへの自動送信はまだ行わず、登録した金額を実購入として損益に集計します。",
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(4.dp)
            )
        }
    }
}

@Composable
private fun PredictionModeBar(selected: Int, onSelect: (Int) -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(4.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
            listOf("開催一覧", "締切順", "AI期待度順").forEachIndexed { index, label ->
                TextButton(onClick = { onSelect(index) }) {
                    Text(label, fontWeight = if (selected == index) FontWeight.Bold else FontWeight.Normal)
                }
            }
        }
    }
}

@Composable
private fun VenueTile(
    stadium: Int,
    races: List<RaceData>,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    val open = races.filter { it.isPurchasable() }
    val next = open.minByOrNull { closeTime(it.closedAt) }
    val best = open.maxOfOrNull(PredictionEngine::confidence)
    val first = races.firstOrNull()
    Card(
        onClick = onClick,
        enabled = races.isNotEmpty(),
        modifier = modifier.heightIn(min = 104.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (races.isEmpty()) MaterialTheme.colorScheme.surfaceVariant
            else MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Column(Modifier.padding(9.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(Venues.name(stadium), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            if (first == null) {
                Text("開催なし", style = MaterialTheme.typography.bodySmall)
                Text("ーー")
            } else {
                Text(
                    "${gradeLabel(first.gradeNumber)}　${first.dayNumber?.let { "${it}日目" } ?: "開催中"}",
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1
                )
                Text(next?.let { "${it.raceNumber}R  ${closeTime(it.closedAt)}" } ?: "本日終了", fontWeight = FontWeight.SemiBold)
                if (best != null) Text("AI $best  ${rankLabel(best)}", style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

@Composable
private fun VenueDetailScreen(ui: BoatUiState, vm: BoatViewModel, stadium: Int) {
    val races = ui.races.filter { it.stadiumNumber == stadium }.sortedBy { it.raceNumber }
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("${Venues.name(stadium)}の一括購入", fontWeight = FontWeight.Bold)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(onClick = { vm.selectVenuePurchasable(stadium) }) { Text("全レース") }
                        OutlinedButton(onClick = { vm.selectVenueTop(stadium) }) { Text("AI上位3件") }
                    }
                }
            }
        }
        item { BulkPurchaseCard(ui, vm) }
        item {
            VenuePredictionCard(
                races = races,
                ui = ui,
                onToggle = vm::toggleBulkRace,
                onIndividualBuy = vm::recordRace,
                onDetail = vm::selectRace
            )
        }
    }
}

@Composable
private fun DateSelectorCard(ui: BoatUiState, vm: BoatViewModel) {
    val formatter = DateTimeFormatter.ofPattern("yyyy年M月d日(E)", Locale.JAPANESE)

    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            IconButton(onClick = vm::previousDay) {
                Icon(Icons.Default.ChevronLeft, contentDescription = "前日")
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(ui.date.format(formatter), fontWeight = FontWeight.Bold)
                Text(
                    if (ui.loading) "データ更新中…" else "全国24場 / 実データ",
                    style = MaterialTheme.typography.bodySmall
                )
            }
            IconButton(onClick = vm::nextDay) {
                Icon(Icons.Default.ChevronRight, contentDescription = "翌日")
            }
        }
    }
}

@Composable
private fun BulkPurchaseCard(ui: BoatUiState, vm: BoatViewModel) {
    val selectedRaces = ui.races.filter { it.id in ui.selectedForBulk && it.isPurchasable() }
    val selectedTickets = selectedRaces.sumOf { PredictionEngine.predict(it).size }
    val total = selectedTickets * ui.stakePerPick
    val availableCount = ui.races.count { it.isPurchasable() }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text("一括購入", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text(
                "対象をチェックしてまとめて購入記録へ登録",
                style = MaterialTheme.typography.bodySmall
            )
            Spacer(Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text("選択 ${selectedRaces.size}レース / ${selectedTickets}点")
                Text(money(total), fontWeight = FontWeight.Bold)
            }

            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedButton(onClick = vm::decreaseStake) { Text("-100") }
                Text(
                    " 1点 ${money(ui.stakePerPick)} ",
                    fontWeight = FontWeight.Bold
                )
                OutlinedButton(onClick = vm::increaseStake) { Text("+100") }
            }

            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(
                    onClick = vm::selectAllPurchasable,
                    enabled = availableCount > 0
                ) {
                    Text("全選択")
                }
                OutlinedButton(
                    onClick = vm::clearBulkSelection,
                    enabled = ui.selectedForBulk.isNotEmpty()
                ) {
                    Text("解除")
                }
            }

            Spacer(Modifier.height(8.dp))
            Button(
                onClick = vm::recordSelectedRaces,
                enabled = selectedRaces.isNotEmpty(),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("選択分を一括購入登録")
            }

            ui.actionMessage?.let {
                Spacer(Modifier.height(6.dp))
                Text(it, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun VenuePredictionCard(
    races: List<RaceData>,
    ui: BoatUiState,
    onToggle: (String) -> Unit,
    onIndividualBuy: (RaceData) -> Unit,
    onDetail: (RaceData) -> Unit
) {
    val first = races.firstOrNull() ?: return

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text(
                "${first.venueName}　${first.title}",
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleMedium
            )
            val sub = listOfNotNull(
                first.dayNumber?.let { "$it 日目" },
                first.subtitle.takeIf { it.isNotBlank() }
            ).joinToString(" / ")
            if (sub.isNotBlank()) {
                Text(sub, style = MaterialTheme.typography.bodySmall)
            }

            Spacer(Modifier.height(6.dp))
            races.sortedBy { it.raceNumber }.forEachIndexed { index, race ->
                RacePredictionRow(
                    race = race,
                    checked = race.id in ui.selectedForBulk,
                    stakePerPick = ui.stakePerPick,
                    purchasedStake = ui.records
                        .filter { it.date == race.date && it.stadiumNumber == race.stadiumNumber && it.raceNumber == race.raceNumber }
                        .sumOf { it.stake },
                    onToggle = { onToggle(race.id) },
                    onIndividualBuy = { onIndividualBuy(race) },
                    onDetail = { onDetail(race) }
                )
                if (index < races.lastIndex) {
                    HorizontalDivider(Modifier.padding(vertical = 6.dp))
                }
            }
        }
    }
}

@Composable
private fun RacePredictionRow(
    race: RaceData,
    checked: Boolean,
    stakePerPick: Int,
    purchasedStake: Int,
    onToggle: () -> Unit,
    onIndividualBuy: () -> Unit,
    onDetail: () -> Unit
) {
    val picks = PredictionEngine.predict(race)
    val total = picks.size * stakePerPick
    val enabled = race.isPurchasable() && picks.isNotEmpty() && purchasedStake == 0

    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.Top
    ) {
        Checkbox(
            checked = checked,
            onCheckedChange = { onToggle() },
            enabled = enabled
        )
        Column(modifier = Modifier.weight(1f)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    "${race.raceNumber}R　締切 ${closeTime(race.closedAt)}",
                    fontWeight = FontWeight.Bold
                )
                Text(
                    when {
                        race.hasResult -> "結果確定"
                        race.isPurchasable() -> money(total)
                        race.date.take(10) < java.time.LocalDate.now(java.time.ZoneId.of("Asia/Tokyo")).toString() -> "終了・結果取得待ち"
                        !race.isDataComplete -> "情報取得待ち"
                        else -> "締切済み"
                    },
                    style = MaterialTheme.typography.bodySmall
                )
            }
            Text(
                if (picks.isEmpty()) "予想データ不足"
                else picks.joinToString(" / ") { it.combination },
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                style = MaterialTheme.typography.bodyMedium
            )
            if (picks.isNotEmpty()) {
                val confidence = PredictionEngine.confidence(race)
                Text(
                    "期待度 $confidence / ${rankLabel(confidence)}ランク",
                    style = MaterialTheme.typography.bodySmall,
                    fontWeight = FontWeight.SemiBold
                )
            }
            if (purchasedStake > 0) {
                Text(
                    "✓ 購入済み　${money(purchasedStake)}",
                    color = MaterialTheme.colorScheme.primary,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Bold
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                OutlinedButton(
                    onClick = onIndividualBuy,
                    enabled = enabled
                ) {
                    Text(if (purchasedStake > 0) "購入済み" else if (race.isPurchasable()) "個別購入" else "購入不可")
                }
                TextButton(onClick = onDetail) {
                    Text("詳細")
                }
            }
        }
    }
}

@Composable
private fun ResultsScreen(ui: BoatUiState, vm: BoatViewModel) {
    val results = ui.races
        .filter { it.hasResult }
        .sortedWith(compareBy<RaceData> { it.stadiumNumber }.thenBy { it.raceNumber })
    val predictionByRace = ui.predictionHistory.associateBy { it.id }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            DateSelectorCard(ui, vm)
        }

        if (ui.loading && results.isEmpty()) {
            item {
                Box(
                    Modifier.fillMaxWidth().padding(32.dp),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator()
                }
            }
        }

        ui.error?.let { message ->
            item {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    ),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(message, modifier = Modifier.padding(12.dp))
                }
            }
        }

        if (!ui.loading && results.isEmpty()) {
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Text(
                        "この日はまだ確定結果がありません。",
                        modifier = Modifier.padding(14.dp)
                    )
                }
            }
        }

        items(results, key = { it.id }) { race ->
            val record = predictionByRace[race.id]
            val purchases = ui.records.filter {
                it.date == race.date &&
                    it.stadiumNumber == race.stadiumNumber &&
                    it.raceNumber == race.raceNumber
            }
            ResultCard(race, record, purchases)
        }
    }
}

@Composable
private fun ResultCard(
    race: RaceData,
    prediction: PredictionRecord?,
    purchases: List<BetRecord>
) {
    val result = race.result
    val actualStake = purchases.sumOf { it.stake }
    val actualPayout = purchases.sumOf { it.payout }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text(
                "${race.venueName} ${race.raceNumber}R",
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleMedium
            )
            Spacer(Modifier.height(6.dp))

            Row(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.weight(0.9f)) {
                    Text("着順", style = MaterialTheme.typography.labelMedium)
                    Text(
                        result?.trifectaCombination ?: "-",
                        fontWeight = FontWeight.Bold
                    )
                }
                Column(modifier = Modifier.weight(0.9f)) {
                    Text("払戻", style = MaterialTheme.typography.labelMedium)
                    Text(
                        result?.trifectaPayout?.let(::money) ?: "-",
                        fontWeight = FontWeight.Bold
                    )
                }
                Column(modifier = Modifier.weight(1.8f)) {
                    Text("事前予想", style = MaterialTheme.typography.labelMedium)
                    Text(
                        prediction?.combinations?.joinToString(" / ") ?: "記録なし",
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }

            prediction?.let {
                Spacer(Modifier.height(6.dp))
                Text(
                    if (it.hit) {
                        "予想的中　想定払戻 ${money(it.simulatedPayout)}"
                    } else {
                        "予想ハズレ"
                    },
                    fontWeight = FontWeight.SemiBold
                )
                PredictionEngine.missReason(race, it.combinations)?.let { reason ->
                    Text(
                        "敗因分析：$reason",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }
            }

            if (purchases.isNotEmpty()) {
                Text(
                    "実購入 ${money(actualStake)} / 払戻 ${money(actualPayout)} / 収支 ${signedMoney(actualPayout - actualStake)}",
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
    }
}

@Composable
private fun ProfitScreen(ui: BoatUiState, vm: BoatViewModel) {
    val settledPredictions = ui.predictionHistory.filter { it.settled }
    val predictionHits = settledPredictions.count { it.hit }
    val predictionStake = settledPredictions.sumOf { it.simulatedStake }
    val predictionPayout = settledPredictions.sumOf { it.simulatedPayout }
    val predictionProfit = predictionPayout - predictionStake
    val predictionHitRate = if (settledPredictions.isNotEmpty()) {
        predictionHits * 100.0 / settledPredictions.size
    } else {
        0.0
    }
    val predictionRoi = if (predictionStake > 0) {
        predictionPayout * 100.0 / predictionStake
    } else {
        0.0
    }

    val actualStake = ui.records.sumOf { it.stake }
    val actualPayout = ui.records.sumOf { it.payout }
    val actualProfit = actualPayout - actualStake
    val actualRoi = if (actualStake > 0) actualPayout * 100.0 / actualStake else 0.0
    val pendingStake = ui.records.filter { !it.settled }.sumOf { it.stake }

    val dateText = ui.date.toString()
    val dayRecords = ui.records.filter { it.date == dateText }
    val dayStake = dayRecords.sumOf { it.stake }
    val dayPayout = dayRecords.sumOf { it.payout }
    val dayPredictions = ui.predictionHistory.filter { it.date == dateText && it.settled }
    val dayPredictionHits = dayPredictions.count { it.hit }
    val dayPredictionStake = dayPredictions.sumOf { it.simulatedStake }
    val dayPredictionPayout = dayPredictions.sumOf { it.simulatedPayout }
    val dayPredictionRate = if (dayPredictions.isEmpty()) 0.0
        else dayPredictionHits * 100.0 / dayPredictions.size

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text(
                        "予想実績",
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.titleMedium
                    )
                    Text(
                        "的中 $predictionHits / ${settledPredictions.size}レース　的中率 ${String.format(Locale.US, "%.1f", predictionHitRate)}%",
                        fontWeight = FontWeight.SemiBold
                    )
                    Text("予想購入合計 ${money(predictionStake)}")
                    Text("予想払戻合計 ${money(predictionPayout)}")
                    Text(
                        "予想損益 ${signedMoney(predictionProfit)}　回収率 ${String.format(Locale.US, "%.1f", predictionRoi)}%",
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        "事前に保存した4点予想を各${money(PredictionHistoryStore.DEFAULT_SIMULATION_STAKE)}で計算",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text(
                        "実購入",
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.titleMedium
                    )
                    Text("購入合計 ${money(actualStake)}")
                    Text("払戻合計 ${money(actualPayout)}")
                    Text(
                        "損益 ${signedMoney(actualProfit)}　回収率 ${String.format(Locale.US, "%.1f", actualRoi)}%",
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        "結果待ち ${ui.records.count { !it.settled }}点 / ${money(pendingStake)}",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text(
                        "${ui.date} のAI予想成績",
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.titleMedium
                    )
                    Text("的中 $dayPredictionHits / ${dayPredictions.size}レース　${String.format(Locale.US, "%.1f", dayPredictionRate)}%")
                    Text("全予想を各${money(PredictionHistoryStore.DEFAULT_SIMULATION_STAKE)}で買った場合")
                    Text("使用 ${money(dayPredictionStake)} / 払戻 ${money(dayPredictionPayout)}")
                    Text(
                        "仮想収支 ${signedMoney(dayPredictionPayout - dayPredictionStake)}",
                        fontWeight = FontWeight.Bold
                    )
                    HorizontalDivider(Modifier.padding(vertical = 8.dp))
                    Text("実際の購入記録", fontWeight = FontWeight.SemiBold)
                    Text("${ui.date}　購入 ${money(dayStake)}")
                    Text("払戻 ${money(dayPayout)}　損益 ${signedMoney(dayPayout - dayStake)}")
                }
            }
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text("AI学習状況", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text("学習済み ${ui.learnedRaceCount}レース")
                    Text(
                        "外れたレースの1着コース傾向を会場別に補正し、次回以降の予想スコアへ反映します。",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }

        if (ui.records.isNotEmpty()) {
            item {
                OutlinedButton(
                    onClick = vm::clearRecords,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("実購入の記録を全削除")
                }
            }
        }
    }
}

@Composable
private fun AppUpdateCard(update: AppUpdateState, vm: BoatViewModel) {
    val context = LocalContext.current
    val activity = context as? Activity

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text("アプリ更新", fontWeight = FontWeight.Bold)
                    Text(
                        when {
                            update.checking -> "更新を確認中…"
                            update.updateAvailable -> "v${update.latestVersion} の更新があります"
                            update.error != null -> update.error
                            update.statusMessage != null -> update.statusMessage
                            else -> "現在 v${update.currentVersion}"
                        },
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                Spacer(Modifier.width(8.dp))
                if (update.updateAvailable) {
                    Button(
                        onClick = { activity?.let(vm::downloadAndInstallUpdate) },
                        enabled = !update.downloading && activity != null
                    ) {
                        Text(if (update.downloading) "取得中" else "更新する")
                    }
                } else {
                    OutlinedButton(
                        onClick = vm::checkForAppUpdate,
                        enabled = !update.checking && !update.downloading
                    ) {
                        Text("確認")
                    }
                }
            }

            if (update.downloading) {
                Spacer(Modifier.height(8.dp))
                val progress = update.downloadProgress
                if (progress != null) {
                    LinearProgressIndicator(
                        progress = { progress / 100f },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Text("$progress%", style = MaterialTheme.typography.bodySmall)
                } else {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                }
            }

            update.releaseNotes
                ?.takeIf { update.updateAvailable && it.isNotBlank() }
                ?.let { notes ->
                    Spacer(Modifier.height(6.dp))
                    Text(
                        notes.lineSequence().take(3).joinToString("\n"),
                        style = MaterialTheme.typography.bodySmall
                    )
                }
        }
    }
}

@Composable
private fun RaceDetailScreen(ui: BoatUiState, vm: BoatViewModel) {
    val race = ui.selectedRace ?: return
    val uriHandler = LocalUriHandler.current
    val day = race.date.replace("-", "")
    val jcd = Venues.code(race.stadiumNumber)
    val programUrl =
        "https://www.boatrace.jp/owpc/pc/race/racelist?hd=$day&jcd=$jcd&rno=${race.raceNumber}"
    val oddsUrl =
        "https://www.boatrace.jp/owpc/pc/race/odds3t?hd=$day&jcd=$jcd&rno=${race.raceNumber}"

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text(
                        race.title,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.titleMedium
                    )
                    Text("締切 ${race.closedAt}　${race.distance ?: 1800}m")
                    race.preview?.let { p ->
                        Spacer(Modifier.height(6.dp))
                        Text(
                            "直前: ${p.weather ?: "-"}　風 ${p.windSpeed ?: "-"}m/s ${p.windDirection ?: ""}　波 ${p.waveHeight ?: "-"}cm"
                        )
                        Text("気温 ${p.airTemperature.f1()}℃　水温 ${p.waterTemperature.f1()}℃")
                    }
                    race.result?.takeIf { race.hasResult }?.let { r ->
                        Spacer(Modifier.height(6.dp))
                        Text(
                            "結果 3連単 ${r.trifectaCombination} / ${r.trifectaPayout?.let { "${it}円" } ?: "-"}",
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }

        item {
            Text(
                "出走データ",
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleMedium
            )
        }

        items(race.racers, key = { it.lane }) { racer ->
            RacerCard(racer)
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text(
                        "AIスコア予想 3連単",
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.titleMedium
                    )
                    Text(
                        "全国/当地・平均ST・モーター/ボート・展示・直前ST・進入を合成",
                        style = MaterialTheme.typography.bodySmall
                    )
                    Spacer(Modifier.height(8.dp))
                    ui.predictions.forEachIndexed { index, pick ->
                        PredictionRow(index + 1, pick, ui.stakePerPick)
                        if (index < ui.predictions.lastIndex) {
                            HorizontalDivider(Modifier.padding(vertical = 6.dp))
                        }
                    }
                    if (ui.oddsLoading) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(
                                modifier = Modifier.width(20.dp).height(20.dp),
                                strokeWidth = 2.dp
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                "公式3連単オッズ取得中…",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                    ui.oddsError?.let { message ->
                        Spacer(Modifier.height(6.dp))
                        Text("オッズ取得失敗：$message", color = MaterialTheme.colorScheme.error)
                        OutlinedButton(onClick = vm::retryOdds) { Text("オッズを再取得") }
                    }
                    ui.oddsUpdatedAt?.let { updated ->
                        Text(
                            "オッズ最終取得 ${java.time.Instant.ofEpochMilli(updated).atZone(java.time.ZoneId.of("Asia/Tokyo")).format(DateTimeFormatter.ofPattern("HH:mm:ss"))}（開催中は60秒ごとに更新）",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    Spacer(Modifier.height(10.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        OutlinedButton(onClick = vm::decreaseStake) { Text("-100") }
                        Text(
                            " 各 ${ui.stakePerPick}円 ",
                            fontWeight = FontWeight.Bold
                        )
                        OutlinedButton(onClick = vm::increaseStake) { Text("+100") }
                    }
                    Text(
                        "合計 ${ui.stakePerPick * ui.predictions.size}円",
                        style = MaterialTheme.typography.bodySmall
                    )
                    Spacer(Modifier.height(8.dp))
                    Button(
                        onClick = vm::recordPredictions,
                        enabled = ui.predictions.isNotEmpty() && race.isPurchasable() && ui.records.none {
                            it.date == race.date && it.stadiumNumber == race.stadiumNumber && it.raceNumber == race.raceNumber
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(if (ui.records.any {
                            it.date == race.date && it.stadiumNumber == race.stadiumNumber && it.raceNumber == race.raceNumber
                        }) "✓ このレースは購入済み" else "このレースを個別購入登録")
                    }
                    ui.actionMessage?.let {
                        Text(
                            it,
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.padding(top = 6.dp)
                        )
                    }
                }
            }
        }

        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { uriHandler.openUri(programUrl) }) {
                    Icon(Icons.Default.OpenInBrowser, contentDescription = null)
                    Spacer(Modifier.width(4.dp))
                    Text("公式出走表")
                }
                OutlinedButton(onClick = { uriHandler.openUri(oddsUrl) }) {
                    Icon(Icons.Default.OpenInBrowser, contentDescription = null)
                    Spacer(Modifier.width(4.dp))
                    Text("公式オッズ")
                }
            }
        }
    }
}

@Composable
private fun RacerCard(racer: Racer) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    shape = MaterialTheme.shapes.small,
                    tonalElevation = 3.dp
                ) {
                    Text(
                        "${racer.lane}",
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                        fontWeight = FontWeight.Bold
                    )
                }
                Spacer(Modifier.width(10.dp))
                Column {
                    Text("${racer.name}  ${racer.rank}", fontWeight = FontWeight.Bold)
                    Text(
                        "登録 ${racer.registrationNumber ?: "-"} / 平均ST ${racer.averageStart.f2()}",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
            Spacer(Modifier.height(6.dp))
            Text(
                "全国 勝率 ${racer.nationalWinRate.f2()} / 2連 ${racer.nationalTop2.f1()}%　当地 ${racer.localWinRate.f2()}"
            )
            Text(
                "M${racer.motorNumber ?: "-"} 2連 ${racer.motorTop2.f1()}%　B${racer.boatNumber ?: "-"} 2連 ${racer.boatTop2.f1()}%"
            )
            racer.preview?.let { p ->
                Text(
                    "展示 ${p.exhibitionTime.f2()} / 進入 ${p.course ?: "-"} / 直前ST ${p.startTiming.f2()} / チルト ${p.tilt.f1()}",
                    fontWeight = FontWeight.SemiBold
                )
            }
        }
    }
}

@Composable
private fun PredictionRow(rank: Int, pick: PredictionPick, stake: Int) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column {
            Text(
                "$rank.  ${pick.combination}",
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleMedium
            )
            Text(
                "AI score ${String.format(Locale.US, "%.1f", pick.score)}",
                style = MaterialTheme.typography.bodySmall
            )
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(
                pick.odds?.let { "${String.format(Locale.US, "%.1f", it)}倍" } ?: "オッズ -"
            )
            pick.odds?.let {
                Text(
                    "想定 ${String.format(Locale.US, "%,.0f", it * stake)}円",
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
    }
}

private fun closeTime(raw: String): String {
    if (raw.isBlank()) return "--:--"
    val timeMatch = Regex("""(\d{2}:\d{2})""").findAll(raw).lastOrNull()?.value
    return timeMatch ?: raw.takeLast(5)
}

private fun rankLabel(score: Int): String = when (score) {
    in 90..100 -> "S"
    in 80..89 -> "A"
    in 70..79 -> "B"
    in 60..69 -> "C"
    else -> "D"
}

private fun gradeLabel(grade: Int?): String = when (grade) {
    1 -> "SG"
    2 -> "G1"
    3 -> "G2"
    4 -> "G3"
    else -> "一般"
}

private fun Double?.f1(): String =
    this?.let { String.format(Locale.US, "%.1f", it) } ?: "-"

private fun Double?.f2(): String =
    this?.let { String.format(Locale.US, "%.2f", it) } ?: "-"

private fun money(value: Int): String =
    String.format(Locale.JAPAN, "%,d円", value)

private fun signedMoney(value: Int): String =
    if (value >= 0) "+${money(value)}" else "-${money(-value)}"
