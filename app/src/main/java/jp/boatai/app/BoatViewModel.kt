package jp.boatai.app

import android.app.Activity
import android.app.Application
import android.content.Context
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId

data class BoatUiState(
    val date: LocalDate = LocalDate.now(ZoneId.of("Asia/Tokyo")),
    val races: List<RaceData> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null,
    val selectedRace: RaceData? = null,
    val selectedVenue: Int? = null,
    val predictions: List<PredictionPick> = emptyList(),
    val oddsLoading: Boolean = false,
    val oddsError: String? = null,
    val oddsUpdatedAt: Long? = null,
    val oddsSource: String? = null,
    val diagnostics: List<DataSourceDiagnostic> = emptyList(),
    val oddsDiagnostics: List<DataSourceDiagnostic> = emptyList(),
    val oddsDecision: String? = null,
    val oddsChange: String? = null,
    val records: List<BetRecord> = emptyList(),
    val predictionHistory: List<PredictionRecord> = emptyList(),
    val performance: PredictionPerformanceProfile = PredictionPerformanceProfile(),
    val selectedForBulk: Set<String> = emptySet(),
    val stakePerPick: Int = 300,
    val raceBudget: Int = BetStrategy.DEFAULT_BUDGET,
    val tab: Int = 0,
    val lastUpdatedAt: Long? = null,
    val actionMessage: String? = null,
    val learnedRaceCount: Int = 0,
    val notificationsEnabled: Boolean = false,
    val update: AppUpdateState = AppUpdateState()
)

class BoatViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = BoatRaceRepository()
    private val betStore = BetStore(application)
    private val predictionStore = PredictionHistoryStore(application)
    private val appUpdateManager = AppUpdateManager(application)
    private val learningStore = LearningStore(application)
    private val notificationScheduler = NotificationScheduler(application)
    private val today = LocalDate.now(ZoneId.of("Asia/Tokyo"))
    private var oddsRefreshJob: Job? = null
    private val initialPredictionHistory = predictionStore.load()
    private val initialPerformance = PredictionPerformanceProfile.from(initialPredictionHistory)

    private val _ui = MutableStateFlow(
        BoatUiState(
            records = betStore.load(),
            predictionHistory = initialPredictionHistory,
            performance = initialPerformance,
            notificationsEnabled = notificationScheduler.enabled
        )
    )
    val ui: StateFlow<BoatUiState> = _ui.asStateFlow()

    init {
        val initialLearning = learningStore.load()
        PredictionEngine.installLearningProfile(initialLearning)
        PredictionEngine.installPerformanceProfile(initialPerformance)
        _ui.update { it.copy(learnedRaceCount = initialLearning.totalRaceCount) }
        viewModelScope.launch {
            appUpdateManager.state.collectLatest { updateState ->
                _ui.update { it.copy(update = updateState) }
                if (updateState.updateAvailable) {
                    notificationScheduler.notifyNow(
                        "BOAT AI v${updateState.latestVersion}",
                        "新しいバージョンをアプリから更新できます",
                        2001
                    )
                }
            }
        }
        viewModelScope.launch {
            appUpdateManager.checkForUpdates()
        }
        loadDate(_ui.value.date)
    }

    fun loadDate(date: LocalDate) {
        if (date.isAfter(today)) return
        viewModelScope.launch {
            _ui.update {
                it.copy(
                    date = date,
                    loading = true,
                    error = null,
                    selectedRace = null,
                    selectedVenue = null,
                    predictions = emptyList(),
                    selectedForBulk = emptySet(),
                    actionMessage = null
                )
            }
            runCatching { repository.loadDateDetailed(date) }
                .onSuccess { loadResult ->
                    val races = loadResult.races
                    val beforePending = _ui.value.records.count { !it.settled }
                    val beforeLearned = _ui.value.learnedRaceCount
                    val records = betStore.settle(races)

                    // 予想は結果学習・成績反映より先に保存し、未来情報の混入を防ぐ。
                    predictionStore.captureOpenRaces(races)
                    val predictionHistory = predictionStore.settle(races)
                    val performance = PredictionPerformanceProfile.from(predictionHistory)
                    PredictionEngine.installPerformanceProfile(performance)

                    val learning = learningStore.observe(races)
                    PredictionEngine.installLearningProfile(learning)
                    notificationScheduler.scheduleDeadlines(races)
                    val newlySettled = beforePending - records.count { !it.settled }
                    if (newlySettled > 0) {
                        notificationScheduler.notifyNow("購入結果を反映", "${newlySettled}件の払戻・損益を更新しました", 2002)
                    }
                    if (beforeLearned > 0 && learning.totalRaceCount > beforeLearned) {
                        notificationScheduler.notifyNow("AI学習を更新", "新しい確定結果を次回予想へ反映しました", 2003)
                    }
                    _ui.update {
                        it.copy(
                            races = races,
                            records = records,
                            predictionHistory = predictionHistory,
                            performance = performance,
                            diagnostics = loadResult.diagnostics,
                            loading = false,
                            error = if (races.isEmpty()) "この日のレースデータがありません" else null,
                            lastUpdatedAt = System.currentTimeMillis(),
                            learnedRaceCount = learning.totalRaceCount
                        )
                    }
                }
                .onFailure { error ->
                    _ui.update {
                        it.copy(
                            loading = false,
                            error = error.message ?: "データ取得に失敗しました",
                            diagnostics = listOf(
                                DataSourceDiagnostic(
                                    "開催・出走データ",
                                    DiagnosticStatus.ERROR,
                                    error.message ?: "取得失敗"
                                )
                            )
                        )
                    }
                }
        }
    }

    fun previousDay() = loadDate(_ui.value.date.minusDays(1))
    fun nextDay() = loadDate(_ui.value.date.plusDays(1))
    fun refresh() = loadDate(_ui.value.date)

    fun selectRace(race: RaceData) {
        val initial = BetStrategy.allocate(race, PredictionEngine.predict(race), _ui.value.raceBudget)
        _ui.update {
            it.copy(
                selectedRace = race,
                predictions = initial,
                oddsLoading = true,
                oddsError = null,
                oddsSource = null,
                oddsDiagnostics = emptyList(),
                oddsDecision = null,
                oddsChange = null,
                error = null,
                actionMessage = null
            )
        }
        oddsRefreshJob?.cancel()
        loadOdds(race, initial)
        if (race.isPurchasable()) {
            oddsRefreshJob = viewModelScope.launch {
                while (_ui.value.selectedRace?.id == race.id && race.isPurchasable()) {
                    delay(60_000)
                    loadOdds(race, initial, showLoading = false)
                }
            }
        }
    }

    private fun loadOdds(race: RaceData, initial: List<PredictionPick>, showLoading: Boolean = true) {
        if (showLoading) _ui.update { it.copy(oddsLoading = true, oddsError = null) }
        viewModelScope.launch {
            runCatching {
                repository.loadOfficialTrifectaOddsDetailed(race, initial.map { it.combination })
            }
                .onSuccess { result ->
                    _ui.update { state ->
                        val nextPredictions = PredictionEngine.withOdds(race, initial, result.odds, state.raceBudget)
                        state.copy(
                            predictions = nextPredictions,
                            oddsLoading = false,
                            oddsUpdatedAt = result.fetchedAt,
                            oddsSource = result.source,
                            oddsDiagnostics = result.diagnostics,
                            oddsDecision = BetStrategy.oddsDecision(nextPredictions),
                            oddsChange = BetStrategy.oddsChange(state.predictions, nextPredictions),
                            oddsError = null
                        )
                    }
                }
                .onFailure { error ->
                    _ui.update { state ->
                        state.copy(
                            oddsLoading = false,
                            oddsError = error.message ?: "オッズ取得失敗",
                            oddsDiagnostics = listOf(
                                DataSourceDiagnostic(
                                    "公式オッズ",
                                    DiagnosticStatus.ERROR,
                                    error.message ?: "取得失敗"
                                )
                            )
                        )
                    }
                }
        }
    }

    fun retryOdds() {
        val race = _ui.value.selectedRace ?: return
        loadOdds(race, PredictionEngine.predict(race))
    }

    fun selectVenue(stadiumNumber: Int) {
        _ui.update { it.copy(selectedVenue = stadiumNumber, actionMessage = null) }
    }

    fun closeVenue() {
        _ui.update { it.copy(selectedVenue = null, selectedForBulk = emptySet(), actionMessage = null) }
    }

    fun closeRace() {
        oddsRefreshJob?.cancel()
        _ui.update {
            it.copy(
                selectedRace = null,
                predictions = emptyList(),
                oddsLoading = false,
                actionMessage = null
            )
        }
    }

    fun selectVenuePurchasable(stadiumNumber: Int) {
        val candidates = _ui.value.races.filter {
            it.stadiumNumber == stadiumNumber && it.isPurchasable() && PredictionEngine.predict(it).isNotEmpty()
        }
        val ids = candidates.filter { PredictionEngine.autoSkipReason(it) == null }
            .mapTo(linkedSetOf()) { it.id }
        val skipped = candidates.size - ids.size
        _ui.update {
            it.copy(
                selectedForBulk = ids,
                actionMessage = if (skipped > 0) "低実績条件の${skipped}レースを自動見送りしました" else null
            )
        }
    }

    fun selectVenueTop(stadiumNumber: Int, count: Int = 3) {
        val candidates = _ui.value.races.filter {
            it.stadiumNumber == stadiumNumber && it.isPurchasable() && PredictionEngine.predict(it).isNotEmpty()
        }
        val allowed = candidates.filter { PredictionEngine.autoSkipReason(it) == null }
        val ids = allowed.sortedByDescending(PredictionEngine::confidence)
            .take(count)
            .mapTo(linkedSetOf()) { it.id }
        val skipped = candidates.size - allowed.size
        _ui.update {
            it.copy(
                selectedForBulk = ids,
                actionMessage = if (skipped > 0) "低実績条件の${skipped}レースを候補から除外しました" else null
            )
        }
    }

    fun selectConfidenceAtLeast(minimum: Int) {
        val candidates = _ui.value.races.filter {
            it.isPurchasable() && PredictionEngine.predict(it).isNotEmpty() && PredictionEngine.confidence(it) >= minimum
        }
        val ids = candidates.filter { PredictionEngine.autoSkipReason(it) == null }
            .mapTo(linkedSetOf()) { it.id }
        val skipped = candidates.size - ids.size
        _ui.update {
            it.copy(
                selectedForBulk = ids,
                actionMessage = when {
                    ids.isEmpty() && skipped > 0 -> "AI期待度${minimum}以上はありますが、低実績条件のため自動見送りしました"
                    ids.isEmpty() -> "AI期待度${minimum}以上の対象レースはありません"
                    skipped > 0 -> "${ids.size}レース選択 / 低実績条件${skipped}レースを自動見送り"
                    else -> null
                }
            )
        }
    }

    fun setTab(tab: Int) {
        _ui.update {
            it.copy(
                tab = tab.coerceIn(0, 2),
                selectedRace = null,
                selectedVenue = null,
                predictions = emptyList(),
                actionMessage = null
            )
        }
    }

    fun increaseStake() = adjustBudget(100)

    fun decreaseStake() = adjustBudget(-100)

    private fun adjustBudget(delta: Int) {
        _ui.update { state ->
            val budget = (state.raceBudget + delta).coerceIn(BetStrategy.MIN_BUDGET, BetStrategy.MAX_BUDGET)
            val race = state.selectedRace
            val predictions = if (race != null) BetStrategy.allocate(race, state.predictions, budget) else state.predictions
            state.copy(
                raceBudget = budget,
                predictions = predictions,
                oddsDecision = if (race != null) BetStrategy.oddsDecision(predictions) else state.oddsDecision
            )
        }
    }

    fun toggleBulkRace(raceId: String) {
        val race = _ui.value.races.firstOrNull { it.id == raceId } ?: return
        if (!race.isPurchasable()) return
        _ui.update { state ->
            val next = state.selectedForBulk.toMutableSet()
            if (!next.add(raceId)) next.remove(raceId)
            state.copy(selectedForBulk = next, actionMessage = null)
        }
    }

    fun selectAllPurchasable() {
        val candidates = _ui.value.races.filter {
            it.isPurchasable() && PredictionEngine.predict(it).isNotEmpty()
        }
        val ids = candidates.filter { PredictionEngine.autoSkipReason(it) == null }
            .mapTo(linkedSetOf()) { it.id }
        val skipped = candidates.size - ids.size
        _ui.update {
            it.copy(
                selectedForBulk = ids,
                actionMessage = if (skipped > 0) "低実績条件の${skipped}レースを自動見送りしました" else null
            )
        }
    }

    fun clearBulkSelection() {
        _ui.update { it.copy(selectedForBulk = emptySet(), actionMessage = null) }
    }

    fun recordSelectedRaces() {
        val state = _ui.value
        val races = state.races.filter {
            it.id in state.selectedForBulk && it.isPurchasable()
        }
        if (races.isEmpty()) {
            _ui.update { it.copy(actionMessage = "購入するレースを選択してください") }
            return
        }

        val before = state.records.size
        val records = betStore.addRacePicks(races, state.raceBudget)
        val addedTickets = (records.size - before).coerceAtLeast(0)
        _ui.update {
            it.copy(
                records = records,
                selectedForBulk = emptySet(),
                actionMessage = "${races.size}レース / ${addedTickets}点を購入記録に追加しました"
            )
        }
    }

    fun recordRace(race: RaceData) {
        if (!race.isPurchasable()) return
        val picks = BetStrategy.allocate(race, PredictionEngine.predict(race), _ui.value.raceBudget)
        if (picks.isEmpty()) return
        val before = _ui.value.records.size
        val records = betStore.addPicks(race, picks, _ui.value.stakePerPick)
        val addedTickets = (records.size - before).coerceAtLeast(0)
        _ui.update {
            it.copy(
                records = records,
                actionMessage = if (addedTickets > 0) {
                    "${race.venueName} ${race.raceNumber}Rを${addedTickets}点、購入記録に追加しました"
                } else {
                    "${race.venueName} ${race.raceNumber}Rはすでに購入記録済みです"
                }
            )
        }
    }

    fun recordPredictions() {
        val state = _ui.value
        val race = state.selectedRace ?: return
        if (state.predictions.isEmpty() || !race.isPurchasable()) return
        val before = state.records.size
        val records = betStore.addPicks(race, state.predictions, state.stakePerPick)
        val addedTickets = (records.size - before).coerceAtLeast(0)
        _ui.update {
            it.copy(
                records = records,
                actionMessage = if (addedTickets > 0) {
                    "${race.venueName} ${race.raceNumber}Rを${addedTickets}点、購入記録に追加しました"
                } else {
                    "このレースはすでに購入記録済みです"
                }
            )
        }
    }

    fun clearRecords() {
        _ui.update {
            it.copy(
                records = betStore.clear(),
                actionMessage = "実購入の記録を削除しました"
            )
        }
    }

    fun setNotificationsEnabled(enabled: Boolean) {
        notificationScheduler.setEnabled(enabled)
        if (enabled) notificationScheduler.scheduleDeadlines(_ui.value.races)
        _ui.update {
            it.copy(
                notificationsEnabled = enabled,
                actionMessage = if (enabled) "通知を有効にしました" else "通知を無効にしました"
            )
        }
    }

    fun shareBackup(context: Context) = runCatching { DataBackupManager(context).shareBackup() }
        .onFailure { error -> _ui.update { it.copy(actionMessage = error.message ?: "バックアップ出力に失敗しました") } }

    fun shareCsv(context: Context) = runCatching { DataBackupManager(context).shareCsv() }
        .onFailure { error -> _ui.update { it.copy(actionMessage = error.message ?: "CSV出力に失敗しました") } }

    fun importBackup(context: Context, uri: Uri) {
        viewModelScope.launch {
            runCatching { DataBackupManager(context).restore(uri) }
                .onSuccess { restored ->
                    val predictions = predictionStore.load()
                    val performance = PredictionPerformanceProfile.from(predictions)
                    val learning = learningStore.load()
                    PredictionEngine.installPerformanceProfile(performance)
                    PredictionEngine.installLearningProfile(learning)
                    _ui.update {
                        it.copy(
                            records = betStore.load(),
                            predictionHistory = predictions,
                            performance = performance,
                            learnedRaceCount = learning.totalRaceCount,
                            actionMessage = "復元完了：実購入${restored.bets}件・予想${restored.predictions}件"
                        )
                    }
                }
                .onFailure { error ->
                    _ui.update { it.copy(actionMessage = "復元失敗：${error.message ?: "ファイルを確認してください"}") }
                }
        }
    }

    fun checkForAppUpdate() {
        viewModelScope.launch {
            appUpdateManager.checkForUpdates(userInitiated = true)
        }
    }

    fun downloadAndInstallUpdate(activity: Activity) {
        viewModelScope.launch {
            appUpdateManager.downloadAndInstall(activity)
        }
    }

    fun resumePendingInstall(activity: Activity) {
        appUpdateManager.resumePendingInstall(activity)
    }
}
