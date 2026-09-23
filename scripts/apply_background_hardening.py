#!/usr/bin/env python3
from pathlib import Path


def rep(text, old, new, label):
    n=text.count(old)
    if n!=1: raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old,new,1)

# CrashRecoveryStore: add non-fatal background diagnostics without forcing safe mode.
p=Path('app/src/main/java/jp/boatai/app/CrashRecoveryStore.kt')
t=p.read_text()
t=rep(t,
'''    fun clearCrash() {
        prefs.edit().remove(KEY_LAST_CRASH).remove(KEY_LAST_CRASH_AT).commit()
    }

    fun installHandler() {
''',
'''    fun clearCrash() {
        prefs.edit().remove(KEY_LAST_CRASH).remove(KEY_LAST_CRASH_AT).commit()
    }

    fun recordNonFatal(scope: String, throwable: Throwable) {
        runCatching {
            val writer = StringWriter()
            throwable.printStackTrace(PrintWriter(writer))
            val report = buildString {
                appendLine("BOAT AI v${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
                appendLine("time=${System.currentTimeMillis()}")
                appendLine("scope=$scope")
                appendLine("device=${Build.MANUFACTURER} ${Build.MODEL}")
                appendLine("android=${Build.VERSION.RELEASE} sdk=${Build.VERSION.SDK_INT}")
                appendLine()
                append(writer.toString())
            }.take(MAX_CRASH_CHARS)
            prefs.edit()
                .putString(KEY_LAST_BACKGROUND_FAILURE, report)
                .putLong(KEY_LAST_BACKGROUND_FAILURE_AT, System.currentTimeMillis())
                .commit()
        }
    }

    fun lastBackgroundFailure(): String? = prefs.getString(KEY_LAST_BACKGROUND_FAILURE, null)

    fun installHandler() {
''','crash store method')
t=rep(t,
'''        private const val KEY_LAST_CRASH_AT = "last_crash_at"
        private const val MAX_CRASH_CHARS = 16_000
''',
'''        private const val KEY_LAST_CRASH_AT = "last_crash_at"
        private const val KEY_LAST_BACKGROUND_FAILURE = "last_background_failure"
        private const val KEY_LAST_BACKGROUND_FAILURE_AT = "last_background_failure_at"
        private const val MAX_CRASH_CHARS = 16_000
''','crash store constants')
p.write_text(t)

# Notification scheduler / purchase alert service hardening.
p=Path('app/src/main/java/jp/boatai/app/NotificationScheduler.kt')
t=p.read_text()
t=rep(t,
'''    @SuppressLint("ScheduleExactAlarm")
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
''',
'''    @SuppressLint("ScheduleExactAlarm")
    private fun scheduleAlarm(triggerAtMillis: Long, pendingIntent: PendingIntent) {
        runCatching {
            if (Build.VERSION.SDK_INT >= 23) {
                if (exactAlarmReady) {
                    alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pendingIntent)
                } else {
                    alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pendingIntent)
                }
            } else {
                alarmManager.setExact(AlarmManager.RTC_WAKEUP, triggerAtMillis, pendingIntent)
            }
        }.onFailure { CrashRecoveryStore(context).recordNonFatal("NotificationScheduler.scheduleAlarm", it) }
    }
''','notification alarm safe')
t=rep(t,
'''class BoatNotificationReceiver : BroadcastReceiver() {
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
''',
'''class BoatNotificationReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val scheduler = NotificationScheduler(context)
        if (!scheduler.enabled) return
        runCatching {
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
        }.onFailure {
            CrashRecoveryStore(context).recordNonFatal("BoatNotificationReceiver.${intent.action}", it)
            scheduler.recordCheck(intent.getStringExtra(NotificationScheduler.EXTRA_RACE_ID) ?: "receiver", "バックグラウンド起動失敗: ${it.javaClass.simpleName}")
        }
    }
}
''','notification receiver safe')
t=rep(t,
'''class BoatAlertBootReceiver : BroadcastReceiver() {
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
''',
'''class BoatAlertBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED && intent.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        val scheduler = NotificationScheduler(context)
        if (!scheduler.enabled) return
        // Android 15 forbids some dataSync foreground-service starts directly from BOOT_COMPLETED.
        // Rebuild the next Alarm only; the Alarm receiver starts work when its trigger arrives.
        runCatching { scheduler.scheduleDailyBootstrap() }
            .onFailure { CrashRecoveryStore(context).recordNonFatal("BoatAlertBootReceiver", it) }
    }
}
''','boot receiver safe')
t=rep(t,
'''    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
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
''',
'''    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        try {
            startAsForeground()
        } catch (error: Throwable) {
            CrashRecoveryStore(this).recordNonFatal("AlertEvaluationService.startForeground", error)
            stopSelf(startId)
            return START_NOT_STICKY
        }
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
            } catch (error: Throwable) {
                CrashRecoveryStore(this@AlertEvaluationService).recordNonFatal("AlertEvaluationService.${intent?.action}", error)
                runCatching { NotificationScheduler(this@AlertEvaluationService).recordCheck("service", "処理失敗: ${error.javaClass.simpleName}") }
            } finally {
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf(startId)
            }
        }
        return START_NOT_STICKY
    }
''','alert service safe')
p.write_text(t)

