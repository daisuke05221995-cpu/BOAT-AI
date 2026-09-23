package jp.boatai.app

import android.app.AlarmManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

/**
 * Android 12+ の「アラームとリマインダー」が許可された直後に、
 * 事前予想トラッカーと購入推奨アラートを現在時点から再構築する。
 */
class ExactAlarmPermissionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (Build.VERSION.SDK_INT < 31) return
        if (intent.action != AlarmManager.ACTION_SCHEDULE_EXACT_ALARM_PERMISSION_STATE_CHANGED) return

        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        if (!alarmManager.canScheduleExactAlarms()) return

        PredictionTrackingScheduler(context).apply {
            scheduleDailyBootstrap()
            scheduleBootstrapSoon(1_000L)
        }

        val notificationScheduler = NotificationScheduler(context)
        if (notificationScheduler.enabled) {
            runCatching { notificationScheduler.scheduleDailyBootstrap() }
                .onFailure { CrashRecoveryStore(context).recordNonFatal("ExactAlarmPermissionReceiver", it) }
        }
    }
}
