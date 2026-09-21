package jp.boatai.app

import android.app.Activity
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.viewModels
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountBalanceWallet
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.OpenInBrowser
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
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

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        if (selected != null) "${selected.venueName} ${selected.raceNumber}R"
                        else if (ui.tab == 0) "BOAT AI  v${BuildConfig.VERSION_NAME}" else "収支・購入記録"
                    )
                },
                navigationIcon = {
                    if (selected != null) {
                        IconButton(onClick = vm::closeRace) {
                            Icon(Icons.Default.ArrowBack, contentDescription = "戻る")
                        }
                    }
                },
                actions = {
                    if (selected == null && ui.tab == 0) {
                        IconButton(onClick = vm::refresh) {
                            Icon(Icons.Default.Refresh, contentDescription = "更新")
                        }
                    }
                }
            )
        },
        bottomBar = {
            if (selected == null) {
                NavigationBar {
                    NavigationBarItem(
                        selected = ui.tab == 0,
                        onClick = { vm.setTab(0) },
                        icon = { Icon(Icons.Default.Home, contentDescription = null) },
                        label = { Text("レース") }
                    )
                    NavigationBarItem(
                        selected = ui.tab == 1,
                        onClick = { vm.setTab(1) },
                        icon = { Icon(Icons.Default.AccountBalanceWallet, contentDescription = null) },
                        label = { Text("収支") }
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
                ui.tab == 0 -> RaceListScreen(ui, vm)
                else -> RecordsScreen(ui, vm)
            }
        }
    }
}

