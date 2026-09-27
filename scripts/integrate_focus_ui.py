from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"{label}: already wired")
        return text
    if old not in text:
        raise SystemExit(f"{label}: insertion point not found")
    print(f"{label}: wired")
    return text.replace(old, new, 1)


# Race-detail UI.
main_path = Path("app/src/main/java/jp/boatai/app/MainActivity.kt")
main = main_path.read_text()
main_old = '''        item { Text("出走データ", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium) }
        items(race.racers, key = { it.lane }) { racer -> RacerCard(racer) }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
'''
main_new = '''        item { Text("出走データ", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium) }
        items(race.racers, key = { it.lane }) { racer -> RacerCard(racer) }

        item {
            FocusPredictionCard(
                race = race,
                raceBudget = ui.raceBudget,
                purchased = ui.records.any {
                    it.date == race.date && it.stadiumNumber == race.stadiumNumber && it.raceNumber == race.raceNumber
                },
                pendingPurchaseExists = ui.pendingPurchase != null
            )
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
'''
main = replace_once(main, main_old, main_new, "Race detail Focus card")
main_path.write_text(main)

# Background ledger capture/settlement. Keep this separate from PredictionHistoryStore so
# focus experiments cannot enter the audited value-v1 ledger.
tracking_path = Path("app/src/main/java/jp/boatai/app/PredictionTrackingScheduler.kt")
tracking = tracking_path.read_text()

bootstrap_old = '''        val predictionStore = PredictionHistoryStore(this)
        val betStore = BetStore(this)

        reconcileRecentPending(today, predictionStore, betStore)
'''
bootstrap_new = '''        val predictionStore = PredictionHistoryStore(this)
        val betStore = BetStore(this)
        val focusStore = FocusPredictionHistoryStore(this)

        reconcileRecentPending(today, predictionStore, betStore)
'''
tracking = replace_once(tracking, bootstrap_old, bootstrap_new, "Bootstrap focus store")

bootstrap_settle_old = '''        if (races != null) {
            predictionStore.settle(races)
            betStore.settle(races)
            PredictionTrackingScheduler(this).scheduleRaces(races)
        }
'''
bootstrap_settle_new = '''        if (races != null) {
            predictionStore.settle(races)
            betStore.settle(races)
            focusStore.settle(races)
            PredictionTrackingScheduler(this).scheduleRaces(races)
        }
'''
tracking = replace_once(tracking, bootstrap_settle_old, bootstrap_settle_new, "Bootstrap focus settle")

reconcile_start_old = '''    ) {
        val pendingDateTexts = buildList {
            predictionStore.load()
'''
reconcile_start_new = '''    ) {
        val focusStore = FocusPredictionHistoryStore(this)
        val pendingDateTexts = buildList {
            predictionStore.load()
'''
tracking = replace_once(tracking, reconcile_start_old, reconcile_start_new, "Recovery focus store")

reconcile_dates_old = '''            betStore.load()
                .asSequence()
                .filter { !it.settled }
                .map { it.date }
                .forEach(::add)
        }
'''
reconcile_dates_new = '''            betStore.load()
                .asSequence()
                .filter { !it.settled }
                .map { it.date }
                .forEach(::add)
            focusStore.pendingDates().forEach(::add)
        }
'''
tracking = replace_once(tracking, reconcile_dates_old, reconcile_dates_new, "Recovery focus pending dates")

reconcile_settle_old = '''            predictionStore.settle(races)
            betStore.settle(races)
        }
    }
'''
reconcile_settle_new = '''            predictionStore.settle(races)
            betStore.settle(races)
            focusStore.settle(races)
        }
    }
'''
tracking = replace_once(tracking, reconcile_settle_old, reconcile_settle_new, "Recovery focus settle")

settle_store_old = '''        val predictionStore = PredictionHistoryStore(this)
        val betStore = BetStore(this)

        fun hasPendingTarget(): Boolean {
'''
settle_store_new = '''        val predictionStore = PredictionHistoryStore(this)
        val betStore = BetStore(this)
        val focusStore = FocusPredictionHistoryStore(this)

        fun hasPendingTarget(): Boolean {
'''
tracking = replace_once(tracking, settle_store_old, settle_store_new, "Settle focus store")

