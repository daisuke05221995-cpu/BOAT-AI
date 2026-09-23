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
            val trigger = close.atZone(TOKYO).toInstant().toEpochMilli() - ALERT_LEAD_MINUTES * 60_000L
            if (trigger <= now || race.hasResult) return@forEach
            val intent = Intent(context, BoatNotificationReceiver::class.java).apply {
                action = ACTION_EVALUATE
                putExtra(EXTRA_RACE_ID, race.id)
                putExtra(EXTRA_DATE, race.date.take(10))
            }
            val pending = PendingIntent.getBroadcast(
                context,
                race.id.hashCode(),
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            scheduleAlarm(trigger, pending)
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
            NotificationChannel(CHANNEL, "レース・更新通知", NotificationManager.IMPORTANCE_DEFAULT)
        )
        manager.createNotificationChannel(
            NotificationChannel(ALERT_CHANNEL, "購入推奨アラート", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "締切約5分前に、AI判定と最新公式オッズの両方を通過したレースだけ通知します"
            }
        )
        manager.createNotificationChannel(
            NotificationChannel(SERVICE_CHANNEL, "購入推奨判定処理", NotificationManager.IMPORTANCE_LOW)
        )
    }

    private fun basicNotification(title: String, body: String) = NotificationCompat.Builder(context, CHANNEL)
        .setSmallIcon(android.R.drawable.ic_dialog_info)
        .setContentTitle(title)
        .setContentText(body)
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
        const val CHANNEL = "boat_ai_events"
        const val ALERT_CHANNEL = "boat_ai_buy_alerts"
        const val SERVICE_CHANNEL = "boat_ai_alert_checks"
        const val ACTION_EVALUATE = "jp.boatai.app.action.EVALUATE_BUY_ALERT"
        const val ACTION_BOOTSTRAP = "jp.boatai.app.action.BOOTSTRAP_ALERTS"
        const val EXTRA_RACE_ID = "alert_race_id"
        const val EXTRA_DATE = "alert_date"
        const val ALERT_LEAD_MINUTES = 5
        const val ALERT_NOTIFICATION_BASE = 10_000
        const val SERVICE_NOTIFICATION_ID = 9_901
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
            NotificationScheduler.ACTION_EVALUATE -> {
                val serviceIntent = Intent(context, AlertEvaluationService::class.java).apply {
                    action = NotificationScheduler.ACTION_EVALUATE
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
                    "購入推奨判定処理",
                    NotificationManager.IMPORTANCE_LOW
                )
            )
        }
        val notification = NotificationCompat.Builder(this, NotificationScheduler.SERVICE_CHANNEL)
            .setSmallIcon(android.R.drawable.ic_popup_sync)
            .setContentTitle("BOAT AI")
            .setContentText("購入推奨を確認中")
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
        val race = races.firstOrNull { it.id == raceId } ?: run {
            scheduler.recordCheck(raceId, "レースが見つかりません")
            return
        }
        if (!race.isPurchasable() || !PredictionEngine.isDecisionReady(race)) {
            scheduler.recordCheck(raceId, "見送り: 締切済みまたは直前情報不足")
            return
        }

        val learning = LearningStore(this).load()
        val history = PredictionHistoryStore(this).load()
        PredictionEngine.installLearningProfile(learning)
        PredictionEngine.installPersistentPerformanceProfile(PerformanceMemoryStore(this).load())
        PredictionEngine.installPerformanceProfile(PredictionPerformanceProfile.from(history))
        PredictionEngine.installValueStrategyModel(ValueStrategyModel.load(this))
        PredictionEngine.restoreValueSelections(history)

        if (PredictionEngine.hasValueStrategyModel()) {
            val combinations = PredictionEngine.valueOddsCombinations()
            val oddsResult = runCatching { repository.loadOfficialTrifectaOddsDetailed(race, combinations) }
                .getOrElse {
                    scheduler.recordCheck(raceId, "公式オッズ取得失敗: ${it.message ?: "不明"}")
                    return
                }
            PredictionEngine.applyValueOdds(race, oddsResult.odds, learning)
            val decision = PredictionEngine.recommendation(race)
            if (!decision.recommended) {
                scheduler.recordCheck(raceId, "見送り: ${decision.reason}")
                return
            }
            val picks = PredictionEngine.withOdds(
                race,
                PredictionEngine.predict(race),
                oddsResult.odds,
                BetStrategy.DEFAULT_BUDGET,
                learning
            )
            if (picks.isEmpty()) {
                scheduler.recordCheck(raceId, "見送り: 買い目なし")
                return
            }
            scheduler.notifyPurchaseRecommendation(race, picks, decision.reason)
            scheduler.recordCheck(raceId, "購入推奨通知済み")
            return
        }

        val decision = PredictionEngine.recommendation(race)
        if (!decision.recommended) {
            scheduler.recordCheck(raceId, "見送り: ${decision.reason}")
            return
        }
        val initial = PredictionEngine.predict(race, maxPicks = 4)
        if (initial.isEmpty()) {
            scheduler.recordCheck(raceId, "見送り: 買い目なし")
            return
        }
        val oddsResult = runCatching {
            repository.loadOfficialTrifectaOddsDetailed(race, initial.map { it.combination })
        }.getOrElse {
            scheduler.recordCheck(raceId, "公式オッズ取得失敗: ${it.message ?: "不明"}")
            return
        }
        val picks = PredictionEngine.withOdds(
            race,
            initial,
            oddsResult.odds,
            BetStrategy.DEFAULT_BUDGET,
            learning
        )
        val oddsDecision = BetStrategy.oddsDecision(picks)
        if (!BetStrategy.oddsRecommended(picks)) {
            scheduler.recordCheck(raceId, "見送り: $oddsDecision")
            return
        }
        scheduler.notifyPurchaseRecommendation(race, picks, "$oddsDecision / ${decision.reason}")
        scheduler.recordCheck(raceId, "購入推奨通知済み")
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
