package jp.boatai.app

import android.annotation.SuppressLint
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

/**
 * 全レースの「締切前に実際に出した予想」を端末へ残すための常時トラッカー。
 * 購入推奨通知のON/OFFとは独立して動き、結果画面と損益集計の母数を欠落させない。
 */
class PredictionTrackingScheduler(private val context: Context) {
    private val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager

    private val exactAlarmReady: Boolean
        get() = Build.VERSION.SDK_INT < 31 || alarmManager.canScheduleExactAlarms()

    fun scheduleDailyBootstrap() {
        val now = LocalDateTime.now(TOKYO)
        var next = LocalDateTime.of(now.toLocalDate(), LocalTime.of(6, 25))
        if (!next.isAfter(now)) next = next.plusDays(1)
        schedule(
            next.atZone(TOKYO).toInstant().toEpochMilli(),
            DAILY_REQUEST_CODE,
            ACTION_BOOTSTRAP
        )
    }

    fun scheduleBootstrapSoon(delayMillis: Long = 10_000L) {
        schedule(System.currentTimeMillis() + delayMillis, BOOTSTRAP_SOON_REQUEST_CODE, ACTION_BOOTSTRAP)
    }

    fun scheduleRaces(races: List<RaceData>) {
        val now = System.currentTimeMillis()
        races.forEach { race ->
            if (race.hasResult) return@forEach
            val close = closeAt(race) ?: return@forEach
            val closeMillis = close.atZone(TOKYO).toInstant().toEpochMilli()

            // BUY通知の5分前判定より少し後に動かす。既存アラート側が先に最終予想を
            // 保存できていれば再取得を避け、アラートOFFならこちらが保存する。
            val normalEvaluate = closeMillis - ALERT_LEAD_MINUTES * 60_000L + TRACKING_DELAY_MS
            val evaluateAt = when {
                normalEvaluate > now -> normalEvaluate
                closeMillis - now > 30_000L -> now + 5_000L
                else -> null
            }
            if (evaluateAt != null) {
                schedule(
                    evaluateAt,
                    race.id.hashCode() xor EVALUATE_REQUEST_XOR,
                    ACTION_EVALUATE,
                    race
                )
            }

            val settleAt = closeMillis + SETTLE_DELAY_MINUTES * 60_000L
            if (settleAt > now) {
                schedule(
                    settleAt,
                    race.id.hashCode() xor SETTLE_REQUEST_XOR,
                    ACTION_SETTLE,
                    race
                )
            }
        }
    }

    fun scheduleSettleRetry(dateText: String, raceId: String, currentAttempt: Int) {
        if (!SettlementRetryPolicy.shouldRetry(currentAttempt, true)) return
        val nextAttempt = SettlementRetryPolicy.nextAttempt(currentAttempt)
        schedule(
            System.currentTimeMillis() + SettlementRetryPolicy.RETRY_DELAY_MINUTES * 60_000L,
            raceId.hashCode() xor SETTLE_RETRY_REQUEST_XOR xor nextAttempt,
            ACTION_SETTLE,
            dateText = dateText.take(10),
            raceId = raceId,
            settleAttempt = nextAttempt
        )
    }

