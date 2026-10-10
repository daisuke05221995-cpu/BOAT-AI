package jp.boatai.app

import android.content.Context

class PurchaseAssistSettings(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    val autoPrepareEnabled: Boolean
        get() = prefs.getBoolean(KEY_AUTO_PREPARE, false)

    fun setAutoPrepareEnabled(value: Boolean) {
        prefs.edit().putBoolean(KEY_AUTO_PREPARE, value).apply()
    }

    companion object {
        private const val PREFS = "boat_ai_purchase_assist"
        private const val KEY_AUTO_PREPARE = "auto_prepare_enabled"
    }
}

object PurchaseAssistCoordinator {
    fun prepareIfEnabled(
        context: Context,
        race: RaceData,
        picks: List<PredictionPick>,
        strategyId: String
    ): PendingPurchaseSession? {
        if (!PurchaseAssistSettings(context).autoPrepareEnabled || picks.isEmpty()) return null

        val incoming = PendingPurchaseSession.create(listOf(race to picks), strategyId) ?: return null
        val store = PendingPurchaseStore(context)
        val existing = store.load()
        val merged = mergePendingSessions(existing, incoming)
        if (existing == merged) return existing
        return store.save(merged)
    }
}


internal fun mergePendingSessions(
    existing: PendingPurchaseSession?,
    incoming: PendingPurchaseSession
): PendingPurchaseSession {
    if (existing == null) return incoming
    val missing = incoming.races.filter { newRace ->
        existing.races.none { it.raceId == newRace.raceId }
    }
    if (missing.isEmpty()) return existing
    return existing.copy(
        races = existing.races + missing,
        selectedRaceIds = existing.selectedRaceIds + missing.map { it.raceId }
    )
}
