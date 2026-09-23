package jp.boatai.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.LocalActivity
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
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
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.filled.Settings
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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
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
        setContent { BoatAiTheme { BoatAiApp(vm) } }
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
    var settingsOpen by remember { mutableStateOf(false) }

    BackHandler {
        when {
            settingsOpen -> settingsOpen = false
            selected != null -> vm.closeRace()
            selectedVenue != null -> vm.closeVenue()
            ui.tab != 0 -> vm.setTab(0)
            else -> Unit
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        when {
                            settingsOpen -> "設定"
                            selected != null -> "${selected.venueName} ${selected.raceNumber}R"
                            selectedVenue != null -> "${Venues.name(selectedVenue)} 開催レース"
                            ui.tab == 0 -> "予想  v${BuildConfig.VERSION_NAME}"
                            ui.tab == 1 -> "購入"
                            ui.tab == 2 -> "結果"
                            else -> "損益"
                        }
                    )
                },
                navigationIcon = {
                    when {
                        settingsOpen -> IconButton(onClick = { settingsOpen = false }) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "設定を閉じる")
                        }
                        selected != null || selectedVenue != null -> {
                            IconButton(onClick = if (selected != null) vm::closeRace else vm::closeVenue) {
                                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "戻る")
                            }
                        }
                    }
                },
                actions = {
                    if (!settingsOpen) {
                        if (selected == null && selectedVenue == null && ui.tab in 0..2) {
                            IconButton(onClick = vm::refresh) {
                                Icon(Icons.Default.Refresh, contentDescription = "更新")
                            }
                        }
                        if (selected == null && selectedVenue == null) {
                            IconButton(onClick = { settingsOpen = true }) {
                                Icon(Icons.Default.Settings, contentDescription = "設定")
                            }
                        }
                    }
                }
            )
        },
        bottomBar = {
            if (!settingsOpen && selected == null && selectedVenue == null) {
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
                        icon = { Icon(Icons.Default.ShoppingCart, contentDescription = null) },
                        label = { Text("購入") }
                    )
                    NavigationBarItem(
                        selected = ui.tab == 2,
                        onClick = { vm.setTab(2) },
                        icon = { Icon(Icons.Default.CheckCircle, contentDescription = null) },
                        label = { Text("結果") }
                    )
                    NavigationBarItem(
                        selected = ui.tab == 3,
                        onClick = { vm.setTab(3) },
                        icon = { Icon(Icons.Default.AccountBalanceWallet, contentDescription = null) },
                        label = { Text("損益") }
                    )
                }
            }
        }
    ) { innerPadding ->
        Box(Modifier.fillMaxSize().padding(innerPadding)) {
            when {
                settingsOpen -> SettingsScreen(ui, vm)
                selected != null -> RaceDetailScreen(ui, vm)
                selectedVenue != null -> VenueDetailScreen(ui, vm, selectedVenue)
                ui.tab == 0 -> PredictionScreen(ui, vm)
                ui.tab == 1 -> PurchaseDashboardScreen(ui, vm)
                ui.tab == 2 -> CompactResultsScreen(ui, vm)
                else -> CompactProfitScreen(ui, vm)
            }
        }
    }
}

@Composable
private fun PredictionScreen(ui: BoatUiState, vm: BoatViewModel) {
    var sortMode by remember { mutableIntStateOf(0) }
    val venues = (1..24).map { stadium -> stadium to ui.races.filter { it.stadiumNumber == stadium } }
        .let { list ->
            when (sortMode) {
                1 -> list.sortedBy { (_, races) -> races.filter { it.isPurchasable() }.minOfOrNull { closeTime(it.closedAt) } ?: "99:99" }
                2 -> list.sortedByDescending { (_, races) -> races.count { it.isPurchasable() && PredictionEngine.isRecommended(it) } }
                else -> list
            }
        }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item { AppUpdateCard(ui.update, vm) }
        item { DateSelectorCard(ui, vm) }
        item { DataDiagnosticsCard(ui.diagnostics, onRetry = vm::refresh) }
        item { PredictionModeBar(sortMode) { sortMode = it } }
        item { BulkSelectionModeCard(vm) }

        if (ui.loading && ui.races.isEmpty()) {
            item {
                Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            }
        }

        ui.error?.let { message ->
            item {
                Card(
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                    modifier = Modifier.fillMaxWidth()
                ) { Text(message, modifier = Modifier.padding(12.dp)) }
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
                "購入ボタンは買い目と金額を「公式投票待ち」に固定保存して、テレボートのシンプル投票サイトを開きます。公式側で実際に投票した後、BOAT AIへ戻って投票できたレースだけ実購入として確定してください。",
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
            listOf("開催一覧", "締切順", "推奨数順").forEachIndexed { index, label ->
                TextButton(onClick = { onSelect(index) }) {
                    Text(label, fontWeight = if (selected == index) FontWeight.Bold else FontWeight.Normal)
                }
            }
        }
    }
}

