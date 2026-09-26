package jp.boatai.app

import java.util.concurrent.ConcurrentHashMap

/**
 * Short-lived bridge from the official odds fetch layer to prediction persistence.
 * The durable copy lives in PredictionRecord; this registry only carries the most
 * recent successful snapshot until the corresponding pre-race record is written.
 */
internal object LiveOddsAuditRegistry {
    private const val MAX_ENTRIES = 256
    private val snapshots = ConcurrentHashMap<String, OddsFetchResult>()

    fun record(raceId: String, result: OddsFetchResult) {
        if (raceId.isBlank()) return
        snapshots[raceId] = result
        if (snapshots.size > MAX_ENTRIES) {
            snapshots.entries.minByOrNull { it.value.fetchedAt }?.key
                ?.takeIf { it != raceId }
                ?.let(snapshots::remove)
        }
    }

    fun latest(raceId: String): OddsFetchResult? = snapshots[raceId]

    fun clear(raceId: String) {
        snapshots.remove(raceId)
    }

    internal fun clearAllForTest() {
        snapshots.clear()
    }
}
