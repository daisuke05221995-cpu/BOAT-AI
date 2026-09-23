package jp.boatai.app

import android.annotation.SuppressLint
import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

/**
 * Android 15/16ではBOOT_COMPLETEDからdataSync foreground serviceを直接開始すると
 * 制限対象になる場合があるため、再起動/更新後はAlarmManagerを経由して復旧する。
 * Alarm発火後は通常のBoatNotificationReceiverが当日レースを再取得・再登録する。
 */
class BoatAlertBootRecoveryReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED && intent.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        val scheduler = NotificationScheduler(context)
        if (!scheduler.enabled) return

        scheduler.scheduleDailyBootstrap()
        scheduleBootstrapSoon(context, scheduler)
    }

    @SuppressLint("ScheduleExactAlarm")
    private fun scheduleBootstrapSoon(context: Context, scheduler: NotificationScheduler) {
        val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
        val intent = Intent(context, BoatNotificationReceiver::class.java).apply {
            action = NotificationScheduler.ACTION_BOOTSTRAP
        }
        val pending = PendingIntent.getBroadcast(
            context,
            BOOTSTRAP_REQUEST_CODE,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val trigger = System.currentTimeMillis() + 60_000L
        when {
            Build.VERSION.SDK_INT >= 23 && scheduler.exactAlarmReady ->
                alarmManager.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, trigger, pending)
            Build.VERSION.SDK_INT >= 23 ->
                alarmManager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, trigger, pending)
            else -> alarmManager.setExact(AlarmManager.RTC_WAKEUP, trigger, pending)
        }
    }

    companion object {
        private const val BOOTSTRAP_REQUEST_CODE = 9_902
    }
}
