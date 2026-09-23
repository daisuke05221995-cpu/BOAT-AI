package jp.boatai.app

import android.content.Context
import android.os.Build
import android.os.Process
import java.io.PrintWriter
import java.io.StringWriter

class CrashRecoveryStore(context: Context) {
    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    val normalBootEnabled: Boolean
        get() = prefs.getBoolean(KEY_NORMAL_BOOT, false)

    fun enableNormalBoot() {
        prefs.edit().putBoolean(KEY_NORMAL_BOOT, true).commit()
    }

    fun disableNormalBoot() {
        prefs.edit().putBoolean(KEY_NORMAL_BOOT, false).commit()
    }

    fun lastCrash(): String? = prefs.getString(KEY_LAST_CRASH, null)

    fun clearCrash() {
        prefs.edit().remove(KEY_LAST_CRASH).remove(KEY_LAST_CRASH_AT).commit()
    }

    fun installHandler() {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            runCatching { recordCrash(thread, throwable) }
            if (previous != null) {
                previous.uncaughtException(thread, throwable)
            } else {
                Process.killProcess(Process.myPid())
            }
        }
    }

    private fun recordCrash(thread: Thread, throwable: Throwable) {
        val writer = StringWriter()
        throwable.printStackTrace(PrintWriter(writer))
        val report = buildString {
            appendLine("BOAT AI v${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})")
            appendLine("time=${System.currentTimeMillis()}")
            appendLine("thread=${thread.name}")
            appendLine("device=${Build.MANUFACTURER} ${Build.MODEL}")
            appendLine("android=${Build.VERSION.RELEASE} sdk=${Build.VERSION.SDK_INT}")
            appendLine()
            append(writer.toString())
        }.take(MAX_CRASH_CHARS)

        prefs.edit()
            .putBoolean(KEY_NORMAL_BOOT, false)
            .putString(KEY_LAST_CRASH, report)
            .putLong(KEY_LAST_CRASH_AT, System.currentTimeMillis())
            .commit()
    }

    companion object {
        private const val PREFS = "boat_ai_crash_recovery"
        private const val KEY_NORMAL_BOOT = "normal_boot_enabled"
        private const val KEY_LAST_CRASH = "last_crash"
        private const val KEY_LAST_CRASH_AT = "last_crash_at"
        private const val MAX_CRASH_CHARS = 16_000
    }
}