    @SuppressLint("ScheduleExactAlarm")
    private fun schedule(
        triggerAtMillis: Long,
        requestCode: Int,
        action: String,
        race: RaceData? = null,
        dateText: String? = null,
        raceId: String? = null,
        settleAttempt: Int = 0
    ) {
        val intent = Intent(context, PredictionTrackingReceiver::class.java).apply {
            this.action = action
            race?.let {
                putExtra(EXTRA_RACE_ID, it.id)
                putExtra(EXTRA_DATE, it.date.take(10))
            }
            dateText?.takeIf { it.isNotBlank() }?.let { putExtra(EXTRA_DATE, it.take(10)) }
            raceId?.takeIf { it.isNotBlank() }?.let { putExtra(EXTRA_RACE_ID, it) }
            if (action == ACTION_SETTLE) putExtra(EXTRA_SETTLE_ATTEMPT, settleAttempt)
        }
        val pending = PendingIntent.getBroadcast(
            context,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        runCatching {
            when {
                Build.VERSION.SDK_INT >= 23 && exactAlarmReady ->
                    alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
                Build.VERSION.SDK_INT >= 23 ->
                    alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
                else -> alarmManager.setExact(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
            }
        }.onFailure { CrashRecoveryStore(context).recordNonFatal("PredictionTrackingScheduler.schedule.$action", it) }
    }

    private fun closeAt(race: RaceData): LocalDateTime? {
        val date = runCatching { LocalDate.parse(race.date.take(10)) }.getOrNull() ?: return null
        val match = Regex("""(\d{1,2}):(\d{2})""").findAll(race.closedAt).lastOrNull() ?: return null
        val time = runCatching {
            LocalTime.of(match.groupValues[1].toInt(), match.groupValues[2].toInt())
        }.getOrNull() ?: return null
        return LocalDateTime.of(date, time)
    }

    companion object {
        val TOKYO: ZoneId = ZoneId.of("Asia/Tokyo")
        const val ACTION_BOOTSTRAP = "jp.boatai.app.action.TRACK_PREDICTION_BOOTSTRAP"
        const val ACTION_EVALUATE = "jp.boatai.app.action.TRACK_PREDICTION_EVALUATE"
        const val ACTION_SETTLE = "jp.boatai.app.action.TRACK_PREDICTION_SETTLE"
        const val EXTRA_RACE_ID = "tracking_race_id"
        const val EXTRA_DATE = "tracking_date"
        const val EXTRA_SETTLE_ATTEMPT = "tracking_settle_attempt"
        const val SERVICE_CHANNEL = "boat_ai_prediction_tracking_visual_only_v4"
        const val SERVICE_NOTIFICATION_ID = 9_911
        private const val ALERT_LEAD_MINUTES = 5
        private const val TRACKING_DELAY_MS = 30_000L
        private const val SETTLE_DELAY_MINUTES = 20
        private const val DAILY_REQUEST_CODE = 9_910
        private const val BOOTSTRAP_SOON_REQUEST_CODE = 9_912
        private const val EVALUATE_REQUEST_XOR = 0x36B1
        private const val SETTLE_REQUEST_XOR = 0x51A7
        private const val SETTLE_RETRY_REQUEST_XOR = 0x6C2D
    }
}

class PredictionTrackingReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val serviceIntent = Intent(context, PredictionTrackingService::class.java).apply {
            action = intent.action
            putExtra(PredictionTrackingScheduler.EXTRA_RACE_ID, intent.getStringExtra(PredictionTrackingScheduler.EXTRA_RACE_ID))
            putExtra(PredictionTrackingScheduler.EXTRA_DATE, intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE))
            putExtra(
                PredictionTrackingScheduler.EXTRA_SETTLE_ATTEMPT,
                intent.getIntExtra(PredictionTrackingScheduler.EXTRA_SETTLE_ATTEMPT, 0)
            )
        }
        runCatching { ContextCompat.startForegroundService(context, serviceIntent) }
            .onFailure { CrashRecoveryStore(context).recordNonFatal("PredictionTrackingReceiver.${intent.action}", it) }
    }
}

class PredictionTrackingBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED && intent.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        runCatching {
            PredictionTrackingScheduler(context).apply {
                scheduleDailyBootstrap()
                scheduleBootstrapSoon(60_000L)
            }
        }.onFailure { CrashRecoveryStore(context).recordNonFatal("PredictionTrackingBootReceiver", it) }
    }
}