settle_pending_old = '''            val purchasePending = betStore.load().any { bet ->
                !bet.settled &&
                    "${bet.date.take(10)}-${Venues.code(bet.stadiumNumber)}-${bet.raceNumber}" == raceId
            }
            return predictionPending || purchasePending
'''
settle_pending_new = '''            val purchasePending = betStore.load().any { bet ->
                !bet.settled &&
                    "${bet.date.take(10)}-${Venues.code(bet.stadiumNumber)}-${bet.raceNumber}" == raceId
            }
            val focusPending = FocusMode.values().any { mode ->
                focusStore.load(mode).any { record -> !record.settled && record.id == raceId }
            }
            return predictionPending || purchasePending || focusPending
'''
tracking = replace_once(tracking, settle_pending_old, settle_pending_new, "Settle focus retry guard")

settle_apply_old = '''        predictionStore.settle(races)
        betStore.settle(races)

        if (hasPendingTarget() && !raceId.isNullOrBlank()) {
'''
settle_apply_new = '''        predictionStore.settle(races)
        betStore.settle(races)
        focusStore.settle(races)

        if (hasPendingTarget() && !raceId.isNullOrBlank()) {
'''
tracking = replace_once(tracking, settle_apply_old, settle_apply_new, "Settle focus results")

evaluate_initial_settle_old = '''        PredictionHistoryStore(this).settle(races)
        BetStore(this).settle(races)

        val race = races.firstOrNull { it.id == raceId } ?: return
'''
evaluate_initial_settle_new = '''        PredictionHistoryStore(this).settle(races)
        BetStore(this).settle(races)
        FocusPredictionHistoryStore(this).settle(races)

        val race = races.firstOrNull { it.id == raceId } ?: return
'''
tracking = replace_once(tracking, evaluate_initial_settle_old, evaluate_initial_settle_new, "Evaluate focus settle")

# Move the existing-ledger early-return after Model A/profile installation, then freeze both
# focus strategies before existing value-v1 handling can return.
evaluate_block_old = '''        val predictionStore = PredictionHistoryStore(this)
        val existing = predictionStore.load().firstOrNull { it.id == race.id }
        if (existing?.strategyId == "value-v1" || existing?.strategyId == "legacy-final-v1") return

        val learning = LearningStore(this).load()
        val history = predictionStore.load()
        PredictionEngine.installLearningProfile(learning)
        PredictionEngine.installPersistentPerformanceProfile(PerformanceMemoryStore(this).load())
        PredictionEngine.installPerformanceProfile(PredictionPerformanceProfile.from(history))
        PredictionEngine.installValueStrategyModel(ValueStrategyModel.load(this))
        PredictionEngine.restoreValueSelections(history)

        val basePicks = PredictionEngine.predict(race, maxPicks = 4)
'''
evaluate_block_new = '''        val predictionStore = PredictionHistoryStore(this)
        val learning = LearningStore(this).load()
        val history = predictionStore.load()
        PredictionEngine.installLearningProfile(learning)
        PredictionEngine.installPersistentPerformanceProfile(PerformanceMemoryStore(this).load())
        PredictionEngine.installPerformanceProfile(PredictionPerformanceProfile.from(history))
        PredictionEngine.installValueStrategyModel(ValueStrategyModel.load(this))
        PredictionEngine.restoreValueSelections(history)

        val focusStore = FocusPredictionHistoryStore(this)
        FocusMode.values().forEach { mode ->
            focusStore.captureRace(race, mode, BetStrategy.DEFAULT_BUDGET)
        }

        val existing = predictionStore.load().firstOrNull { it.id == race.id }
        if (existing?.strategyId == "value-v1" || existing?.strategyId == "legacy-final-v1") return

        val basePicks = PredictionEngine.predict(race, maxPicks = 4)
'''
tracking = replace_once(tracking, evaluate_block_old, evaluate_block_new, "Evaluate focus capture")

tracking_path.write_text(tracking)
