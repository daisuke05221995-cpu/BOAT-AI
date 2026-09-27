from pathlib import Path

VM = Path('app/src/main/java/jp/boatai/app/BoatViewModel.kt')
ACTIVITY = Path('app/src/main/java/jp/boatai/app/MainActivity.kt')

vm_text = VM.read_text(encoding='utf-8')
old_vm = '''    fun setTab(tab: Int) {
        _ui.update {
            it.copy(
                tab = tab.coerceIn(0, 3),
                selectedRace = null,
                selectedVenue = null,
                predictions = emptyList(),
                actionMessage = null
            )
        }
    }
'''
new_vm = '''    /**
     * Background tracking can settle races while this ViewModel stays alive. Reload the
     * durable stores before showing accounting-oriented screens so cumulative money never
     * depends on recreating the Activity or manually refreshing the race list.
     */
    fun syncStoredAccounting() {
        val records = betStore.load()
        val history = predictionStore.load()
        val performance = PredictionPerformanceProfile.from(history)
        PredictionEngine.restoreValueSelections(history)
        PredictionEngine.installPerformanceProfile(performance)
        _ui.update {
            it.copy(
                records = records,
                pendingPurchase = pendingPurchaseStore.load(),
                predictionHistory = history,
                performance = performance
            )
        }
    }

    fun setTab(tab: Int) {
        val nextTab = tab.coerceIn(0, 3)
        if (nextTab != 0) syncStoredAccounting()
        _ui.update {
            it.copy(
                tab = nextTab,
                selectedRace = null,
                selectedVenue = null,
                predictions = emptyList(),
                actionMessage = null
            )
        }
    }
'''
if old_vm not in vm_text:
    raise SystemExit('BoatViewModel setTab anchor not found; refusing unsafe patch')
VM.write_text(vm_text.replace(old_vm, new_vm, 1), encoding='utf-8')

activity_text = ACTIVITY.read_text(encoding='utf-8')
old_activity = '''    override fun onResume() {
        super.onResume()
        vm.resumePendingInstall(this)
    }
'''
new_activity = '''    override fun onResume() {
        super.onResume()
        // PredictionTrackingService may have settled purchases while the UI process stayed
        // alive. Pull durable accounting back into the ViewModel before the user sees Profit.
        vm.syncStoredAccounting()
        runCatching {
            PredictionTrackingScheduler(this).scheduleBootstrapSoon(2_000L)
        }.onFailure { CrashRecoveryStore(this).recordNonFatal("MainActivity.resumeTrackingBootstrap", it) }
        vm.resumePendingInstall(this)
    }
'''
if old_activity not in activity_text:
    raise SystemExit('MainActivity onResume anchor not found; refusing unsafe patch')
ACTIVITY.write_text(activity_text.replace(old_activity, new_activity, 1), encoding='utf-8')

print('Patched accounting refresh on tab entry and Activity resume.')