@Composable
private fun BulkSelectionModeCard(vm: BoatViewModel) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("一括購入の対象", fontWeight = FontWeight.Bold)
            Text("AIの最終判断は「購入推奨 / 見送り」の2択です。", style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedButton(onClick = vm::selectAllPurchasable) { Text("購入推奨のみ") }
                OutlinedButton(onClick = vm::selectAllIncludingSkipped) { Text("見送りも含む") }
                OutlinedButton(onClick = vm::clearBulkSelection) { Text("解除") }
            }
        }
    }
}

@Composable
private fun VenueTile(stadium: Int, races: List<RaceData>, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val open = races.filter { it.isPurchasable() }
    val next = open.minByOrNull { closeTime(it.closedAt) }
    val recommended = open.count(PredictionEngine::isRecommended)
    val skipped = open.count { race ->
        if (PredictionEngine.hasValueStrategyModel()) {
            PredictionEngine.cachedValueSelection(race)?.recommendation == RaceRecommendation.SKIP
        } else {
            PredictionEngine.predict(race).isNotEmpty() && !PredictionEngine.isRecommended(race)
        }
    }
    val first = races.firstOrNull()
    Card(
        onClick = onClick,
        enabled = races.isNotEmpty(),
        modifier = modifier.heightIn(min = 112.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (races.isEmpty()) MaterialTheme.colorScheme.surfaceVariant else MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Column(Modifier.padding(9.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(Venues.name(stadium), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            if (first == null) {
                Text("開催なし", style = MaterialTheme.typography.bodySmall)
                Text("ーー")
            } else {
                Text("${gradeLabel(first.gradeNumber)}　${first.dayNumber?.let { "${it}日目" } ?: "開催中"}", style = MaterialTheme.typography.bodySmall, maxLines = 1)
                Text(next?.let { "${it.raceNumber}R  ${closeTime(it.closedAt)}" } ?: "本日終了", fontWeight = FontWeight.SemiBold)
                if (open.isNotEmpty()) {
                    Text("推奨 $recommended / 見送り $skipped", style = MaterialTheme.typography.labelSmall)
                }
            }
        }
    }
}

@Composable
private fun VenueDetailScreen(ui: BoatUiState, vm: BoatViewModel, stadium: Int) {
    val races = ui.races.filter { it.stadiumNumber == stadium }.sortedBy { it.raceNumber }
    val uriHandler = LocalUriHandler.current
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        ui.pendingPurchase?.let { pending -> item { PendingPurchaseCard(pending, vm) } }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("${Venues.name(stadium)}の一括購入", fontWeight = FontWeight.Bold)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        OutlinedButton(onClick = { vm.selectVenuePurchasable(stadium) }) { Text("購入推奨のみ") }
                        OutlinedButton(onClick = { vm.selectVenueIncludingSkipped(stadium) }) { Text("見送りも含む") }
                    }
                }
            }
        }
        if (ui.selectedForBulk.isNotEmpty()) item { BulkPurchaseCard(ui, vm) }
        item {
            VenuePredictionCard(
                races = races,
                ui = ui,
                purchasePicksFor = vm::purchasePicksFor,
                onToggle = vm::toggleBulkRace,
                onIndividualBuy = { race ->
                    if (vm.prepareRacePurchase(race)) {
                        uriHandler.openUri(PendingPurchaseStore.OFFICIAL_SIMPLE_BET_URL)
                    }
                },
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
            IconButton(onClick = vm::previousDay) { Icon(Icons.Default.ChevronLeft, contentDescription = "前日") }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(ui.date.format(formatter), fontWeight = FontWeight.Bold)
                Text(if (ui.loading) "データ更新中…" else "全国24場 / 実データ", style = MaterialTheme.typography.bodySmall)
            }
            IconButton(onClick = vm::nextDay) { Icon(Icons.Default.ChevronRight, contentDescription = "翌日") }
        }
    }
}

