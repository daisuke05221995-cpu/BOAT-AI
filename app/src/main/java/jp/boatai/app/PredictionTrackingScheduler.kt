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

    @SuppressLint("ScheduleExactAlarm")
    private fun schedule(
        triggerAtMillis: Long,
        requestCode: Int,
        action: String,
        race: RaceData? = null
    ) {
        val intent = Intent(context, PredictionTrackingReceiver::class.java).apply {
            this.action = action
            race?.let {
                putExtra(EXTRA_RACE_ID, it.id)
                putExtra(EXTRA_DATE, it.date.take(10))
            }
        }
        val pending = PendingIntent.getBroadcast(
            context,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        when {
            Build.VERSION.SDK_INT >= 23 && exactAlarmReady ->
                alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
            Build.VERSION.SDK_INT >= 23 ->
                alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
            else -> alarmManager.setExact(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
        }
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
        const val SERVICE_CHANNEL = "boat_ai_prediction_tracking"
        const val SERVICE_NOTIFICATION_ID = 9_911
        private const val ALERT_LEAD_MINUTES = 5
        private const val TRACKING_DELAY_MS = 30_000L
        private const val SETTLE_DELAY_MINUTES = 20
        private const val DAILY_REQUEST_CODE = 9_910
        private const val BOOTSTRAP_SOON_REQUEST_CODE = 9_912
        private const val EVALUATE_REQUEST_XOR = 0x36B1
        private const val SETTLE_REQUEST_XOR = 0x51A7
    }
}

class PredictionTrackingReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val serviceIntent = Intent(context, PredictionTrackingService::class.java).apply {
            action = intent.action
            putExtra(PredictionTrackingScheduler.EXTRA_RACE_ID, intent.getStringExtra(PredictionTrackingScheduler.EXTRA_RACE_ID))
            putExtra(PredictionTrackingScheduler.EXTRA_DATE, intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE))
        }
        ContextCompat.startForegroundService(context, serviceIntent)
    }
}

class PredictionTrackingBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED && intent.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        PredictionTrackingScheduler(context).apply {
            scheduleDailyBootstrap()
            scheduleBootstrapSoon(60_000L)
        }
    }
}

class PredictionTrackingService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startAsForeground()
        scope.launch {
            try {
                when (intent?.action) {
                    PredictionTrackingScheduler.ACTION_BOOTSTRAP -> bootstrapToday()
                    PredictionTrackingScheduler.ACTION_EVALUATE -> evaluateRace(
                        intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE),
                        intent.getStringExtra(PredictionTrackingScheduler.EXTRA_RACE_ID)
                    )
                    PredictionTrackingScheduler.ACTION_SETTLE -> settleDate(
                        intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE)
                    )
                }
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
        val races = runCatching { BoatRaceRepository().loadDate(today) }.getOrNull()
        if (races != null) {
            PredictionHistoryStore(this).settle(races)
            BetStore(this).settle(races)
            PredictionTrackingScheduler(this).scheduleRaces(races)
        }
        PredictionTrackingScheduler(this).scheduleDailyBootstrap()
    }

    private suspend fun settleDate(dateText: String?) {
        if (dateText.isNullOrBlank()) return
        val date = runCatching { LocalDate.parse(dateText.take(10)) }.getOrNull() ?: return
        val races = runCatching { BoatRaceRepository().loadDate(date) }.getOrNull() ?: return
        PredictionHistoryStore(this).settle(races)
        BetStore(this).settle(races)
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
            predictionStore.upsertEvaluatedRace(race, picks, decision, "value-v1")
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
            "legacy-final-v1"
        )
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
