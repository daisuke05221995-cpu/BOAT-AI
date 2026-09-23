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
    val pendingPurchase: PendingPurchaseSession? = null,
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
    private val pendingPurchaseStore = PendingPurchaseStore(application)
    private val predictionStore = PredictionHistoryStore(application)
    private val appUpdateManager = AppUpdateManager(application)
    private val learningStore = LearningStore(application)
    private val performanceMemoryStore = PerformanceMemoryStore(application)
    private val notificationScheduler = NotificationScheduler(application)
    private val today = LocalDate.now(ZoneId.of("Asia/Tokyo"))
    private var oddsRefreshJob: Job? = null
    private var valueRefreshJob: Job? = null
    private val initialPredictionHistory = predictionStore.load()
    private val initialPerformance = PredictionPerformanceProfile.from(initialPredictionHistory)

    private val _ui = MutableStateFlow(
        BoatUiState(
            records = betStore.load(),
            pendingPurchase = pendingPurchaseStore.load(),
            predictionHistory = initialPredictionHistory,
            performance = initialPerformance,
            notificationsEnabled = notificationScheduler.enabled
        )
    )
    val ui: StateFlow<BoatUiState> = _ui.asStateFlow()

    init {
        val initialLearning = learningStore.load()
        PredictionEngine.installLearningProfile(initialLearning)
        PredictionEngine.installPersistentPerformanceProfile(performanceMemoryStore.load())
        PredictionEngine.installPerformanceProfile(initialPerformance)
        // v0.14.x has no promoted asset, so load() safely returns null and the legacy
        // engine remains unchanged. v0.15+ activates only after the validated exporter
        // has generated value_strategy_model.json.
        PredictionEngine.installValueStrategyModel(ValueStrategyModel.load(application))
        PredictionEngine.restoreValueSelections(initialPredictionHistory)
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
        val changingDate = date != _ui.value.date
        if (changingDate) {
            valueRefreshJob?.cancel()
            oddsRefreshJob?.cancel()
            PredictionEngine.clearValueSelections()
        }
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

                    // Existing resolved value decisions or the legacy engine may be
                    // persisted before result learning. Fresh value decisions are captured
                    // immediately after the official 120-way odds evaluation below.
                    val preOddsHistory = predictionStore.captureOpenRaces(races)
                    PredictionEngine.restoreValueSelections(preOddsHistory)
                    val preOddsPerformance = PredictionPerformanceProfile.from(preOddsHistory)
                    PredictionEngine.installPerformanceProfile(preOddsPerformance)

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
                            predictionHistory = preOddsHistory,
                            performance = preOddsPerformance,
                            diagnostics = loadResult.diagnostics,
                            loading = false,
                            error = if (races.isEmpty()) "この日のレースデータがありません" else null,
                            lastUpdatedAt = System.currentTimeMillis(),
                            learnedRaceCount = learning.totalRaceCount
                        )
                    }
                    refreshValueSelections(races)
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
        val initial = if (PredictionEngine.hasValueStrategyModel()) {
            val selection = PredictionEngine.cachedValueSelection(race)
            if (selection?.recommendation == RaceRecommendation.BUY) {
                BetStrategy.allocate(race, selection.picks, _ui.value.raceBudget)
            } else {
                emptyList()
            }
        } else {
            BetStrategy.allocate(race, PredictionEngine.predict(race), _ui.value.raceBudget)
        }
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
                    loadOdds(race, _ui.value.predictions, showLoading = false)
                }
            }
        }
    }

    private fun loadOdds(race: RaceData, initial: List<PredictionPick>, showLoading: Boolean = true) {
        if (showLoading) _ui.update { it.copy(oddsLoading = true, oddsError = null) }
        viewModelScope.launch {
            val requested = if (PredictionEngine.hasValueStrategyModel()) {
                PredictionEngine.valueOddsCombinations()
            } else {
                initial.map { it.combination }
            }
            if (requested.isEmpty()) {
                _ui.update { it.copy(oddsLoading = false, oddsError = "オッズ取得対象がありません") }
                return@launch
            }
            runCatching {
                repository.loadOfficialTrifectaOddsDetailed(race, requested)
            }
                .onSuccess { result ->
                    val strategyPredictions = PredictionEngine.withOdds(
                        race,
                        initial,
                        result.odds,
                        _ui.value.raceBudget
                    )
                    val decision = PredictionEngine.recommendation(race)
                    // Detail screen keeps an explicit manual-override candidate list for a
                    // user who deliberately buys a SKIP race. Those candidates are never
                    // used for AI virtual P/L or recommendation-only bulk purchase.
                    val displayedPredictions = if (
                        PredictionEngine.hasValueStrategyModel() &&
                        decision.recommendation == RaceRecommendation.SKIP
                    ) {
                        PredictionEngine.manualOverridePicks(race, _ui.value.raceBudget)
                            .map { pick ->
                                pick.copy(
                                    odds = result.odds[pick.combination],
                                    reason = "手動購入用候補（AI最終判断は見送り）"
                                )
                            }
                    } else {
                        strategyPredictions
                    }

                    val history = predictionStore.captureOpenRaces(listOf(race))
                    val performance = PredictionPerformanceProfile.from(history)
                    PredictionEngine.installPerformanceProfile(performance)

                    _ui.update { state ->
                        state.copy(
                            predictions = displayedPredictions,
                            predictionHistory = history,
                            performance = performance,
                            oddsLoading = false,
                            oddsUpdatedAt = result.fetchedAt,
                            oddsSource = result.source,
                            oddsDiagnostics = result.diagnostics,
                            oddsDecision = if (PredictionEngine.hasValueStrategyModel()) {
                                decision.reason
                            } else {
                                BetStrategy.oddsDecision(displayedPredictions)
                            },
                            oddsChange = BetStrategy.oddsChange(state.predictions, displayedPredictions),
                            oddsError = null,
                            lastUpdatedAt = System.currentTimeMillis()
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

    /**
     * Resolve every currently purchasable race whose exhibition data is ready. This is
     * intentionally sequential to avoid hammering the official site, while still making
     * list/bulk BUY-SKIP decisions available without opening each detail screen.
     */
    private fun refreshValueSelections(races: List<RaceData>) {
        if (!PredictionEngine.hasValueStrategyModel()) return
        val combinations = PredictionEngine.valueOddsCombinations()
        if (combinations.size != 120) return
        val candidates = races.filter {
            it.isPurchasable() && PredictionEngine.isDecisionReady(it)
        }
        if (candidates.isEmpty()) return

        valueRefreshJob?.cancel()
        valueRefreshJob = viewModelScope.launch {
            for (race in candidates) {
                if (!race.isPurchasable()) continue
                if (PredictionEngine.cachedValueSelection(race) != null) continue
                runCatching {
                    repository.loadOfficialTrifectaOddsDetailed(race, combinations)
                }.onSuccess { result ->
                    PredictionEngine.applyValueOdds(race, result.odds)
                    val history = predictionStore.captureOpenRaces(listOf(race))
                    val performance = PredictionPerformanceProfile.from(history)
                    PredictionEngine.installPerformanceProfile(performance)
                    _ui.update { state ->
                        if (state.selectedRace?.id == race.id) {
                            val selection = PredictionEngine.cachedValueSelection(race)
                            val picks = if (selection?.recommendation == RaceRecommendation.BUY) {
                                BetStrategy.allocate(race, selection.picks, state.raceBudget)
                            } else {
                                state.predictions
                            }
                            state.copy(
                                predictions = picks,
                                predictionHistory = history,
                                performance = performance,
                                oddsUpdatedAt = result.fetchedAt,
                                oddsSource = result.source,
                                lastUpdatedAt = System.currentTimeMillis()
                            )
                        } else {
                            state.copy(
                                predictionHistory = history,
                                performance = performance,
                                lastUpdatedAt = System.currentTimeMillis()
                            )
                        }
                    }
                }
                delay(250)
            }
        }
    }

    fun retryOdds() {
        val race = _ui.value.selectedRace ?: return
        loadOdds(race, _ui.value.predictions)
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
        val candidates = purchasableCandidates(stadiumNumber)
        val ids = candidates.filter(PredictionEngine::isRecommended).mapTo(linkedSetOf()) { it.id }
        val skipped = candidates.size - ids.size
        _ui.update {
            it.copy(
                selectedForBulk = ids,
                actionMessage = "購入推奨 ${ids.size}レースを選択" + if (skipped > 0) " / 見送り ${skipped}レースは除外" else ""
            )
        }
    }

    fun selectVenueIncludingSkipped(stadiumNumber: Int) {
        val candidates = purchasableCandidates(stadiumNumber)
        val ids = candidates.mapTo(linkedSetOf()) { it.id }
        val recommended = candidates.count(PredictionEngine::isRecommended)
        _ui.update {
            it.copy(
                selectedForBulk = ids,
                actionMessage = "判定済み全${ids.size}レースを選択（購入推奨 $recommended / 見送り ${ids.size - recommended}）"
            )
        }
    }

    // 旧UI互換。内部スコア上位ではなく購入推奨の先頭から選ぶ。
    fun selectVenueTop(stadiumNumber: Int, count: Int = 3) {
        val ids = purchasableCandidates(stadiumNumber)
            .filter(PredictionEngine::isRecommended)
            .take(count)
            .mapTo(linkedSetOf()) { it.id }
        _ui.update { it.copy(selectedForBulk = ids, actionMessage = "購入推奨から${ids.size}レースを選択") }
    }

    // 旧UI互換。値モデル稼働時も購入推奨だけを対象にする。
    fun selectConfidenceAtLeast(minimum: Int) {
        val candidates = purchasableCandidates()
        val ids = candidates.filter { PredictionEngine.isRecommended(it) && PredictionEngine.confidence(it) >= minimum }
            .mapTo(linkedSetOf()) { it.id }
        _ui.update { it.copy(selectedForBulk = ids, actionMessage = "購入推奨 ${ids.size}レースを選択") }
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
                oddsDecision = if (race != null && !PredictionEngine.hasValueStrategyModel()) {
                    BetStrategy.oddsDecision(predictions)
                } else {
                    state.oddsDecision
                }
            )
        }
    }

    fun toggleBulkRace(raceId: String) {
        val race = _ui.value.races.firstOrNull { it.id == raceId } ?: return
        if (!race.isPurchasable()) return
        if (PredictionEngine.hasValueStrategyModel() && PredictionEngine.cachedValueSelection(race) == null) {
            _ui.update { it.copy(actionMessage = "${race.venueName} ${race.raceNumber}Rは公式オッズ判定中です") }
            return
        }
        _ui.update { state ->
            val next = state.selectedForBulk.toMutableSet()
            if (!next.add(raceId)) next.remove(raceId)
            state.copy(selectedForBulk = next, actionMessage = null)
        }
    }

    fun selectAllPurchasable() {
        val candidates = purchasableCandidates()
        val ids = candidates.filter(PredictionEngine::isRecommended).mapTo(linkedSetOf()) { it.id }
        val skipped = candidates.size - ids.size
        _ui.update {
            it.copy(
                selectedForBulk = ids,
                actionMessage = "購入推奨 ${ids.size}レースを選択" + if (skipped > 0) " / 見送り ${skipped}レースは除外" else ""
            )
        }
    }

    fun selectAllIncludingSkipped() {
        val candidates = purchasableCandidates()
        val ids = candidates.mapTo(linkedSetOf()) { it.id }
        val recommended = candidates.count(PredictionEngine::isRecommended)
        _ui.update {
            it.copy(
                selectedForBulk = ids,
                actionMessage = "判定済み全${ids.size}レースを選択（購入推奨 $recommended / 見送り ${ids.size - recommended}）"
            )
        }
    }

    fun clearBulkSelection() {
        _ui.update { it.copy(selectedForBulk = emptySet(), actionMessage = null) }
    }

    /** Purchase preview used by both UI totals and final record creation. */
    fun purchasePicksFor(race: RaceData): List<PredictionPick> {
        if (!race.isPurchasable()) return emptyList()
        val budget = _ui.value.raceBudget
        if (!PredictionEngine.hasValueStrategyModel()) {
            return BetStrategy.allocate(race, PredictionEngine.predict(race), budget)
        }
        val selection = PredictionEngine.cachedValueSelection(race) ?: return emptyList()
        return if (selection.recommendation == RaceRecommendation.BUY) {
            BetStrategy.allocate(race, selection.picks, budget)
        } else {
            // Only reached from explicit user selection of a SKIP race.
            PredictionEngine.manualOverridePicks(race, budget)
        }
    }

    fun prepareSelectedPurchase(): Boolean {
        val state = _ui.value
        val races = state.races.filter { it.id in state.selectedForBulk && it.isPurchasable() }
        if (races.isEmpty()) {
            _ui.update { it.copy(actionMessage = "購入するレースを選択してください") }
            return false
        }
        val entries = races.mapNotNull { race ->
            val picks = purchasePicksFor(race)
            if (picks.isEmpty()) null else race to picks
        }
        return savePendingPurchase(entries, "${entries.size}レースを一括投票待ちに保存")
    }

    fun prepareRacePurchase(race: RaceData): Boolean {
        if (!race.isPurchasable()) return false
        val picks = purchasePicksFor(race)
        if (picks.isEmpty()) {
            _ui.update { it.copy(actionMessage = "公式オッズの最終判定を待ってください") }
            return false
        }
        return savePendingPurchase(listOf(race to picks), "${race.venueName} ${race.raceNumber}Rを投票待ちに保存")
    }

    fun preparePredictionsPurchase(): Boolean {
        val state = _ui.value
        val race = state.selectedRace ?: return false
        if (!race.isPurchasable() || state.predictions.isEmpty()) return false
        return savePendingPurchase(
            listOf(race to state.predictions),
            "${race.venueName} ${race.raceNumber}Rを投票待ちに保存"
        )
    }

    private fun savePendingPurchase(
        entries: List<Pair<RaceData, List<PredictionPick>>>,
        message: String
    ): Boolean {
        if (entries.isEmpty()) {
            _ui.update { it.copy(actionMessage = "投票できる買い目がありません") }
            return false
        }
        val session = PendingPurchaseSession.create(entries)
        if (session == null) {
            _ui.update { it.copy(actionMessage = "100円単位の買い目を作成できませんでした") }
            return false
        }
        pendingPurchaseStore.save(session)
        _ui.update {
            it.copy(
                pendingPurchase = session,
                selectedForBulk = emptySet(),
                actionMessage = "$message。公式サイトで投票後、BOAT AIへ戻って完了記録してください"
            )
        }
        return true
    }

    fun togglePendingPurchaseRace(raceId: String) {
        val session = _ui.value.pendingPurchase ?: return
        if (session.races.none { it.raceId == raceId }) return
        val selected = session.selectedRaceIds.toMutableSet()
        if (!selected.add(raceId)) selected.remove(raceId)
        val updated = session.copy(selectedRaceIds = selected)
        pendingPurchaseStore.save(updated)
        _ui.update { it.copy(pendingPurchase = updated, actionMessage = null) }
    }

    fun selectAllPendingPurchaseRaces() {
        val session = _ui.value.pendingPurchase ?: return
        val updated = session.copy(selectedRaceIds = session.races.mapTo(linkedSetOf()) { it.raceId })
        pendingPurchaseStore.save(updated)
        _ui.update { it.copy(pendingPurchase = updated, actionMessage = null) }
    }

    fun confirmPendingPurchase() {
        val session = _ui.value.pendingPurchase ?: return
        val selected = session.selectedRaces
        if (selected.isEmpty()) {
            _ui.update { it.copy(actionMessage = "公式サイトで実際に投票できたレースを選択してください") }
            return
        }
        val before = _ui.value.records.size
        val records = betStore.addConfirmedPurchases(selected)
        val addedTickets = (records.size - before).coerceAtLeast(0)
        pendingPurchaseStore.clear()
        _ui.update {
            it.copy(
                records = records,
                pendingPurchase = null,
                actionMessage = "${selected.size}レース / ${addedTickets}点を実購入として記録しました"
            )
        }
    }

    fun cancelPendingPurchase() {
        pendingPurchaseStore.clear()
        _ui.update { it.copy(pendingPurchase = null, actionMessage = "投票待ちを破棄しました") }
    }

    fun recordSelectedRaces() {
        val state = _ui.value
        val races = state.races.filter { it.id in state.selectedForBulk && it.isPurchasable() }
        if (races.isEmpty()) {
            _ui.update { it.copy(actionMessage = "購入するレースを選択してください") }
            return
        }

        val entries = races.mapNotNull { race ->
            val picks = purchasePicksFor(race)
            if (picks.isEmpty()) null else race to picks
        }
        if (entries.isEmpty()) {
            _ui.update { it.copy(actionMessage = "公式オッズ判定済みの買い目がありません") }
            return
        }

        val before = state.records.size
        val records = betStore.addResolvedRacePicks(entries, state.stakePerPick)
        val addedTickets = (records.size - before).coerceAtLeast(0)
        val recommended = races.count(PredictionEngine::isRecommended)
        _ui.update {
            it.copy(
                records = records,
                selectedForBulk = emptySet(),
                actionMessage = "${entries.size}レース / ${addedTickets}点を購入記録に追加（推奨 $recommended / 手動見送り ${entries.size - recommended}）"
            )
        }
    }

    fun recordRace(race: RaceData) {
        if (!race.isPurchasable()) return
        val picks = purchasePicksFor(race)
        if (picks.isEmpty()) {
            _ui.update { it.copy(actionMessage = "公式オッズの最終判定を待ってください") }
            return
        }
        val before = _ui.value.records.size
        val records = betStore.addPicks(race, picks, _ui.value.stakePerPick)
        val addedTickets = (records.size - before).coerceAtLeast(0)
        val manual = PredictionEngine.hasValueStrategyModel() && !PredictionEngine.isRecommended(race)
        _ui.update {
            it.copy(
                records = records,
                actionMessage = if (addedTickets > 0) {
                    "${race.venueName} ${race.raceNumber}Rを${addedTickets}点、購入記録に追加しました" +
                        if (manual) "（AI見送りを手動購入）" else ""
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
        val manual = PredictionEngine.hasValueStrategyModel() && !PredictionEngine.isRecommended(race)
        _ui.update {
            it.copy(
                records = records,
                actionMessage = if (addedTickets > 0) {
                    "${race.venueName} ${race.raceNumber}Rを${addedTickets}点、購入記録に追加しました" +
                        if (manual) "（AI見送りを手動購入）" else ""
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
                    PredictionEngine.installPersistentPerformanceProfile(performanceMemoryStore.load())
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
        viewModelScope.launch { appUpdateManager.checkForUpdates(userInitiated = true) }
    }

    fun downloadAndInstallUpdate(activity: Activity) {
        viewModelScope.launch { appUpdateManager.downloadAndInstall(activity) }
    }

    fun resumePendingInstall(activity: Activity) {
        appUpdateManager.resumePendingInstall(activity)
    }

    private fun purchasableCandidates(stadiumNumber: Int? = null): List<RaceData> =
        _ui.value.races.filter { race ->
            if (stadiumNumber != null && race.stadiumNumber != stadiumNumber) return@filter false
            if (!race.isPurchasable()) return@filter false
            if (PredictionEngine.hasValueStrategyModel()) {
                PredictionEngine.isDecisionReady(race) && PredictionEngine.cachedValueSelection(race) != null
            } else {
                PredictionEngine.predict(race).isNotEmpty()
            }
        }
}