# Prediction tracking hardening.
p=Path('app/src/main/java/jp/boatai/app/PredictionTrackingScheduler.kt')
t=p.read_text()
t=rep(t,
'''        when {
            Build.VERSION.SDK_INT >= 23 && exactAlarmReady ->
                alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
            Build.VERSION.SDK_INT >= 23 ->
                alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
            else -> alarmManager.setExact(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
        }
''',
'''        runCatching {
            when {
                Build.VERSION.SDK_INT >= 23 && exactAlarmReady ->
                    alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
                Build.VERSION.SDK_INT >= 23 ->
                    alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
                else -> alarmManager.setExact(AlarmManager.RTC_WAKEUP, triggerAtMillis, pending)
            }
        }.onFailure { CrashRecoveryStore(context).recordNonFatal("PredictionTrackingScheduler.schedule.$action", it) }
''','tracking alarm safe')
t=rep(t,
'''class PredictionTrackingReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val serviceIntent = Intent(context, PredictionTrackingService::class.java).apply {
            action = intent.action
            putExtra(PredictionTrackingScheduler.EXTRA_RACE_ID, intent.getStringExtra(PredictionTrackingScheduler.EXTRA_RACE_ID))
            putExtra(PredictionTrackingScheduler.EXTRA_DATE, intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE))
        }
        ContextCompat.startForegroundService(context, serviceIntent)
    }
}
''',
'''class PredictionTrackingReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val serviceIntent = Intent(context, PredictionTrackingService::class.java).apply {
            action = intent.action
            putExtra(PredictionTrackingScheduler.EXTRA_RACE_ID, intent.getStringExtra(PredictionTrackingScheduler.EXTRA_RACE_ID))
            putExtra(PredictionTrackingScheduler.EXTRA_DATE, intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE))
        }
        runCatching { ContextCompat.startForegroundService(context, serviceIntent) }
            .onFailure { CrashRecoveryStore(context).recordNonFatal("PredictionTrackingReceiver.${intent.action}", it) }
    }
}
''','tracking receiver safe')
t=rep(t,
'''class PredictionTrackingBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED && intent.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        PredictionTrackingScheduler(context).apply {
            scheduleDailyBootstrap()
            scheduleBootstrapSoon(60_000L)
        }
    }
}
''',
'''class PredictionTrackingBootReceiver : BroadcastReceiver() {
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
''','tracking boot safe')
t=rep(t,
'''    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
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
''',
'''    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
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
                        intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE)
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
''','tracking service safe')
p.write_text(t)

# Exact-alarm permission broadcast: never directly launch a dataSync FGS from the broadcast.
p=Path('app/src/main/java/jp/boatai/app/ExactAlarmPermissionReceiver.kt')
t=p.read_text()
t=t.replace('import androidx.core.content.ContextCompat\n','')
t=rep(t,
'''        val notificationScheduler = NotificationScheduler(context)
        if (notificationScheduler.enabled) {
            notificationScheduler.scheduleDailyBootstrap()
            ContextCompat.startForegroundService(
                context,
                Intent(context, AlertEvaluationService::class.java).apply {
                    action = NotificationScheduler.ACTION_BOOTSTRAP
                }
            )
        }
''',
'''        val notificationScheduler = NotificationScheduler(context)
        if (notificationScheduler.enabled) {
            runCatching { notificationScheduler.scheduleDailyBootstrap() }
                .onFailure { CrashRecoveryStore(context).recordNonFatal("ExactAlarmPermissionReceiver", it) }
        }
''','exact alarm no fgs')
p.write_text(t)
print('background hardening patch applied')
