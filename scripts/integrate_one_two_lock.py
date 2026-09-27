from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if new in text:
        print(f"{label}: already integrated")
        return
    if old not in text:
        raise SystemExit(f"{label}: insertion point not found")
    path.write_text(text.replace(old, new, 1))
    print(f"{label}: integrated")


# --- BoatViewModel ---------------------------------------------------------
vm = Path("app/src/main/java/jp/boatai/app/BoatViewModel.kt")

replace_once(
    vm,
    '''    val notificationsEnabled: Boolean = false,
    val update: AppUpdateState = AppUpdateState()
)''',
    '''    val notificationsEnabled: Boolean = false,
    val oneTwoQuotes: Map<String, OneTwoLockQuote> = emptyMap(),
    val oneTwoLoading: Boolean = false,
    val oneTwoStats: OneTwoLockSummary = OneTwoLockSummary(),
    val update: AppUpdateState = AppUpdateState()
)''',
    "BoatUiState one-two fields",
)

replace_once(
    vm,
    '''    private val predictionStore = PredictionHistoryStore(application)
    private val modelARecentVirtualRepository = ModelARecentVirtualRepository(application)''',
    '''    private val predictionStore = PredictionHistoryStore(application)
    private val oneTwoStore = OneTwoLockHistoryStore(application)
    private val modelARecentVirtualRepository = ModelARecentVirtualRepository(application)''',
    "ViewModel one-two store",
)

replace_once(
    vm,
    '''    private var oddsRefreshJob: Job? = null
    private var valueRefreshJob: Job? = null''',
    '''    private var oddsRefreshJob: Job? = null
    private var valueRefreshJob: Job? = null
    private var oneTwoRefreshJob: Job? = null''',
    "ViewModel one-two job",
)

replace_once(
    vm,
    '''            predictionHistory = initialPredictionHistory,
            performance = initialPerformance,
            notificationsEnabled = notificationScheduler.enabled''',
    '''            predictionHistory = initialPredictionHistory,
            performance = initialPerformance,
            notificationsEnabled = notificationScheduler.enabled,
            oneTwoStats = oneTwoStore.summary()''',
    "Initial one-two stats",
)

replace_once(
    vm,
    '''        if (changingDate) {
            valueRefreshJob?.cancel()
            oddsRefreshJob?.cancel()
            PredictionEngine.clearValueSelections()
        }''',
    '''        if (changingDate) {
            valueRefreshJob?.cancel()
            oneTwoRefreshJob?.cancel()
            oddsRefreshJob?.cancel()
            PredictionEngine.clearValueSelections()
        }''',
    "Cancel one-two job on date change",
)

replace_once(
    vm,
    '''                    predictions = emptyList(),
                    selectedForBulk = emptySet(),
                    actionMessage = null''',
    '''                    predictions = emptyList(),
                    selectedForBulk = emptySet(),
                    oneTwoQuotes = emptyMap(),
                    oneTwoLoading = false,
                    actionMessage = null''',
    "Clear one-two quotes on load",
)

replace_once(
    vm,
    '''                    val beforeLearned = _ui.value.learnedRaceCount
                    val records = betStore.settle(races)

                    // Existing resolved value decisions''',
    '''                    val beforeLearned = _ui.value.learnedRaceCount
                    val records = betStore.settle(races)
                    oneTwoStore.settle(races)

                    // Existing resolved value decisions''',
    "Settle one-two history on date load",
)

replace_once(
    vm,
    '''                            error = if (races.isEmpty()) "この日のレースデータがありません" else null,
                            lastUpdatedAt = System.currentTimeMillis(),
                            learnedRaceCount = learning.totalRaceCount''',
    '''                            error = if (races.isEmpty()) "この日のレースデータがありません" else null,
                            lastUpdatedAt = System.currentTimeMillis(),
                            learnedRaceCount = learning.totalRaceCount,
                            oneTwoStats = oneTwoStore.summary()''',
    "Refresh one-two stats after settlement",
)

