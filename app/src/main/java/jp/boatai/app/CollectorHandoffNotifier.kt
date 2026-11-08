package jp.boatai.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

/**
 * Local-only receipt alert for a NEW 1st-phone -> 2nd-phone handoff.
 * A handoff is proposed tickets, not a purchased/accepted wager.
 * Never triggers official-app actions or remote purchases.
 */
internal object CollectorHandoffNoticePolicy {
    fun shouldNotify(
        enabled: Boolean,
        handoffId: String,
        expiresAtMs: Long,
        nowMs: Long,
        lastNotifiedId: String?
    ): Boolean = enabled && handoffId.isNotBlank() &&
        expiresAtMs > nowMs && lastNotifiedId != handoffId

    fun summary(raceCount: Int, ticketCount: Int, totalYen: Int): String =
        "${raceCount}レース・${ticketCount}点・合計${totalYen}円。BOAT AIで内容を確認してください"

    // A distinct notification ID for each new transfer; a single fixed ID with
    // setOnlyAlertOnce would silently suppress alerts for later transfers.
    fun notificationId(handoffId: String): Int = 20_000 + (handoffId.hashCode() and 0x0fffffff)
}

/** Independent from prediction alerts: collector receiving notifications default to ON. */
internal class CollectorHandoffNotifier(context: Context) {
    private val appContext = context.applicationContext
    private val preferences = appContext.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)

    val enabled: Boolean get() = preferences.getBoolean(KEY_ENABLED, true)

    fun setEnabled(value: Boolean) {
        preferences.edit().putBoolean(KEY_ENABLED, value).apply()
    }

    fun canPost(): Boolean =
        (Build.VERSION.SDK_INT < 33 || ContextCompat.checkSelfPermission(
            appContext, Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED) &&
            NotificationManagerCompat.from(appContext).areNotificationsEnabled()

    /**
     * Only invoked after the handoff is validated and stored on the collector device.
     * Records the handoff ID only after successful posting to suppress duplicates
     * during retries, foreground refreshes and app restarts.
     */
    @SuppressLint("MissingPermission")
    fun notifyReceived(handoff: CollectorPurchaseHandoff): Boolean {
        val now = System.currentTimeMillis()
        if (!CollectorHandoffNoticePolicy.shouldNotify(
                enabled, handoff.handoffId, handoff.expiresAt, now,
                preferences.getString(KEY_LAST_NOTIFIED_ID, null)
            ) || !canPost()) return false

        if (Build.VERSION.SDK_INT >= 26) {
            val manager = appContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "1台目からの買い目受信", NotificationManager.IMPORTANCE_HIGH).apply {
                    description = "2台目が1台目から新しい買い目を受信した際に通知します"
                    // Independent of the silent prediction-alert channels.
                    enableVibration(true)
                    lockscreenVisibility = android.app.Notification.VISIBILITY_PRIVATE
                }
            )
        }

        val openApp = Intent(appContext, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        }
        val notificationId = CollectorHandoffNoticePolicy.notificationId(handoff.handoffId)
        val openPending = PendingIntent.getActivity(
            appContext, notificationId, openApp,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val session = handoff.session
        val message = CollectorHandoffNoticePolicy.summary(
            session.selectedRaces.size, session.selectedTicketCount, session.selectedStake
        )
        val notification = NotificationCompat.Builder(appContext, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_email)
            .setContentTitle("BOAT AI：1台目から買い目を受信")
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setVisibility(NotificationCompat.VISIBILITY_PRIVATE)
            .setOnlyAlertOnce(true)
            .setAutoCancel(true)
            .setContentIntent(openPending)
            .build()

        NotificationManagerCompat.from(appContext).notify(notificationId, notification)
        preferences.edit().putString(KEY_LAST_NOTIFIED_ID, handoff.handoffId).apply()
        return true
    }

    private companion object {
        const val CHANNEL_ID = "boat_ai_collector_handoff_v1"
        const val PREF_NAME = "boat_ai_collector_handoff_notifications_v1"
        const val KEY_ENABLED = "enabled"
        const val KEY_LAST_NOTIFIED_ID = "last_notified_handoff_id"
    }
}
