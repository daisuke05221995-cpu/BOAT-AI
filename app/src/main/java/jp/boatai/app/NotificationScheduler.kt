package jp.boatai.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
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

class NotificationScheduler(private val context: Context) {
    private val prefs = context.getSharedPreferences("boat_ai_settings", Context.MODE_PRIVATE)
    private val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager

    val enabled: Boolean get() = prefs.getBoolean(KEY_ENABLED, false)
    val exactAlarmReady: Boolean
        get() = Build.VERSION.SDK_INT < 31 || alarmManager.canScheduleExactAlarms()

    fun setEnabled(value: Boolean) {
        prefs.edit().putBoolean(KEY_ENABLED, value).apply()
        ensureChannels()
        if (value) scheduleDailyBootstrap() else cancelDailyBootstrap()
    }

    fun requestExactAlarmPermissionIntent(): Intent? {
        if (Build.VERSION.SDK_INT < 31 || exactAlarmReady) return null
        return Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM).apply {
            data = Uri.parse("package:${context.packageName}")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
    }

    fun scheduleDeadlines(races: List<RaceData>) {
        if (!enabled || !canNotify()) return
        ensureChannels()
        scheduleDailyBootstrap()
        val now = System.currentTimeMillis()
        races.forEach { race ->
            val close = closeAt(race) ?: return@forEach
            if (race.hasResult) return@forEach
            val closeMillis = close.atZone(TOKYO).toInstant().toEpochMilli()

            val evaluateTrigger = closeMillis - ALERT_LEAD_MINUTES * 60_000L
            if (evaluateTrigger > now) {
                val evaluateIntent = Intent(context, BoatNotificationReceiver::class.java).apply {
                    action = ACTION_EVALUATE
                    putExtra(EXTRA_RACE_ID, race.id)
                    putExtra(EXTRA_DATE, race.date.take(10))
                }
                val evaluatePending = PendingIntent.getBroadcast(
                    context,
                    race.id.hashCode(),
                    evaluateIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
                scheduleAlarm(evaluateTrigger, evaluatePending)
            }

            val settleTrigger = closeMillis + SETTLE_DELAY_MINUTES * 60_000L
            if (settleTrigger > now) {
                val settleIntent = Intent(context, BoatNotificationReceiver::class.java).apply {
                    action = ACTION_SETTLE
                    putExtra(EXTRA_RACE_ID, race.id)
                    putExtra(EXTRA_DATE, race.date.take(10))
                }
                val settlePending = PendingIntent.getBroadcast(
                    context,
                    race.id.hashCode() xor SETTLE_REQUEST_XOR,
                    settleIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
                scheduleAlarm(settleTrigger, settlePending)
            }
        }
    }

    fun scheduleDailyBootstrap() {
        if (!enabled) return
        val now = LocalDateTime.now(TOKYO)
        var next = LocalDateTime.of(now.toLocalDate(), LocalTime.of(6, 30))
        if (!next.isAfter(now)) next = next.plusDays(1)
        val trigger = next.atZone(TOKYO).toInstant().toEpochMilli()
        val intent = Intent(context, BoatNotificationReceiver::class.java).apply {
            action = ACTION_BOOTSTRAP
        }
        val pending = PendingIntent.getBroadcast(
            context,
            DAILY_REQUEST_CODE,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        scheduleAlarm(trigger, pending)
    }

    private fun cancelDailyBootstrap() {
        val pending = PendingIntent.getBroadcast(
            context,
            DAILY_REQUEST_CODE,
            Intent(context, BoatNotificationReceiver::class.java).apply { action = ACTION_BOOTSTRAP },
            PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE
        ) ?: return
        alarmManager.cancel(pending)
        pending.cancel()
    }

    @SuppressLint("ScheduleExactAlarm")
    private fun scheduleAlarm(triggerAtMillis: Long, pendingIntent: PendingIntent) {
        if (Build.VERSION.SDK_INT >= 23) {
            if (exactAlarmReady) {
                alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pendingIntent)
            } else {
                alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pendingIntent)
            }
        } else {
            alarmManager.setExact(AlarmManager.RTC_WAKEUP, triggerAtMillis, pendingIntent)
        }
    }

    @SuppressLint("MissingPermission")
    fun notifyNow(title: String, body: String, id: Int) {
        if (!enabled || !canNotify()) return
        ensureChannels()
        NotificationManagerCompat.from(context).notify(id, basicNotification(title, body))
    }

    @SuppressLint("MissingPermission")
    fun notifyPurchaseRecommendation(race: RaceData, picks: List<PredictionPick>, decisionReason: String) {
        if (!enabled || !canNotify() || picks.isEmpty()) return
        ensureChannels()
        val lines = picks.joinToString(" / ") { pick ->
            val odds = pick.odds?.let { String.format("%.1f倍", it) } ?: "--倍"
            "${pick.combination} $odds ${pick.recommendedStake}円"
        }
        val body = "$lines\n$decisionReason"
        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)?.apply {
            putExtra(EXTRA_RACE_ID, race.id)
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        val contentIntent = launch?.let {
            PendingIntent.getActivity(
                context,
                race.id.hashCode(),
                it,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
        }
        val day = race.date.replace("-", "").take(8)
        val officialUrl = "https://www.boatrace.jp/owpc/pc/race/odds3t?hd=$day&jcd=${Venues.code(race.stadiumNumber)}&rno=${race.raceNumber}"
        val officialIntent = PendingIntent.getActivity(
            context,
            race.id.hashCode() xor 0x45A1,
            Intent(Intent.ACTION_VIEW, Uri.parse(officialUrl)),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification = NotificationCompat.Builder(context, ALERT_CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("購入推奨 🚤 ${race.venueName} ${race.raceNumber}R　締切約5分")
            .setContentText(lines)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
            .setDefaults(0)
            .setVibrate(longArrayOf(0L))
            .setSilent(true)
            .setAutoCancel(true)
            .setContentIntent(contentIntent)
            .addAction(0, "公式オッズ", officialIntent)
            .build()
        NotificationManagerCompat.from(context).notify(ALERT_NOTIFICATION_BASE + race.id.hashCode(), notification)
    }

    fun recordCheck(raceId: String, status: String) {
        prefs.edit()
            .putString(KEY_LAST_CHECK_RACE, raceId)
            .putString(KEY_LAST_CHECK_STATUS, status)
            .putLong(KEY_LAST_CHECK_AT, System.currentTimeMillis())
            .apply()
    }

    private fun canNotify(): Boolean = Build.VERSION.SDK_INT < 33 ||
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    private fun ensureChannels() {
        if (Build.VERSION.SDK_INT < 26) return
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "BOAT AI通知（表示のみ）", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "BOAT AIからの通知を音・振動なしで表示します"
                setSound(null, null)
                enableVibration(false)
            }
        )
        manager.createNotificationChannel(
            NotificationChannel(ALERT_CHANNEL, "購入推奨アラート（表示のみ）", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "締切約5分前に、AI判定と最新公式オッズの両方を通過したレースだけ画面通知します"
                setSound(null, null)
                enableVibration(false)
            }
        )
        manager.createNotificationChannel(
            NotificationChannel(SERVICE_CHANNEL, "購入推奨判定処理（表示のみ）", NotificationManager.IMPORTANCE_LOW).apply {
                setSound(null, null)
                enableVibration(false)
            }
        )
    }

    private fun basicNotification(title: String, body: String) = NotificationCompat.Builder(context, CHANNEL)
        .setSmallIcon(android.R.drawable.ic_dialog_info)
        .setContentTitle(title)
        .setContentText(body)
        .setPriority(NotificationCompat.PRIORITY_DEFAULT)
        .setDefaults(0)
        .setVibrate(longArrayOf(0L))
        .setSilent(true)
        .setAutoCancel(true)
        .build()

    private fun closeAt(race: RaceData): LocalDateTime? {
        val date = runCatching { LocalDate.parse(race.date.take(10)) }.getOrNull() ?: return null
        val match = Regex("""(\d{1,2}):(\d{2})""").findAll(race.closedAt).lastOrNull() ?: return null
        val time = runCatching { LocalTime.of(match.groupValues[1].toInt(), match.groupValues[2].toInt()) }.getOrNull() ?: return null
        return LocalDateTime.of(date, time)
    }

    companion object {
        val TOKYO: ZoneId = ZoneId.of("Asia/Tokyo")
        const val CHANNEL = "boat_ai_events_visual_v3"
        const val ALERT_CHANNEL = "boat_ai_buy_alerts_visual_v3"
        const val SERVICE_CHANNEL = "boat_ai_alert_checks_visual_v3"
        const val ACTION_EVALUATE = "jp.boatai.app.action.EVALUATE_BUY_ALERT"
        const val ACTION_SETTLE = "jp.boatai.app.action.SETTLE_PREDICTION_RESULT"
        const val ACTION_BOOTSTRAP = "jp.boatai.app.action.BOOTSTRAP_ALERTS"
        const val EXTRA_RACE_ID = "alert_race_id"
        const val EXTRA_DATE = "alert_date"
        const val ALERT_LEAD_MINUTES = 5
        const val SETTLE_DELAY_MINUTES = 20
        const val ALERT_NOTIFICATION_BASE = 10_000
        const val SERVICE_NOTIFICATION_ID = 9_901
        private const val SETTLE_REQUEST_XOR = 0x2A51
        private const val DAILY_REQUEST_CODE = 9_900
        private const val KEY_ENABLED = "notifications_enabled"
        private const val KEY_LAST_CHECK_RACE = "alert_last_check_race"
        private const val KEY_LAST_CHECK_STATUS = "alert_last_check_status"
        private const val KEY_LAST_CHECK_AT = "alert_last_check_at"
    }
}

class BoatNotificationReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val scheduler = NotificationScheduler(context)
        if (!scheduler.enabled) return
        when (intent.action) {
            NotificationScheduler.ACTION_EVALUATE,
            NotificationScheduler.ACTION_SETTLE -> {
                val serviceIntent = Intent(context, AlertEvaluationService::class.java).apply {
                    action = intent.action
                    putExtra(NotificationScheduler.EXTRA_RACE_ID, intent.getStringExtra(NotificationScheduler.EXTRA_RACE_ID))
                    putExtra(NotificationScheduler.EXTRA_DATE, intent.getStringExtra(NotificationScheduler.EXTRA_DATE))
                }
                ContextCompat.startForegroundService(context, serviceIntent)
            }
            NotificationScheduler.ACTION_BOOTSTRAP -> {
                ContextCompat.startForegroundService(
                    context,
                    Intent(context, AlertEvaluationService::class.java).apply {
                        action = NotificationScheduler.ACTION_BOOTSTRAP
                    }
                )
            }
        }
    }
}

class BoatAlertBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED && intent.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        val scheduler = NotificationScheduler(context)
        if (!scheduler.enabled) return
        scheduler.scheduleDailyBootstrap()
        ContextCompat.startForegroundService(
            context,
            Intent(context, AlertEvaluationService::class.java).apply {
                action = NotificationScheduler.ACTION_BOOTSTRAP
            }
        )
    }
}

class AlertEvaluationService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startAsForeground()
        scope.launch {
            try {
                when (intent?.action) {
                    NotificationScheduler.ACTION_BOOTSTRAP -> bootstrapToday()
                    NotificationScheduler.ACTION_EVALUATE -> evaluateRace(
                        intent.getStringExtra(NotificationScheduler.EXTRA_DATE),
                        intent.getStringExtra(NotificationScheduler.EXTRA_RACE_ID)
                    )
                    NotificationScheduler.ACTION_SETTLE -> settleDate(
                        intent.getStringExtra(NotificationScheduler.EXTRA_DATE),
                        intent.getStringExtra(NotificationScheduler.EXTRA_RACE_ID)
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
                    NotificationScheduler.SERVICE_CHANNEL,
                    "購入推奨判定処理（表示のみ）",
                    NotificationManager.IMPORTANCE_LOW
                ).apply {
                    setSound(null, null)
                    enableVibration(false)
                }
            )
        }
        val notification = NotificationCompat.Builder(this, NotificationScheduler.SERVICE_CHANNEL)
            .setSmallIcon(android.R.drawable.ic_popup_sync)
            .setContentTitle("BOAT AI")
            .setContentText("予想・結果を確認中")
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setDefaults(0)
            .setVibrate(longArrayOf(0L))
            .setSilent(true)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(
                NotificationScheduler.SERVICE_NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            startForeground(NotificationScheduler.SERVICE_NOTIFICATION_ID, notification)
        }
    }

    private suspend fun bootstrapToday() {
        val scheduler = NotificationScheduler(this)
        if (!scheduler.enabled) return
        val today = LocalDate.now(NotificationScheduler.TOKYO)
        runCatching { BoatRaceRepository().loadDate(today) }
            .onSuccess { races -> scheduler.scheduleDeadlines(races) }
            .onFailure { scheduler.recordCheck("bootstrap-$today", "当日レース登録失敗: ${it.message ?: "不明"}") }
        scheduler.scheduleDailyBootstrap()
    }

    private suspend fun settleDate(dateText: String?, raceId: String?) {
        val scheduler = NotificationScheduler(this)
        if (!scheduler.enabled || dateText.isNullOrBlank()) return
        val date = runCatching { LocalDate.parse(dateText.take(10)) }.getOrNull() ?: return
        val races = runCatching { BoatRaceRepository().loadDate(date) }
            .getOrElse {
                scheduler.recordCheck(raceId ?: "settle-$date", "結果取得失敗: ${it.message ?: "不明"}")
                return
            }
        val before = PredictionHistoryStore(this).load().count { !it.settled && it.date.take(10) == date.toString() }
        val settled = PredictionHistoryStore(this).settle(races)
        val after = settled.count { !it.settled && it.date.take(10) == date.toString() }
        BetStore(this).settle(races)
        scheduler.recordCheck(raceId ?: "settle-$date", "予想結果反映 ${before - after}件")
    }

    private suspend fun evaluateRace(dateText: String?, raceId: String?) {
        val scheduler = NotificationScheduler(this)
        if (!scheduler.enabled || dateText.isNullOrBlank() || raceId.isNullOrBlank()) return
        val date = runCatching { LocalDate.parse(dateText.take(10)) }.getOrNull() ?: return
        val repository = BoatRaceRepository()

        val races = runCatching { repository.loadDate(date) }
            .getOrElse {
                scheduler.recordCheck(raceId, "レース再取得失敗: ${it.message ?: "不明"}")
                return
            }
        PredictionHistoryStore(this).settle(races)
        BetStore(this).settle(races)

        val race = races.firstOrNull { it.id == raceId } ?: run {
            scheduler.recordCheck(raceId, "レースが見つかりません")
            return
        }
        if (!race.isPurchasable() || !PredictionEngine.isDecisionReady(race)) {
            scheduler.recordCheck(raceId, "見送り: 締切済みまたは直前情報不足")
            return
        }

        val learning = LearningStore(this).load()
        val predictionStore = PredictionHistoryStore(this)
        val history = predictionStore.load()
        PredictionEngine.installLearningProfile(learning)
        PredictionEngine.installPersistentPerformanceProfile(PerformanceMemoryStore(this).load())
        PredictionEngine.installPerformanceProfile(PredictionPerformanceProfile.from(history))
        PredictionEngine.installValueStrategyModel(ValueStrategyModel.load(this))
        PredictionEngine.restoreValueSelections(history)

        val basePicks = PredictionEngine.predict(race, maxPicks = 4)
        if (basePicks.isEmpty()) {
            scheduler.recordCheck(raceId, "見送り: 買い目なし")
            return
        }

        if (PredictionEngine.hasValueStrategyModel()) {
            val combinations = PredictionEngine.valueOddsCombinations()
            val oddsResult = runCatching { repository.loadOfficialTrifectaOddsDetailed(race, combinations) }
                .getOrElse {
                    val failed = RecommendationDecision(RaceRecommendation.SKIP, "見送り：公式オッズ取得失敗")
                    predictionStore.upsertEvaluatedRace(race, basePicks, failed, "value-v1")
                    scheduler.recordCheck(raceId, "公式オッズ取得失敗: ${it.message ?: "不明"}")
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
            if (!decision.recommended) {
                scheduler.recordCheck(raceId, "見送り: ${decision.reason}")
                return
            }
            scheduler.notifyPurchaseRecommendation(race, picks, decision.reason)
            scheduler.recordCheck(raceId, "購入推奨通知済み")
            return
        }

        val baseDecision = PredictionEngine.recommendation(race)
        if (!baseDecision.recommended) {
            predictionStore.upsertEvaluatedRace(race, basePicks, baseDecision, "legacy-final-v1")
            scheduler.recordCheck(raceId, "見送り: ${baseDecision.reason}")
            return
        }

        val oddsResult = runCatching {
            repository.loadOfficialTrifectaOddsDetailed(race, basePicks.map { it.combination })
        }.getOrElse {
            val failed = RecommendationDecision(RaceRecommendation.SKIP, "見送り：公式オッズ取得失敗")
            predictionStore.upsertEvaluatedRace(race, basePicks, failed, "legacy-final-v1")
            scheduler.recordCheck(raceId, "公式オッズ取得失敗: ${it.message ?: "不明"}")
            return
        }
        val picks = PredictionEngine.withOdds(
            race,
            basePicks,
            oddsResult.odds,
            BetStrategy.DEFAULT_BUDGET,
            learning
        )
        val oddsDecision = BetStrategy.oddsDecision(picks)
        val finalDecision = if (BetStrategy.oddsRecommended(picks)) {
            RecommendationDecision(RaceRecommendation.BUY, "$oddsDecision / ${baseDecision.reason}")
        } else {
            RecommendationDecision(RaceRecommendation.SKIP, oddsDecision)
        }
        predictionStore.upsertEvaluatedRace(race, picks.ifEmpty { basePicks }, finalDecision, "legacy-final-v1")
        if (!finalDecision.recommended) {
            scheduler.recordCheck(raceId, "見送り: ${finalDecision.reason}")
            return
        }
        scheduler.notifyPurchaseRecommendation(race, picks, finalDecision.reason)
        scheduler.recordCheck(raceId, "購入推奨通知済み")
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