@Composable
private fun BulkPurchaseCard(ui: BoatUiState, vm: BoatViewModel) {
    val uriHandler = LocalUriHandler.current
    val selectedRaces = ui.races.filter { it.id in ui.selectedForBulk && it.isPurchasable() }
    val recommendedCount = selectedRaces.count(PredictionEngine::isRecommended)
    val skippedCount = selectedRaces.size - recommendedCount
    val selectedPicks = selectedRaces.map(vm::purchasePicksFor)
    val selectedTickets = selectedPicks.sumOf { it.size }
    val total = selectedPicks.sumOf { picks -> picks.sumOf { it.recommendedStake } }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text("一括購入", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text("選択 ${selectedRaces.size}レース（推奨 $recommendedCount / 見送り $skippedCount）")
            Text("${selectedTickets}点 / 合計 ${money(total)}", fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedButton(onClick = vm::decreaseStake) { Text("-100") }
                Text(" 1レース予算 ${money(ui.raceBudget)} ", fontWeight = FontWeight.Bold)
                OutlinedButton(onClick = vm::increaseStake) { Text("+100") }
            }
            Spacer(Modifier.height(8.dp))
            OutlinedButton(onClick = vm::clearBulkSelection) { Text("選択解除") }
            Spacer(Modifier.height(8.dp))
            ConfirmPurchaseButton(
                label = "選択分を一括投票へ",
                summary = "${selectedRaces.size}レース・${selectedTickets}点・合計${money(total)}を投票待ちに固定保存して、公式シンプル投票サイトを開きます。公式側で実際に投票後、BOAT AIへ戻って投票できたレースだけ実購入として確定してください。",
                enabled = selectedRaces.isNotEmpty() && selectedTickets > 0,
                modifier = Modifier.fillMaxWidth(),
                onConfirm = {
                    if (vm.prepareSelectedPurchase()) {
                        uriHandler.openUri(PendingPurchaseStore.OFFICIAL_SIMPLE_BET_URL)
                    }
                }
            )
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
    purchasePicksFor: (RaceData) -> List<PredictionPick>,
    onToggle: (String) -> Unit,
    onIndividualBuy: (RaceData) -> Unit,
    onDetail: (RaceData) -> Unit
) {
    val first = races.firstOrNull() ?: return
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("${first.venueName}　${first.title}", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            val sub = listOfNotNull(first.dayNumber?.let { "$it 日目" }, first.subtitle.takeIf { it.isNotBlank() }).joinToString(" / ")
            if (sub.isNotBlank()) Text(sub, style = MaterialTheme.typography.bodySmall)
            Spacer(Modifier.height(6.dp))
            races.forEachIndexed { index, race ->
                RacePredictionRow(
                    race = race,
                    checked = race.id in ui.selectedForBulk,
                    picks = purchasePicksFor(race),
                    purchasedStake = ui.records.filter { it.date == race.date && it.stadiumNumber == race.stadiumNumber && it.raceNumber == race.raceNumber }.sumOf { it.stake },
                    onToggle = { onToggle(race.id) },
                    onIndividualBuy = { onIndividualBuy(race) },
                    onDetail = { onDetail(race) }
                )
                if (index < races.lastIndex) HorizontalDivider(Modifier.padding(vertical = 6.dp))
            }
        }
    }
}

@Composable
private fun RacePredictionRow(
    race: RaceData,
    checked: Boolean,
    picks: List<PredictionPick>,
    purchasedStake: Int,
    onToggle: () -> Unit,
    onIndividualBuy: () -> Unit,
    onDetail: () -> Unit
) {
    val total = picks.sumOf { it.recommendedStake }
    val enabled = race.isPurchasable() && picks.isNotEmpty() && purchasedStake == 0
    val decision = PredictionEngine.recommendation(race)

    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        Checkbox(checked = checked, onCheckedChange = { onToggle() }, enabled = enabled)
        Column(modifier = Modifier.weight(1f)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("${race.raceNumber}R　締切 ${closeTime(race.closedAt)} ${remainingTime(race)}", fontWeight = FontWeight.Bold)
                Text(
                    when {
                        race.hasResult -> "結果確定"
                        race.isPurchasable() -> money(total)
                        race.date.take(10) < java.time.LocalDate.now(java.time.ZoneId.of("Asia/Tokyo")).toString() -> "終了"
                        !race.isDataComplete -> "情報取得待ち"
                        else -> "締切済み"
                    },
                    style = MaterialTheme.typography.bodySmall
                )
            }
            Text(
                if (picks.isEmpty()) {
                    if (PredictionEngine.hasValueStrategyModel() && race.isPurchasable()) "公式オッズ判定中" else "予想データ不足"
                } else picks.joinToString(" / ") { it.combination },
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )
            if (picks.isNotEmpty()) {
                Text(
                    decision.recommendation.label,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Bold,
                    color = if (decision.recommended) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                )
                Text(decision.reason, style = MaterialTheme.typography.bodySmall)
            }
            if (purchasedStake > 0) {
                Text("✓ 購入済み　${money(purchasedStake)}", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                ConfirmPurchaseButton(
                    label = if (purchasedStake > 0) "購入済み" else if (race.isPurchasable()) "公式投票へ" else "購入不可",
                    summary = "${race.venueName} ${race.raceNumber}R・${decision.recommendation.label}・${picks.size}点・合計${money(total)}を投票待ちに保存して公式サイトを開きます。実投票後にBOAT AIで完了記録してください。",
                    enabled = enabled,
                    outlined = true,
                    onConfirm = onIndividualBuy
                )
                TextButton(onClick = onDetail) { Text("詳細") }
            }
        }
    }
}