replace_once(
    vm,
    '''                    refreshValueSelections(races)
                }
''',
    '''                    refreshValueSelections(races)
                    refreshOneTwoLocks(races)
                }
''',
    "Start one-two quote refresh",
)

marker = '''    /**
     * Resolve every currently purchasable race whose exhibition data is ready. This is
'''
method = '''    private fun refreshOneTwoLocks(races: List<RaceData>) {
        oneTwoRefreshJob?.cancel()
        val candidates = races.mapNotNull { race ->
            if (!race.isPurchasable() || !PredictionEngine.isDecisionReady(race)) return@mapNotNull null
            val selection = OneTwoLockStrategy.selection(race) ?: return@mapNotNull null
            if (!selection.eligible) null else race to selection
        }
        val initialQuotes = candidates.associate { (race, selection) -> race.id to OneTwoLockQuote(selection) }
        _ui.update { state ->
            state.copy(
                oneTwoQuotes = initialQuotes,
                oneTwoLoading = candidates.isNotEmpty()
            )
        }
        if (candidates.isEmpty()) return

        oneTwoRefreshJob = viewModelScope.launch {
            for ((race, selection) in candidates) {
                if (!race.isPurchasable()) continue
                oneTwoStore.captureRace(race, selection)
                runCatching {
                    repository.loadOfficialTrifectaOddsDetailed(race, selection.combinations)
                }.onSuccess { result ->
                    val quote = OneTwoLockStrategy.quote(selection, result)
                    oneTwoStore.updateOdds(race.id, quote)
                    _ui.update { state ->
                        state.copy(
                            oneTwoQuotes = state.oneTwoQuotes + (race.id to quote),
                            oneTwoStats = oneTwoStore.summary()
                        )
                    }
                }.onFailure { error ->
                    val quote = OneTwoLockQuote(selection = selection, error = error.message ?: "公式オッズ取得失敗")
                    _ui.update { state ->
                        state.copy(oneTwoQuotes = state.oneTwoQuotes + (race.id to quote))
                    }
                }
            }
            _ui.update { it.copy(oneTwoLoading = false, oneTwoStats = oneTwoStore.summary()) }
        }
    }

'''
text = vm.read_text()
if method.strip() not in text:
    if marker not in text:
        raise SystemExit("One-two refresh method insertion point not found")
    vm.write_text(text.replace(marker, method + marker, 1))
    print("One-two refresh method: integrated")
else:
    print("One-two refresh method: already integrated")

replace_once(
    vm,
    '''                predictionHistory = history,
                performance = performance
            )''',
    '''                predictionHistory = history,
                performance = performance,
                oneTwoStats = oneTwoStore.summary()
            )''',
    "Sync one-two stats with accounting",
)

purchase_marker = '''    fun prepareSelectedPurchase(): Boolean {
'''
purchase_method = '''    fun prepareOneTwoLockPurchase(race: RaceData): Boolean {
        if (!race.isPurchasable()) return false
        val quote = _ui.value.oneTwoQuotes[race.id]
        if (quote == null || !quote.purchaseQualified) {
            _ui.update { it.copy(actionMessage = "1→2鉄板の90%＋3.1倍条件を満たしていません") }
            return false
        }
        val picks = OneTwoLockStrategy.purchasePicks(quote, _ui.value.raceBudget)
        if (picks.isEmpty()) {
            _ui.update { it.copy(actionMessage = "1→2鉄板の3点均等買いを作成できませんでした") }
            return false
        }
        return savePendingPurchase(
            entries = listOf(race to picks),
            message = "${race.venueName} ${race.raceNumber}Rの1→2鉄板3点を投票待ちに保存",
            strategyId = OneTwoLockStrategy.STRATEGY_ID
        )
    }

'''
text = vm.read_text()
if purchase_method.strip() not in text:
    if purchase_marker not in text:
        raise SystemExit("One-two purchase method insertion point not found")
    vm.write_text(text.replace(purchase_marker, purchase_method + purchase_marker, 1))
    print("One-two purchase method: integrated")
