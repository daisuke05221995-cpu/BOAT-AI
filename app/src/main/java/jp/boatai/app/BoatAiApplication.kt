package jp.boatai.app

import android.app.Application
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId

class BoatAiApplication : Application() {
    private val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onCreate() {
        super.onCreate()
        CrashRecoveryStore(this).installHandler()
        ModelAProduction.install(this)
        applicationScope.launch { catchUpModelAHistory() }
    }

    /**
     * Keep Model A history complete through yesterday. A failed/incomplete day stops
     * advancement; forecast then safely falls back to the v0.15.16 pure-AI formula.
     */
    private suspend fun catchUpModelAHistory() {
        val target = LocalDate.now(ZoneId.of("Asia/Tokyo")).minusDays(1)
        var current = ModelAProduction.historyLastDate()?.plusDays(1) ?: return
        if (current.isAfter(target)) return
        val repository = BoatRaceRepository()
        while (!current.isAfter(target)) {
            val day = current
            val success = runCatching {
                val races = repository.loadDateDetailed(day).races
                ModelAProduction.commitFetchedDay(day, races)
                    ?: error("Model A runtime unavailable")
            }.isSuccess
            if (!success) return
            current = current.plusDays(1)
        }
    }
}
