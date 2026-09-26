from pathlib import Path

path = Path('app/src/main/java/jp/boatai/app/PredictionTrackingScheduler.kt')
text = path.read_text(encoding='utf-8')

anchor = '''    private suspend fun bootstrapToday() {
        val today = LocalDate.now(PredictionTrackingScheduler.TOKYO)
        val races = runCatching { BoatRaceRepository().loadDate(today) }.getOrNull()
        if (races != null) {
            PredictionHistoryStore(this).settle(races)
            BetStore(this).settle(races)
            PredictionTrackingScheduler(this).scheduleRaces(races)
        }
        PredictionTrackingScheduler(this).scheduleDailyBootstrap()
    }
'''
replacement = '''    private suspend fun bootstrapToday() {
        val today = LocalDate.now(PredictionTrackingScheduler.TOKYO)
        val predictionStore = PredictionHistoryStore(this)
        val betStore = BetStore(this)

        reconcileRecentPending(today, predictionStore, betStore)

        val races = runCatching { BoatRaceRepository().loadDate(today) }.getOrNull()
        if (races != null) {
            predictionStore.settle(races)
            betStore.settle(races)
            PredictionTrackingScheduler(this).scheduleRaces(races)
        }
        PredictionTrackingScheduler(this).scheduleDailyBootstrap()
    }

    private suspend fun reconcileRecentPending(
        today: LocalDate,
        predictionStore: PredictionHistoryStore,
        betStore: BetStore
    ) {
        val pendingDateTexts = buildList {
            predictionStore.load()
                .asSequence()
                .filter { !it.settled }
                .map { it.date }
                .forEach(::add)
            betStore.load()
                .asSequence()
                .filter { !it.settled }
                .map { it.date }
                .forEach(::add)
        }
        val dates = SettlementRecoveryPlanner.selectDates(pendingDateTexts, today)
            .filter { it != today }
        if (dates.isEmpty()) return

        val repository = BoatRaceRepository()
        dates.forEach { pendingDate ->
            val races = runCatching { repository.loadDate(pendingDate) }.getOrNull() ?: return@forEach
            predictionStore.settle(races)
            betStore.settle(races)
        }
    }
'''
if anchor not in text:
    raise SystemExit('bootstrapToday anchor not found')
text = text.replace(anchor, replacement, 1)

path.write_text(text, encoding='utf-8')
print('Patched recent pending settlement recovery into bootstrap.')