else:
    print("One-two purchase method: already integrated")

replace_once(
    vm,
    '''    private fun savePendingPurchase(
        entries: List<Pair<RaceData, List<PredictionPick>>>,
        message: String
    ): Boolean {''',
    '''    private fun savePendingPurchase(
        entries: List<Pair<RaceData, List<PredictionPick>>>,
        message: String,
        strategyId: String? = null
    ): Boolean {''',
    "Pending purchase strategy argument",
)

replace_once(
    vm,
    '''        val session = PendingPurchaseSession.create(entries)
''',
    '''        val session = PendingPurchaseSession.create(entries, strategyId)
''',
    "Pending purchase strategy propagation",
)


# --- MainActivity prediction mode -----------------------------------------
main = Path("app/src/main/java/jp/boatai/app/MainActivity.kt")
replace_once(
    main,
    '''            listOf("開催一覧", "締切順", "推奨数順").forEachIndexed { index, label ->''',
    '''            listOf("開催一覧", "締切順", "推奨数順", "1→2鉄板").forEachIndexed { index, label ->''',
    "Prediction mode label",
)

replace_once(
    main,
    '''        item { PredictionModeBar(sortMode) { sortMode = it } }
        item { BulkSelectionModeCard(vm) }

        if (ui.loading && ui.races.isEmpty()) {''',
    '''        item { PredictionModeBar(sortMode) { sortMode = it } }
        if (sortMode == 3) {
            item { OneTwoLockCandidateList(ui, vm) }
        } else {
            item { BulkSelectionModeCard(vm) }
        }

        if (ui.loading && ui.races.isEmpty()) {''',
    "Show one-two lock panel",
)

replace_once(
    main,
    '''        items(venues.chunked(3), key = { row -> row.joinToString { it.first.toString() } }) {
            row ->
''',
    '''        if (sortMode != 3) items(venues.chunked(3), key = { row -> row.joinToString { it.first.toString() } }) {
            row ->
''',
    "Hide venue grid in one-two mode",
)

replace_once(
    main,
    '''        if (ui.selectedForBulk.isNotEmpty()) item { BulkPurchaseCard(ui, vm) }
''',
    '''        if (sortMode != 3 && ui.selectedForBulk.isNotEmpty()) item { BulkPurchaseCard(ui, vm) }
''',
    "Hide legacy bulk card in one-two mode",
)


# --- Background tracking --------------------------------------------------
tracking = Path("app/src/main/java/jp/boatai/app/PredictionTrackingScheduler.kt")
replace_once(
    tracking,
    '''        val betStore = BetStore(this)
        val focusStore = FocusPredictionHistoryStore(this)

        reconcileRecentPending(today, predictionStore, betStore)''',
    '''        val betStore = BetStore(this)
        val focusStore = FocusPredictionHistoryStore(this)
        val oneTwoStore = OneTwoLockHistoryStore(this)

        reconcileRecentPending(today, predictionStore, betStore)''',
    "Bootstrap one-two store",
)

replace_once(
    tracking,
    '''            betStore.settle(races)
            focusStore.settle(races)
            PredictionTrackingScheduler(this).scheduleRaces(races)''',
    '''            betStore.settle(races)
            focusStore.settle(races)
            oneTwoStore.settle(races)
            PredictionTrackingScheduler(this).scheduleRaces(races)''',
    "Bootstrap one-two settle",
)

replace_once(
    tracking,
    '''        val focusStore = FocusPredictionHistoryStore(this)
        val pendingDateTexts = buildList {''',
    '''        val focusStore = FocusPredictionHistoryStore(this)
        val oneTwoStore = OneTwoLockHistoryStore(this)
        val pendingDateTexts = buildList {''',
    "Recovery one-two store",
)

replace_once(
    tracking,
    '''            focusStore.pendingDates().forEach(::add)
        }''',
    '''            focusStore.pendingDates().forEach(::add)
            oneTwoStore.pendingDates().forEach(::add)
        }''',
    "Recovery one-two pending dates",
)