@Composable
private fun ResultsScreen(ui: BoatUiState, vm: BoatViewModel) {
    val results = ui.races.filter { it.hasResult }.sortedWith(compareBy<RaceData> { it.stadiumNumber }.thenBy { it.raceNumber })
    val predictionByRace = ui.predictionHistory.associateBy { it.id }
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item { DateSelectorCard(ui, vm) }
        if (ui.loading && results.isEmpty()) {
            item { Box(Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() } }
        }
        ui.error?.let { message ->
            item { Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) { Text(message, Modifier.padding(12.dp)) } }
        }
        if (!ui.loading && results.isEmpty()) item { Card { Text("この日はまだ確定結果がありません。", Modifier.padding(14.dp)) } }
        items(results, key = { it.id }) { race ->
            val record = predictionByRace[race.id]
            val purchases = ui.records.filter { it.date == race.date && it.stadiumNumber == race.stadiumNumber && it.raceNumber == race.raceNumber }
            ResultCard(race, record, purchases)
        }
    }
}

@Composable
private fun ResultCard(race: RaceData, prediction: PredictionRecord?, purchases: List<BetRecord>) {
    val result = race.result
    val actualStake = purchases.sumOf { it.stake }
    val actualPayout = purchases.sumOf { it.payout }
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("${race.venueName} ${race.raceNumber}R", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(6.dp))
            Row(Modifier.fillMaxWidth()) {
                Column(Modifier.weight(0.9f)) {
                    Text("着順", style = MaterialTheme.typography.labelMedium)
                    Text(result?.trifectaCombination ?: "-", fontWeight = FontWeight.Bold)
                }
                Column(Modifier.weight(0.9f)) {
                    Text("払戻", style = MaterialTheme.typography.labelMedium)
                    Text(result?.trifectaPayout?.let(::money) ?: "-", fontWeight = FontWeight.Bold)
                }
                Column(Modifier.weight(1.8f)) {
                    Text("事前予想", style = MaterialTheme.typography.labelMedium)
                    Text(prediction?.combinations?.joinToString(" / ") ?: "記録なし", maxLines = 3, overflow = TextOverflow.Ellipsis)
                }
            }
            prediction?.let {
                Spacer(Modifier.height(6.dp))
                Text("予想時判定 ${it.recommendation.label} / 仮想購入 ${money(it.simulatedStake)}", fontWeight = FontWeight.SemiBold)
                it.recommendationReason?.let { reason -> Text(reason, style = MaterialTheme.typography.bodySmall) }
                Text(if (it.hit) "予想的中　想定払戻 ${money(it.simulatedPayout)}" else "予想ハズレ", fontWeight = FontWeight.SemiBold)
                PredictionEngine.missReason(race, it.combinations)?.let { reason ->
                    Text("敗因分析：$reason", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                }
            }
            if (purchases.isNotEmpty()) {
                Text("購入買い目：" + purchases.joinToString(" / ") { "${it.combination} ${money(it.stake)}" }, style = MaterialTheme.typography.bodySmall)
                Text("実購入 ${money(actualStake)} / 払戻 ${money(actualPayout)} / 収支 ${signedMoney(actualPayout - actualStake)}", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun ProfitScreen(ui: BoatUiState, vm: BoatViewModel) {
    val settled = ui.predictionHistory.filter { it.settled && it.evaluationEligible }
    val allSummary = ProfitAnalytics.summarize(settled)
    val recommendedSummary = ProfitAnalytics.summarize(settled.filter { it.recommended })
    val skippedSummary = ProfitAnalytics.summarize(settled.filterNot { it.recommended })

    val settledActual = ui.records.filter { it.settled }
    val actualStake = settledActual.sumOf { it.stake }
    val actualPayout = settledActual.sumOf { it.payout }
    val pendingStake = ui.records.filter { !it.settled }.sumOf { it.stake }

    val dateText = ui.date.toString()
    val dayRecords = ui.records.filter { it.date == dateText }
    val dayAll = settled.filter { it.date == dateText }
    val dayRecommended = dayAll.filter { it.recommended }
    val dayAllSummary = ProfitAnalytics.summarize(dayAll)
    val dayRecommendedSummary = ProfitAnalytics.summarize(dayRecommended)
    val dayCapturedCount = ui.predictionHistory.count { it.date == dateText && it.evaluationEligible }
    val dayResultCount = ui.races.count { it.date.take(10) == dateText && it.hasResult }

    val weekStart = ui.date.minusDays(6)
    val weekStartText = weekStart.toString()
    val monthPrefix = String.format(Locale.US, "%04d-%02d", ui.date.year, ui.date.monthValue)
    val weekAll = settled.filter { record ->
        val day = record.date.take(10)
        day >= weekStartText && day <= dateText
    }
    val weekRecommendedSummary = ProfitAnalytics.summarize(weekAll.filter { it.recommended })
    val weekAllSummary = ProfitAnalytics.summarize(weekAll)
    val weekRecords = ui.records.filter { record ->
        val day = record.date.take(10)
        day >= weekStartText && day <= dateText
    }

    val monthAll = settled.filter { it.date.startsWith(monthPrefix) }
    val monthRecommendedSummary = ProfitAnalytics.summarize(monthAll.filter { it.recommended })
    val monthAllSummary = ProfitAnalytics.summarize(monthAll)
    val monthRecords = ui.records.filter { it.date.startsWith(monthPrefix) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item { HistoricalBacktestCard() }

        item { SummaryCard("購入推奨だけ買った場合（全期間）", recommendedSummary, "締切前に保存できた購入推奨だけを各${money(PredictionHistoryStore.DEFAULT_SIMULATION_STAKE)}×4点で計算") }
        item { SummaryCard("全予想を買った場合（全期間・比較用）", allSummary, "締切前に保存できた見送り判定を含む全予想の仮想成績") }
        item { SummaryCard("見送り判定の成績（検証用）", skippedSummary, "買わなかったレースの結果も追跡し、判定が正しかったか検証") }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text("実購入（確定分）", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text("購入合計 ${money(actualStake)}")
                    Text("払戻合計 ${money(actualPayout)}")
                    val roi = if (actualStake > 0) actualPayout * 100.0 / actualStake else 0.0
                    Text("損益 ${signedMoney(actualPayout - actualStake)}　回収率 ${formatPercent(roi)}", fontWeight = FontWeight.Bold)
                    Text("結果待ち ${ui.records.count { !it.settled }}点 / ${money(pendingStake)}（確定損益には未算入）", style = MaterialTheme.typography.bodySmall)
                }
            }
        }

        item {
            PredictionPeriodSummaryCard(
                title = "${ui.date} の全予想成績（今日）",
                recommended = dayRecommendedSummary,
                allPredictions = dayAllSummary,
                actualRecords = dayRecords,
                note = "締切前保存 $dayCapturedCount レース / 当日結果 $dayResultCount レース。未保存分は結果後に後付けせず、今後は5分前自動評価で全レース保存します。"
            )
        }

        item {
            PredictionPeriodSummaryCard(
                title = "直近7日（${weekStart.monthValue}/${weekStart.dayOfMonth}〜${ui.date.monthValue}/${ui.date.dayOfMonth}）の予想成績",
                recommended = weekRecommendedSummary,
                allPredictions = weekAllSummary,
                actualRecords = weekRecords,
                note = "直近7日間に締切前保存できた事前予想だけを集計"
            )
        }

        item {
            PredictionPeriodSummaryCard(
                title = "${ui.date.year}年${ui.date.monthValue}月の月間予想成績",
                recommended = monthRecommendedSummary,
                allPredictions = monthAllSummary,
                actualRecords = monthRecords,
                note = "この月に締切前保存できた全予想と購入推奨の累計。結果後の後付け予想は除外"
            )
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text("AI学習状況", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text("学習済み ${ui.learnedRaceCount}レース")
                    Text("5年ベースライン、端末学習、過去バージョンで判明した弱点を内部評価へ反映し、最終的に購入推奨/見送りへ変換します。", style = MaterialTheme.typography.bodySmall)
                }
            }
        }

        item { PerformanceFeedbackCard(ui) }
        item { AdvancedAnalyticsCard(ui) }
        item { BackupCard(ui, vm) }
        item { NotificationSettingsCard(ui, vm) }
    }
}

@Composable
private fun PredictionPeriodSummaryCard(
    title: String,
    recommended: AnalyticsSummary,
    allPredictions: AnalyticsSummary,
    actualRecords: List<BetRecord>,
    note: String
) {
    val settledActual = actualRecords.filter { it.settled }
    val actualStake = settledActual.sumOf { it.stake }
    val actualPayout = settledActual.sumOf { it.payout }
    val pending = actualRecords.filterNot { it.settled }
    val pendingStake = pending.sumOf { it.stake }
    val actualRoi = if (actualStake > 0) actualPayout * 100.0 / actualStake else 0.0

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text(title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(6.dp))
            Text("全予想（購入推奨＋見送り）", fontWeight = FontWeight.SemiBold)
            SummaryCompact(allPredictions)
            Text("期間損益 ${signedMoney(allPredictions.profit)}　回収率 ${formatPercent(allPredictions.roi)}", fontWeight = FontWeight.Bold)
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("購入推奨のみを買い続けた場合", fontWeight = FontWeight.SemiBold)
            SummaryCompact(recommended)
            Text("期間損益 ${signedMoney(recommended.profit)}　回収率 ${formatPercent(recommended.roi)}", fontWeight = FontWeight.Bold)
            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Text("実際の購入記録（確定分）", fontWeight = FontWeight.SemiBold)
            Text("購入 ${money(actualStake)} / 払戻 ${money(actualPayout)}")
            Text("損益 ${signedMoney(actualPayout - actualStake)}　回収率 ${formatPercent(actualRoi)}")
            if (pending.isNotEmpty()) {
                Text("結果待ち ${pending.size}点 / ${money(pendingStake)}（確定損益には未算入）", style = MaterialTheme.typography.bodySmall)
            }
            Spacer(Modifier.height(4.dp))
            Text(note, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun SummaryCard(title: String, summary: AnalyticsSummary, note: String) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp)) {
            Text(title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text("的中 ${summary.hits} / ${summary.races}レース　的中率 ${formatPercent(summary.hitRate)}", fontWeight = FontWeight.SemiBold)
            Text("購入 ${money(summary.stake)} / 払戻 ${money(summary.payout)}")
            Text("損益 ${signedMoney(summary.profit)}　回収率 ${formatPercent(summary.roi)}", fontWeight = FontWeight.Bold)
            Text(note, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun SummaryCompact(summary: AnalyticsSummary) {
    Text("${summary.hits}/${summary.races}的中　的中率 ${formatPercent(summary.hitRate)}　回収率 ${formatPercent(summary.roi)}")
    Text("購入 ${money(summary.stake)} / 払戻 ${money(summary.payout)} / ${signedMoney(summary.profit)}")
}

@Composable
private fun AppUpdateCard(update: AppUpdateState, vm: BoatViewModel) {
    val activity = LocalActivity.current
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
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
                    Button(onClick = { activity?.let(vm::downloadAndInstallUpdate) }, enabled = !update.downloading && activity != null) {
                        Text(if (update.downloading) "取得中" else "更新する")
                    }
                } else {
                    OutlinedButton(onClick = vm::checkForAppUpdate, enabled = !update.checking && !update.downloading) { Text("確認") }
                }
            }
            if (update.downloading) {
                Spacer(Modifier.height(8.dp))
                val progress = update.downloadProgress
                if (progress != null) {
                    LinearProgressIndicator(progress = { progress / 100f }, modifier = Modifier.fillMaxWidth())
                    Text("$progress%", style = MaterialTheme.typography.bodySmall)
                } else {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                }
            }
            update.releaseNotes?.takeIf { update.updateAvailable && it.isNotBlank() }?.let { notes ->
                Spacer(Modifier.height(6.dp))
                Text(notes.lineSequence().take(3).joinToString("\n"), style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun RaceDetailScreen(ui: BoatUiState, vm: BoatViewModel) {
    val race = ui.selectedRace ?: return
    val savedPrediction = ui.predictionHistory.firstOrNull { it.id == race.id }
    val decision = savedPrediction?.let {
        RecommendationDecision(
            it.recommendation,
            it.recommendationReason ?: if (it.recommended) "締切前保存時の購入推奨" else "締切前保存時の見送り"
        )
    } ?: PredictionEngine.recommendation(race)
    val uriHandler = LocalUriHandler.current
    val day = race.date.replace("-", "")
    val jcd = Venues.code(race.stadiumNumber)
    val programUrl = "https://www.boatrace.jp/owpc/pc/race/racelist?hd=$day&jcd=$jcd&rno=${race.raceNumber}"
    val oddsUrl = "https://www.boatrace.jp/owpc/pc/race/odds3t?hd=$day&jcd=$jcd&rno=${race.raceNumber}"

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        ui.pendingPurchase?.let { pending -> item { PendingPurchaseCard(pending, vm) } }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text(race.title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text("締切 ${race.closedAt}　${race.distance ?: 1800}m")
                    race.preview?.let { p ->
                        Spacer(Modifier.height(6.dp))
                        Text("直前: ${p.weather ?: "-"}　風 ${p.windSpeed ?: "-"}m/s ${p.windDirection ?: ""}　波 ${p.waveHeight ?: "-"}cm")
                        Text("気温 ${p.airTemperature.f1()}℃　水温 ${p.waterTemperature.f1()}℃")
                    }
                }
            }
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("AI購入判断", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text(
                        decision.recommendation.label,
                        fontWeight = FontWeight.Bold,
                        style = MaterialTheme.typography.headlineSmall,
                        color = if (decision.recommended) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                    )
                    Text(decision.reason, style = MaterialTheme.typography.bodySmall)
                }
            }
        }

        if (race.hasResult) {
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp)) {
                        Text("レース結果", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                        Text(
                            "3連単 ${race.result?.trifectaCombination ?: "-"}　払戻 ${race.result?.trifectaPayout?.let(::money) ?: "-"}",
                            fontWeight = FontWeight.Bold
                        )
                        savedPrediction?.let { prediction ->
                            Spacer(Modifier.height(4.dp))
                            Text("事前予想 ${prediction.combinations.joinToString(" / ").ifBlank { "買い目なし" }}")
                            Text(
                                if (prediction.hit) "予想的中　想定払戻 ${money(prediction.simulatedPayout)}" else "予想ハズレ",
                                fontWeight = FontWeight.SemiBold,
                                color = if (prediction.hit) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error
                            )
                        } ?: Text("このレースは締切前の予想履歴が保存されていません", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }

        item { Text("出走データ", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium) }
        items(race.racers, key = { it.lane }) { racer -> RacerCard(racer) }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("AI予想 3連単", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text("全国/当地・平均ST・モーター/ボート・展示・直前ST・進入を合成", style = MaterialTheme.typography.bodySmall)
                    Spacer(Modifier.height(8.dp))
                    ui.predictions.forEachIndexed { index, pick ->
                        PredictionRow(index + 1, pick, ui.stakePerPick)
                        if (index < ui.predictions.lastIndex) HorizontalDivider(Modifier.padding(vertical = 6.dp))
                    }
                    if (ui.oddsLoading) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(Modifier.width(20.dp).height(20.dp), strokeWidth = 2.dp)
                            Spacer(Modifier.width(8.dp))
                            Text("公式3連単オッズ取得中…", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    ui.oddsError?.let { message ->
                        Spacer(Modifier.height(6.dp))
                        Text("オッズ取得失敗：$message", color = MaterialTheme.colorScheme.error)
                        OutlinedButton(onClick = vm::retryOdds) { Text("オッズを再取得") }
                    }
                    ui.oddsUpdatedAt?.let { updated ->
                        Text(
                            "${ui.oddsSource ?: "公式"} / 最終取得 ${java.time.Instant.ofEpochMilli(updated).atZone(java.time.ZoneId.of("Asia/Tokyo")).format(DateTimeFormatter.ofPattern("HH:mm:ss"))}" +
                                if (System.currentTimeMillis() - updated > 90_000) " ⚠ 90秒以上前" else "（60秒更新）",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    ui.oddsChange?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                    ui.oddsDecision?.let { Text("オッズ判定：$it", fontWeight = FontWeight.SemiBold) }
                    Spacer(Modifier.height(10.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        OutlinedButton(onClick = vm::decreaseStake) { Text("-100") }
                        Text(" 1レース予算 ${money(ui.raceBudget)} ", fontWeight = FontWeight.Bold)
                        OutlinedButton(onClick = vm::increaseStake) { Text("+100") }
                    }
                    Text("推奨合計 ${money(ui.predictions.sumOf { it.recommendedStake })}（1,000〜3,000円）", style = MaterialTheme.typography.bodySmall)
                    Spacer(Modifier.height(8.dp))
                    ConfirmPurchaseButton(
                        label = if (ui.records.any { it.date == race.date && it.stadiumNumber == race.stadiumNumber && it.raceNumber == race.raceNumber }) "✓ このレースは購入済み" else "公式投票へ",
                        summary = "${race.venueName} ${race.raceNumber}R・${decision.recommendation.label}・${ui.predictions.size}点・合計${money(ui.predictions.sumOf { it.recommendedStake })}を投票待ちに保存して公式サイトを開きます。実投票後にBOAT AIで完了記録してください。",
                        enabled = ui.predictions.isNotEmpty() && race.isPurchasable() && ui.records.none { it.date == race.date && it.stadiumNumber == race.stadiumNumber && it.raceNumber == race.raceNumber },
                        modifier = Modifier.fillMaxWidth(),
                        onConfirm = {
                            if (vm.preparePredictionsPurchase()) {
                                uriHandler.openUri(PendingPurchaseStore.OFFICIAL_SIMPLE_BET_URL)
                            }
                        }
                    )
                    ui.actionMessage?.let { Text(it, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 6.dp)) }
                }
            }
        }

        item { DataDiagnosticsCard(ui.oddsDiagnostics, title = "オッズ取得診断", onRetry = vm::retryOdds) }
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
                Surface(shape = MaterialTheme.shapes.small, tonalElevation = 3.dp) {
                    Text("${racer.lane}", Modifier.padding(horizontal = 12.dp, vertical = 8.dp), fontWeight = FontWeight.Bold)
                }
                Spacer(Modifier.width(10.dp))
                Column {
                    Text("${racer.name}  ${racer.rank}", fontWeight = FontWeight.Bold)
                    Text("登録 ${racer.registrationNumber ?: "-"} / 平均ST ${racer.averageStart.f2()}", style = MaterialTheme.typography.bodySmall)
                }
            }
            Spacer(Modifier.height(6.dp))
            Text("全国 勝率 ${racer.nationalWinRate.f2()} / 2連 ${racer.nationalTop2.f1()}%　当地 ${racer.localWinRate.f2()}")
            Text("M${racer.motorNumber ?: "-"} 2連 ${racer.motorTop2.f1()}%　B${racer.boatNumber ?: "-"} 2連 ${racer.boatTop2.f1()}%")
            racer.preview?.let { p ->
                Text("展示 ${p.exhibitionTime.f2()} / 進入 ${p.course ?: "-"} / 直前ST ${p.startTiming.f2()} / チルト ${p.tilt.f1()}", fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun PredictionRow(rank: Int, pick: PredictionPick, stake: Int) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text("$rank.  ${pick.combination}", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text(pick.tier.label, style = MaterialTheme.typography.bodySmall)
            Text(pick.reason, style = MaterialTheme.typography.labelSmall)
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(pick.odds?.let { "${String.format(Locale.US, "%.1f", it)}倍" } ?: "オッズ -")
            Text("推奨 ${money(pick.recommendedStake.takeIf { it > 0 } ?: stake)}", fontWeight = FontWeight.SemiBold)
            pick.odds?.let {
                Text("想定 ${String.format(Locale.US, "%,.0f", it * (pick.recommendedStake.takeIf { amount -> amount > 0 } ?: stake))}円", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

private fun closeTime(raw: String): String {
    if (raw.isBlank()) return "--:--"
    return Regex("""(\d{2}:\d{2})""").findAll(raw).lastOrNull()?.value ?: raw.takeLast(5)
}

private fun remainingTime(race: RaceData): String {
    if (!race.isPurchasable()) return ""
    val time = Regex("""(\d{1,2}):(\d{2})""").findAll(race.closedAt).lastOrNull() ?: return ""
    val close = runCatching {
        java.time.LocalDateTime.of(
            java.time.LocalDate.parse(race.date.take(10)),
            java.time.LocalTime.of(time.groupValues[1].toInt(), time.groupValues[2].toInt())
        )
    }.getOrNull() ?: return ""
    val minutes = java.time.Duration.between(java.time.LocalDateTime.now(java.time.ZoneId.of("Asia/Tokyo")), close).toMinutes().coerceAtLeast(0)
    return "（あと${minutes}分）"
}

private fun gradeLabel(grade: Int?): String = when (grade) {
    1 -> "SG"
    2 -> "G1"
    3 -> "G2"
    4 -> "G3"
    else -> "一般"
}

private fun Double?.f1(): String = this?.let { String.format(Locale.US, "%.1f", it) } ?: "-"
private fun Double?.f2(): String = this?.let { String.format(Locale.US, "%.2f", it) } ?: "-"
private fun money(value: Int): String = String.format(Locale.JAPAN, "%,d円", value)
private fun signedMoney(value: Int): String = if (value >= 0) "+${money(value)}" else "-${money(-value)}"
private fun formatPercent(value: Double): String = String.format(Locale.US, "%.1f%%", value)