@Composable
private fun RaceListScreen(ui: BoatUiState, vm: BoatViewModel) {
    val formatter = DateTimeFormatter.ofPattern("yyyy年M月d日(E)", Locale.JAPANESE)
    val grouped = ui.races.groupBy { it.stadiumNumber }.toSortedMap()

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            AppUpdateCard(ui.update, vm)
        }

        item {
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
                            if (ui.loading) "データ更新中…" else "全国24場対応 / 実データ",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    IconButton(onClick = vm::nextDay) {
                        Icon(Icons.Default.ChevronRight, contentDescription = "翌日")
                    }
                }
            }
        }

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
                ) {
                    Text(message, modifier = Modifier.padding(12.dp))
                }
            }
        }

        grouped.forEach { (stadium, races) ->
            item(key = "venue-$stadium") {
                VenueCard(races = races, onRaceClick = vm::selectRace)
            }
        }

        item {
            Text(
                "出走表・直前情報・結果は日次JSONから取得。予想4点の3連単オッズは選択時にBOAT RACE公式ページから直接取得します。",
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(4.dp)
            )
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

            update.releaseNotes?.takeIf { update.updateAvailable && it.isNotBlank() }?.let { notes ->
                Spacer(Modifier.height(6.dp))
                Text(notes.lineSequence().take(3).joinToString("\n"), style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun VenueCard(races: List<RaceData>, onRaceClick: (RaceData) -> Unit) {
    val first = races.firstOrNull() ?: return
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
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
            Spacer(Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                races.sortedBy { it.raceNumber }.forEach { race ->
                    OutlinedButton(onClick = { onRaceClick(race) }) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("${race.raceNumber}R", fontWeight = FontWeight.Bold)
                            Text(
                                race.closedAt.takeLast(8).take(5).ifBlank { "--:--" },
                                style = MaterialTheme.typography.labelSmall
                            )
                            if (race.hasResult) Text("確定", style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
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
    val programUrl = "https://www.boatrace.jp/owpc/pc/race/racelist?hd=$day&jcd=$jcd&rno=${race.raceNumber}"
    val oddsUrl = "https://www.boatrace.jp/owpc/pc/race/odds3t?hd=$day&jcd=$jcd&rno=${race.raceNumber}"

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text(race.title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
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
            Text("出走データ", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        }

        items(race.racers, key = { it.lane }) { racer ->
            RacerCard(racer)
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("AIスコア予想 3連単", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text(
                        "全国/当地・平均ST・モーター/ボート・展示・直前ST・進入を合成",
                        style = MaterialTheme.typography.bodySmall
                    )
                    Spacer(Modifier.height(8.dp))
                    ui.predictions.forEachIndexed { index, pick ->
                        PredictionRow(index + 1, pick, ui.stakePerPick)
                        if (index < ui.predictions.lastIndex) HorizontalDivider(Modifier.padding(vertical = 6.dp))
                    }
                    if (ui.oddsLoading) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(modifier = Modifier.width(20.dp).height(20.dp), strokeWidth = 2.dp)
                            Spacer(Modifier.width(8.dp))
                            Text("公式3連単オッズ取得中…", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        OutlinedButton(onClick = vm::decreaseStake) { Text("-100") }
                        Text(" 各 ${ui.stakePerPick}円 ", fontWeight = FontWeight.Bold)
                        OutlinedButton(onClick = vm::increaseStake) { Text("+100") }
                    }
                    Text(
                        "合計 ${ui.stakePerPick * ui.predictions.size}円",
                        style = MaterialTheme.typography.bodySmall
                    )
                    Spacer(Modifier.height(8.dp))
                    Button(
                        onClick = vm::recordPredictions,
                        enabled = ui.predictions.isNotEmpty() && !race.hasResult,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("この4点を購入記録に追加")
                    }
                    Text(
                        "現時点では実投票ではなく購入記録です。結果取得後に自動で的中・払戻を照合します。",
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(top = 6.dp)
                    )
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
                    Text("登録 ${racer.registrationNumber ?: "-"} / 平均ST ${racer.averageStart.f2()}", style = MaterialTheme.typography.bodySmall)
                }
            }
            Spacer(Modifier.height(6.dp))
            Text("全国 勝率 ${racer.nationalWinRate.f2()} / 2連 ${racer.nationalTop2.f1()}%　当地 ${racer.localWinRate.f2()}")
            Text("M${racer.motorNumber ?: "-"} 2連 ${racer.motorTop2.f1()}%　B${racer.boatNumber ?: "-"} 2連 ${racer.boatTop2.f1()}%")
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
            Text("$rank.  ${pick.combination}", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
            Text("AI score ${String.format(Locale.US, "%.1f", pick.score)}", style = MaterialTheme.typography.bodySmall)
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(pick.odds?.let { "${String.format(Locale.US, "%.1f", it)}倍" } ?: "オッズ -")
            pick.odds?.let {
                Text("想定 ${String.format(Locale.US, "%,.0f", it * stake)}円", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun RecordsScreen(ui: BoatUiState, vm: BoatViewModel) {
    val totalStake = ui.records.sumOf { it.stake }
    val totalPayout = ui.records.sumOf { it.payout }
    val profit = totalPayout - totalStake
    val roi = if (totalStake > 0) totalPayout * 100.0 / totalStake else 0.0

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp)) {
                    Text("累計", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text("投資 ${money(totalStake)}　払戻 ${money(totalPayout)}")
                    Text("収支 ${signedMoney(profit)}　回収率 ${String.format(Locale.US, "%.1f", roi)}%", fontWeight = FontWeight.Bold)
                    Text(
                        "未確定 ${ui.records.count { !it.settled }}件 / 確定 ${ui.records.count { it.settled }}件",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }

        if (ui.records.isEmpty()) {
            item {
                Text("購入記録はまだありません。レース詳細の予想から記録できます。")
            }
        } else {
            items(ui.records, key = { it.id }) { bet ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp)) {
                        Text("${bet.date}  ${bet.venueName} ${bet.raceNumber}R", fontWeight = FontWeight.Bold)
                        Text("3連単 ${bet.combination}　${money(bet.stake)}")
                        Text(
                            if (bet.settled) "払戻 ${money(bet.payout)} / 収支 ${signedMoney(bet.profit)}" else "結果待ち",
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
            }
        }

        if (ui.records.isNotEmpty()) {
            item {
                OutlinedButton(onClick = vm::clearRecords, modifier = Modifier.fillMaxWidth()) {
                    Text("購入記録を全削除")
                }
            }
        }
    }
}

private fun Double?.f1(): String = this?.let { String.format(Locale.US, "%.1f", it) } ?: "-"
private fun Double?.f2(): String = this?.let { String.format(Locale.US, "%.2f", it) } ?: "-"
private fun money(value: Int): String = String.format(Locale.JAPAN, "%,d円", value)
private fun signedMoney(value: Int): String = if (value >= 0) "+${money(value)}" else "-${money(-value)}"
