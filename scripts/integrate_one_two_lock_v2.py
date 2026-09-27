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


vm = Path("app/src/main/java/jp/boatai/app/BoatViewModel.kt")
patches = [
    (
        '''    val notificationsEnabled: Boolean = false,
    val update: AppUpdateState = AppUpdateState()
)''',
        '''    val notificationsEnabled: Boolean = false,
    val oneTwoQuotes: Map<String, OneTwoLockQuote> = emptyMap(),
    val oneTwoLoading: Boolean = false,
    val oneTwoStats: OneTwoLockSummary = OneTwoLockSummary(),
    val update: AppUpdateState = AppUpdateState()
)''',
        "BoatUiState fields",
    ),
    (
        '''    private val predictionStore = PredictionHistoryStore(application)
    private val modelARecentVirtualRepository = ModelARecentVirtualRepository(application)''',
        '''    private val predictionStore = PredictionHistoryStore(application)
    private val oneTwoStore = OneTwoLockHistoryStore(application)
    private val modelARecentVirtualRepository = ModelARecentVirtualRepository(application)''',
        "ViewModel store",
    ),
    (
        '''    private var oddsRefreshJob: Job? = null
    private var valueRefreshJob: Job? = null''',
        '''    private var oddsRefreshJob: Job? = null
    private var valueRefreshJob: Job? = null
    private var oneTwoRefreshJob: Job? = null''',
        "ViewModel job",
    ),
    (
        '''            predictionHistory = initialPredictionHistory,
            performance = initialPerformance,
            notificationsEnabled = notificationScheduler.enabled''',
        '''            predictionHistory = initialPredictionHistory,
            performance = initialPerformance,
            notificationsEnabled = notificationScheduler.enabled,
            oneTwoStats = oneTwoStore.summary()''',
        "Initial stats",
    ),
    (
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
        "Cancel refresh",
    ),
    (
        '''                    predictions = emptyList(),
                    selectedForBulk = emptySet(),
                    actionMessage = null''',
        '''                    predictions = emptyList(),
                    selectedForBulk = emptySet(),
                    oneTwoQuotes = emptyMap(),
                    oneTwoLoading = false,
                    actionMessage = null''',
        "Clear quotes",
    ),
    (
        '''                    val beforeLearned = _ui.value.learnedRaceCount
                    val records = betStore.settle(races)

                    // Existing resolved value decisions''',
        '''                    val beforeLearned = _ui.value.learnedRaceCount
                    val records = betStore.settle(races)
                    oneTwoStore.settle(races)

                    // Existing resolved value decisions''',
        "Settle on load",
    ),
    (
        '''                            lastUpdatedAt = System.currentTimeMillis(),
                            learnedRaceCount = learning.totalRaceCount
                        )''',
        '''                            lastUpdatedAt = System.currentTimeMillis(),
                            learnedRaceCount = learning.totalRaceCount,
                            oneTwoStats = oneTwoStore.summary()
                        )''',
        "Stats on load",
    ),
    (
        '''                    refreshValueSelections(races)
                }
''',
        '''                    refreshValueSelections(races)
                    refreshOneTwoLocks(races)
                }
''',
        "Refresh quotes",
    ),
]
for old, new, label in patches:
    replace_once(vm, old, new, label)

refresh_method = '''    private fun refreshOneTwoLocks(races: List<RaceData>) {
        oneTwoRefreshJob?.cancel()
        val candidates = races.mapNotNull { race ->
            if (!race.isPurchasable() || !PredictionEngine.isDecisionReady(race)) return@mapNotNull null
            val selection = OneTwoLockStrategy.selection(race) ?: return@mapNotNull null
            if (!selection.eligible) null else race to selection
        }
        val initialQuotes = candidates.associate { (race, selection) -> race.id to OneTwoLockQuote(selection) }
        _ui.update { state -> state.copy(oneTwoQuotes = initialQuotes, oneTwoLoading = candidates.isNotEmpty()) }
        if (candidates.isEmpty()) return

        oneTwoRefreshJob = viewModelScope.launch {
            for ((race, selection) in candidates) {
                if (!race.isPurchasable()) continue
                oneTwoStore.captureRace(race, selection)
                runCatching { repository.loadOfficialTrifectaOddsDetailed(race, selection.combinations) }
                    .onSuccess { result ->
                        val quote = OneTwoLockStrategy.quote(selection, result)
                        oneTwoStore.updateOdds(race.id, quote)
                        _ui.update { state ->
                            state.copy(
                                oneTwoQuotes = state.oneTwoQuotes + (race.id to quote),
                                oneTwoStats = oneTwoStore.summary()
                            )
                        }
                    }
                    .onFailure { error ->
                        val quote = OneTwoLockQuote(selection = selection, error = error.message ?: "公式オッズ取得失敗")
                        _ui.update { state -> state.copy(oneTwoQuotes = state.oneTwoQuotes + (race.id to quote)) }
                    }
            }
            _ui.update { it.copy(oneTwoLoading = false, oneTwoStats = oneTwoStore.summary()) }
        }
    }

'''
text = vm.read_text()
marker = '''    /**
     * Resolve every currently purchasable race whose exhibition data is ready. This is
'''
if refresh_method.strip() not in text:
    if marker not in text:
        raise SystemExit("Refresh method insertion point not found")
    vm.write_text(text.replace(marker, refresh_method + marker, 1))
    print("Refresh method: integrated")