replace_once(
    tracking,
    '''            betStore.settle(races)
            focusStore.settle(races)
        }
    }

    private suspend fun settleDate''',
    '''            betStore.settle(races)
            focusStore.settle(races)
            oneTwoStore.settle(races)
        }
    }

    private suspend fun settleDate''',
    "Recovery one-two settle",
)

replace_once(
    tracking,
    '''        val betStore = BetStore(this)
        val focusStore = FocusPredictionHistoryStore(this)

        fun hasPendingTarget(): Boolean {''',
    '''        val betStore = BetStore(this)
        val focusStore = FocusPredictionHistoryStore(this)
        val oneTwoStore = OneTwoLockHistoryStore(this)

        fun hasPendingTarget(): Boolean {''',
    "Settle one-two store",
)

replace_once(
    tracking,
    '''            val focusPending = FocusMode.values().any { mode ->
                focusStore.load(mode).any { record -> !record.settled && record.id == raceId }
            }
            return predictionPending || purchasePending || focusPending''',
    '''            val focusPending = FocusMode.values().any { mode ->
                focusStore.load(mode).any { record -> !record.settled && record.id == raceId }
            }
            val oneTwoPending = oneTwoStore.hasPending(raceId)
            return predictionPending || purchasePending || focusPending || oneTwoPending''',
    "Settle one-two retry guard",
)

replace_once(
    tracking,
    '''        betStore.settle(races)
        focusStore.settle(races)

        if (hasPendingTarget()''',
    '''        betStore.settle(races)
        focusStore.settle(races)
        oneTwoStore.settle(races)

        if (hasPendingTarget()''',
    "Settle one-two results",
)

replace_once(
    tracking,
    '''        PredictionHistoryStore(this).settle(races)
        BetStore(this).settle(races)
        FocusPredictionHistoryStore(this).settle(races)

        val race = races.firstOrNull { it.id == raceId } ?: return''',
    '''        PredictionHistoryStore(this).settle(races)
        BetStore(this).settle(races)
        FocusPredictionHistoryStore(this).settle(races)
        OneTwoLockHistoryStore(this).settle(races)

        val race = races.firstOrNull { it.id == raceId } ?: return''',
    "Evaluate one-two settle",
)

anchor = '''        val focusStore = FocusPredictionHistoryStore(this)
        FocusMode.values().forEach { mode ->
            focusStore.captureRace(race, mode, BetStrategy.DEFAULT_BUDGET)
        }

        val existing = predictionStore.load().firstOrNull { it.id == race.id }
'''
replacement = '''        val focusStore = FocusPredictionHistoryStore(this)
        FocusMode.values().forEach { mode ->
            focusStore.captureRace(race, mode, BetStrategy.DEFAULT_BUDGET)
        }

        OneTwoLockStrategy.selection(race)?.takeIf { it.eligible }?.let { selection ->
            val oneTwoStore = OneTwoLockHistoryStore(this)
            oneTwoStore.captureRace(race, selection)
            runCatching {
                repository.loadOfficialTrifectaOddsDetailed(race, selection.combinations)
            }.onSuccess { oddsResult ->
                oneTwoStore.updateOdds(race.id, OneTwoLockStrategy.quote(selection, oddsResult))
            }
        }

        val existing = predictionStore.load().firstOrNull { it.id == race.id }
'''
replace_once(tracking, anchor, replacement, "Evaluate one-two capture and odds")


# --- Version ---------------------------------------------------------------
build = Path("app/build.gradle.kts")
replace_once(build, 'versionCode = 45\n        versionName = "0.17.0"', 'versionCode = 46\n        versionName = "0.18.0"', "Version bump")
replace_once(
    build,
    '// v0.17.0: Add Focus 4/5 grouped Model A predictions with separate pre-close performance tracking.',
    '// v0.18.0: Add ultra-selective 1→2 90% candidate mode, 3.1x odds gate and realized calibration tracking.',
    "Version comment",
)
