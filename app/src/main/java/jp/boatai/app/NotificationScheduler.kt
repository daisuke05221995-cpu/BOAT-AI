package jp.boatai.app

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

class NotificationScheduler(private val context: Context) {
    private val prefs = context.getSharedPreferences("boat_ai_settings", Context.MODE_PRIVATE)
    val enabled: Boolean get() = prefs.getBoolean(KEY_ENABLED, false)

    fun setEnabled(value: Boolean) {
        prefs.edit().putBoolean(KEY_ENABLED, value).apply()
        ensureChannel()
    }

    fun scheduleDeadlines(races: List<RaceData>) {
        if (!enabled || !canNotify()) return
        ensureChannel()
        val now = System.currentTimeMillis()
        races.filter { it.isPurchasable() }.forEach { race ->
            val close = closeAt(race) ?: return@forEach
            val trigger = close.atZone(ZoneId.of("Asia/Tokyo")).toInstant().toEpochMilli() - 10 * 60_000
            if (trigger <= now) return@forEach
            val intent = Intent(context, BoatNotificationReceiver::class.java).apply {
                putExtra("title", "${race.venueName} ${race.raceNumber}R 締切10分前")
                putExtra("body", "AI予想と最新オッズを確認してください")
                putExtra("id", race.id.hashCode())
            }
            val pending = PendingIntent.getBroadcast(
                context, race.id.hashCode(), intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            (context.getSystemService(Context.ALARM_SERVICE) as AlarmManager)
                .setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, trigger, pending)
        }
    }

    fun notifyNow(title: String, body: String, id: Int) {
        if (!enabled || !canNotify()) return
        ensureChannel()
        NotificationManagerCompat.from(context).notify(id, notification(title, body))
    }

    private fun canNotify(): Boolean = Build.VERSION.SDK_INT < 33 ||
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL, "レース・更新通知", NotificationManager.IMPORTANCE_DEFAULT)
            )
        }
    }

    private fun notification(title: String, body: String) = NotificationCompat.Builder(context, CHANNEL)
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
        const val CHANNEL = "boat_ai_events"
        private const val KEY_ENABLED = "notifications_enabled"
    }
}

class BoatNotificationReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        NotificationScheduler(context).notifyNow(
            intent.getStringExtra("title") ?: "BOAT AI",
            intent.getStringExtra("body") ?: "更新があります",
            intent.getIntExtra("id", 1001)
        )
    }
}