class PredictionTrackingService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
            startAsForeground()
        } catch (error: Throwable) {
            CrashRecoveryStore(this).recordNonFatal("PredictionTrackingService.startForeground", error)
            stopSelf(startId)
            return START_NOT_STICKY
        }
        scope.launch {
            try {
                when (intent?.action) {
                    PredictionTrackingScheduler.ACTION_BOOTSTRAP -> bootstrapToday()
                    PredictionTrackingScheduler.ACTION_EVALUATE -> evaluateRace(
                        intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE),
                        intent.getStringExtra(PredictionTrackingScheduler.EXTRA_RACE_ID)
                    )
                    PredictionTrackingScheduler.ACTION_SETTLE -> settleDate(
                        intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE),
                        intent.getStringExtra(PredictionTrackingScheduler.EXTRA_RACE_ID),
                        intent.getIntExtra(PredictionTrackingScheduler.EXTRA_SETTLE_ATTEMPT, 0)
                    )
                }
            } catch (error: Throwable) {
                CrashRecoveryStore(this@PredictionTrackingService).recordNonFatal("PredictionTrackingService.${intent?.action}", error)
            } finally {
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf(startId)
            }
        }
        return START_NOT_STICKY
    }

    private fun startAsForeground() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(
                NotificationChannel(
                    PredictionTrackingScheduler.SERVICE_CHANNEL,
                    "事前予想の自動記録",
                    NotificationManager.IMPORTANCE_LOW
                ).apply {
                    description = "全レースの締切前予想を結果・損益検証用に保存します"
                    setSound(null, null)
                    enableVibration(false)
                }
            )
        }
        val notification = NotificationCompat.Builder(this, PredictionTrackingScheduler.SERVICE_CHANNEL)
            .setSmallIcon(android.R.drawable.ic_popup_sync)
            .setContentTitle("BOAT AI")
            .setContentText("事前予想を記録中")
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setSilent(true)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(
                PredictionTrackingScheduler.SERVICE_NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            startForeground(PredictionTrackingScheduler.SERVICE_NOTIFICATION_ID, notification)
        }
    }

    private suspend fun bootstrapToday() {
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

    private suspend fun settleDate(dateText: String?, raceId: String?, attempt: Int) {
        if (dateText.isNullOrBlank()) return
        val normalizedDate = dateText.take(10)
        val date = runCatching { LocalDate.parse(normalizedDate) }.getOrNull() ?: return
        val predictionStore = PredictionHistoryStore(this)
        val betStore = BetStore(this)

        fun hasPendingTarget(): Boolean {
            if (raceId.isNullOrBlank()) return false
            val predictionPending = predictionStore.load().any { record ->
                !record.settled && record.id == raceId
            }
            val purchasePending = betStore.load().any { bet ->
                !bet.settled &&
                    "${bet.date.take(10)}-${Venues.code(bet.stadiumNumber)}-${bet.raceNumber}" == raceId
            }
            return predictionPending || purchasePending
        }

        val pendingBeforeFetch = hasPendingTarget()
        val races = runCatching { BoatRaceRepository().loadDate(date) }.getOrNull()
        if (races == null) {
            if (pendingBeforeFetch && !raceId.isNullOrBlank()) {
                PredictionTrackingScheduler(this).scheduleSettleRetry(normalizedDate, raceId, attempt)
            }
            return
        }

        predictionStore.settle(races)
        betStore.settle(races)

        if (hasPendingTarget() && !raceId.isNullOrBlank()) {
            PredictionTrackingScheduler(this).scheduleSettleRetry(normalizedDate, raceId, attempt)
        }
    }

    private suspend fun evaluateRace(dateText: String?, raceId: String?) {
        if (dateText.isNullOrBlank() || raceId.isNullOrBlank()) return
        val date = runCatching { LocalDate.parse(dateText.take(10)) }.getOrNull() ?: return
        val repository = BoatRaceRepository()
        val races = runCatching { repository.loadDate(date) }.getOrNull() ?: return

        PredictionHistoryStore(this).settle(races)
        BetStore(this).settle(races)

        val race = races.firstOrNull { it.id == raceId } ?: return
        if (!race.isPurchasable() || !PredictionEngine.isDecisionReady(race)) return

        val predictionStore = PredictionHistoryStore(this)
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
        if (basePicks.isEmpty()) return

        if (PredictionEngine.hasValueStrategyModel()) {
            val oddsResult = runCatching {
                repository.loadOfficialTrifectaOddsDetailed(race, PredictionEngine.valueOddsCombinations())
            }.getOrElse {
                predictionStore.upsertEvaluatedRace(
                    race,
                    basePicks,
                    RecommendationDecision(RaceRecommendation.SKIP, "見送り：公式オッズ取得失敗"),
                    "value-v1"
                )
                return
            }
            PredictionEngine.applyValueOdds(race, oddsResult.odds, learning)
            val decision = PredictionEngine.recommendation(race)
            val picks = PredictionEngine.withOdds(
                race,
                basePicks,
                oddsResult.odds,
                BetStrategy.DEFAULT_BUDGET,
                learning
            ).ifEmpty { basePicks }
            predictionStore.upsertEvaluatedRace(
                race,
                if (decision.recommended) picks else emptyList(),
                decision,
                "value-v1",
                oddsResult = oddsResult
            )
            return
        }

        val baseDecision = PredictionEngine.recommendation(race)
        if (!baseDecision.recommended) {
            predictionStore.upsertEvaluatedRace(race, basePicks, baseDecision, "legacy-final-v1")
            return
        }

        val oddsResult = runCatching {
            repository.loadOfficialTrifectaOddsDetailed(race, basePicks.map { it.combination })
        }.getOrElse {
            predictionStore.upsertEvaluatedRace(
                race,
                basePicks,
                RecommendationDecision(RaceRecommendation.SKIP, "見送り：公式オッズ取得失敗"),
                "legacy-final-v1"
            )
            return
        }
        val picks = PredictionEngine.withOdds(
            race,
            basePicks,
            oddsResult.odds,
            BetStrategy.DEFAULT_BUDGET,
            learning
        )
        val finalDecision = if (BetStrategy.oddsRecommended(picks)) {
            RecommendationDecision(
                RaceRecommendation.BUY,
                "${BetStrategy.oddsDecision(picks)} / ${baseDecision.reason}"
            )
        } else {
            RecommendationDecision(RaceRecommendation.SKIP, BetStrategy.oddsDecision(picks))
        }
        predictionStore.upsertEvaluatedRace(
            race,
            picks.ifEmpty { basePicks },
            finalDecision,
            "legacy-final-v1",
            oddsResult = oddsResult
        )
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