replace_once(
    vm,
    '''                predictionHistory = history,
                performance = performance
            )''',
    '''                predictionHistory = history,
                performance = performance,
                oneTwoStats = oneTwoStore.summary()
            )''',
    "Accounting stats",
)

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
marker = '    fun prepareSelectedPurchase(): Boolean {\n'
if purchase_method.strip() not in text:
    if marker not in text:
        raise SystemExit("Purchase method insertion point not found")
    vm.write_text(text.replace(marker, purchase_method + marker, 1))
    print("Purchase method: integrated")

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
    "Save strategy arg",
)
replace_once(vm, '        val session = PendingPurchaseSession.create(entries)\n', '        val session = PendingPurchaseSession.create(entries, strategyId)\n', "Save strategy id")


main = Path("app/src/main/java/jp/boatai/app/MainActivity.kt")
replace_once(
    main,
    '            listOf("開催一覧", "締切順", "推奨数順").forEachIndexed { index, label ->',
    '            listOf("開催一覧", "締切順", "推奨数順", "1→2鉄板").forEachIndexed { index, label ->',
    "Mode label",
)
replace_once(
    main,
    '''        item { PredictionModeBar(sortMode) { sortMode = it } }
        item { BulkSelectionModeCard(vm) }
''',
    '''        item { PredictionModeBar(sortMode) { sortMode = it } }
        if (sortMode == 3) {
            item { OneTwoLockCandidateList(ui, vm) }
        } else {
            item { BulkSelectionModeCard(vm) }
        }
''',
    "Mode panel",
)
old_grid = '        items(venues.chunked(3), key = { row -> row.joinToString { it.first.toString() } }) { row ->\n'
new_grid = '        if (sortMode != 3) items(venues.chunked(3), key = { row -> row.joinToString { it.first.toString() } }) { row ->\n'
replace_once(main, old_grid, new_grid, "Hide venue grid")
replace_once(
    main,
    '        if (ui.selectedForBulk.isNotEmpty()) item { BulkPurchaseCard(ui, vm) }\n',
    '        if (sortMode != 3 && ui.selectedForBulk.isNotEmpty()) item { BulkPurchaseCard(ui, vm) }\n',
    "Hide bulk card",
)


tracking = Path("app/src/main/java/jp/boatai/app/PredictionTrackingScheduler.kt")
tracking_patches = [
    (
        '''        val betStore = BetStore(this)
        val focusStore = FocusPredictionHistoryStore(this)

        reconcileRecentPending(today, predictionStore, betStore)''',
        '''        val betStore = BetStore(this)
        val focusStore = FocusPredictionHistoryStore(this)
        val oneTwoStore = OneTwoLockHistoryStore(this)

        reconcileRecentPending(today, predictionStore, betStore)''',
        "Bootstrap store",
    ),
    (
        '''            betStore.settle(races)
            focusStore.settle(races)
            PredictionTrackingScheduler(this).scheduleRaces(races)''',
        '''            betStore.settle(races)
            focusStore.settle(races)
            oneTwoStore.settle(races)
            PredictionTrackingScheduler(this).scheduleRaces(races)''',
        "Bootstrap settle",
    ),
    (
        '''        val focusStore = FocusPredictionHistoryStore(this)
        val pendingDateTexts = buildList {''',
        '''        val focusStore = FocusPredictionHistoryStore(this)
        val oneTwoStore = OneTwoLockHistoryStore(this)
        val pendingDateTexts = buildList {''',
        "Recovery store",
    ),
    (
        '''            focusStore.pendingDates().forEach(::add)
        }''',
        '''            focusStore.pendingDates().forEach(::add)
            oneTwoStore.pendingDates().forEach(::add)
        }''',
        "Recovery dates",
    ),
    (
        '''            predictionStore.settle(races)
            betStore.settle(races)
            focusStore.settle(races)
        }
    }

    private suspend fun settleDate''',
        '''            predictionStore.settle(races)
            betStore.settle(races)
            focusStore.settle(races)
            oneTwoStore.settle(races)
        }
    }

    private suspend fun settleDate''',
        "Recovery settle",
    ),
    (
        '''        val betStore = BetStore(this)
        val focusStore = FocusPredictionHistoryStore(this)

        fun hasPendingTarget(): Boolean {''',
        '''        val betStore = BetStore(this)
        val focusStore = FocusPredictionHistoryStore(this)
        val oneTwoStore = OneTwoLockHistoryStore(this)

        fun hasPendingTarget(): Boolean {''',
        "Settle store",
    ),
    (
        '''            val focusPending = FocusMode.values().any { mode ->
                focusStore.load(mode).any { record -> !record.settled && record.id == raceId }
            }
            return predictionPending || purchasePending || focusPending''',
        '''            val focusPending = FocusMode.values().any { mode ->
                focusStore.load(mode).any { record -> !record.settled && record.id == raceId }
            }
            val oneTwoPending = oneTwoStore.hasPending(raceId)
            return predictionPending || purchasePending || focusPending || oneTwoPending''',
        "Retry guard",
    ),
    (
        '''        predictionStore.settle(races)
        betStore.settle(races)
        focusStore.settle(races)

        if (hasPendingTarget()''',
        '''        predictionStore.settle(races)
        betStore.settle(races)
        focusStore.settle(races)
        oneTwoStore.settle(races)

        if (hasPendingTarget()''',
        "Settle result",
    ),
    (
        '''        PredictionHistoryStore(this).settle(races)
        BetStore(this).settle(races)
        FocusPredictionHistoryStore(this).settle(races)

        val race = races.firstOrNull { it.id == raceId } ?: return''',
        '''        PredictionHistoryStore(this).settle(races)
        BetStore(this).settle(races)
        FocusPredictionHistoryStore(this).settle(races)
        OneTwoLockHistoryStore(this).settle(races)

        val race = races.firstOrNull { it.id == raceId } ?: return''',
        "Evaluate settle",
    ),
]
for old, new, label in tracking_patches:
    replace_once(tracking, old, new, label)

replace_once(
    tracking,
    '''        val focusStore = FocusPredictionHistoryStore(this)
        FocusMode.values().forEach { mode ->
            focusStore.captureRace(race, mode, BetStrategy.DEFAULT_BUDGET)
        }

        val existing = predictionStore.load().firstOrNull { it.id == race.id }''',
    '''        val focusStore = FocusPredictionHistoryStore(this)
        FocusMode.values().forEach { mode ->
            focusStore.captureRace(race, mode, BetStrategy.DEFAULT_BUDGET)
        }

        OneTwoLockStrategy.selection(race)?.takeIf { it.eligible }?.let { selection ->
            val oneTwoStore = OneTwoLockHistoryStore(this)
            oneTwoStore.captureRace(race, selection)
            runCatching { repository.loadOfficialTrifectaOddsDetailed(race, selection.combinations) }
                .onSuccess { oddsResult ->
                    oneTwoStore.updateOdds(race.id, OneTwoLockStrategy.quote(selection, oddsResult))
                }
        }

        val existing = predictionStore.load().firstOrNull { it.id == race.id }''',
    "Evaluate capture",
)

build = Path("app/build.gradle.kts")
replace_once(build, 'versionCode = 45\n        versionName = "0.17.0"', 'versionCode = 46\n        versionName = "0.18.0"', "Version")
replace_once(
    build,
    '// v0.17.0: Add Focus 4/5 grouped Model A predictions with separate pre-close performance tracking.',
    '// v0.18.0: Add 1→2 90% candidate mode, 3.1x odds gate and realized calibration tracking.',
    "Version comment",
)
