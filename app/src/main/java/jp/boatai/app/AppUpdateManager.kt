package jp.boatai.app

import android.app.Activity
import android.app.Application
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL


data class AppUpdateState(
    val currentVersion: String = BuildConfig.VERSION_NAME,
    val latestVersion: String? = null,
    val updateAvailable: Boolean = false,
    val checking: Boolean = false,
    val downloading: Boolean = false,
    val downloadProgress: Int? = null,
    val releaseNotes: String? = null,
    val downloadUrl: String? = null,
    val expectedApkSha256: String? = null,
    val statusMessage: String? = null,
    val error: String? = null
)

internal object VersionComparator {
    fun isNewer(latest: String, current: String): Boolean = compare(latest, current) > 0

    fun compare(a: String, b: String): Int {
        val left = normalize(a)
        val right = normalize(b)
        val size = maxOf(left.size, right.size)
        for (index in 0 until size) {
            val l = left.getOrElse(index) { 0 }
            val r = right.getOrElse(index) { 0 }
            if (l != r) return l.compareTo(r)
        }
        return 0
    }

    private fun normalize(value: String): List<Int> = value
        .trim()
        .removePrefix("v")
        .removePrefix("V")
        .substringBefore('-')
        .split('.')
        .map { token -> token.takeWhile { it.isDigit() }.toIntOrNull() ?: 0 }
}

class AppUpdateManager(private val application: Application) {
    private val _state = MutableStateFlow(AppUpdateState())
    val state: StateFlow<AppUpdateState> = _state.asStateFlow()
    private val installState = application.getSharedPreferences(INSTALL_STATE_PREFS, Context.MODE_PRIVATE)

    @Volatile
    private var pendingApk: File? = null

    suspend fun checkForUpdates(userInitiated: Boolean = false) {
        _state.update {
            it.copy(
                checking = true,
                error = null,
                statusMessage = if (userInitiated) "更新を確認しています…" else null
            )
        }

        runCatching { fetchLatestRelease() }
            .onSuccess { release ->
                val available = VersionComparator.isNewer(release.version, BuildConfig.VERSION_NAME)
                _state.update {
                    it.copy(
                        latestVersion = release.version,
                        updateAvailable = available,
                        checking = false,
                        releaseNotes = release.notes,
                        downloadUrl = release.apkUrl,
                        expectedApkSha256 = release.apkSha256,
                        statusMessage = when {
                            available -> "v${release.version} の更新があります"
                            userInitiated -> "最新版です（v${BuildConfig.VERSION_NAME}）"
                            else -> null
                        },
                        error = null
                    )
                }
            }
            .onFailure { error ->
                _state.update {
                    it.copy(
                        checking = false,
                        statusMessage = null,
                        error = if (userInitiated) {
                            error.message ?: "更新確認に失敗しました"
                        } else {
                            null
                        }
                    )
                }
            }
    }

    suspend fun downloadAndInstall(activity: Activity) {
        val snapshot = state.value
        val url = snapshot.downloadUrl ?: return
        _state.update {
            it.copy(
                downloading = true,
                downloadProgress = 0,
                error = null,
                statusMessage = "更新APKをダウンロードしています…"
            )
        }

        runCatching {
            val file = downloadApk(url)
            DownloadedApkVerifier.verify(application, file, snapshot.expectedApkSha256)
            file
        }
            .onSuccess { file ->
                pendingApk = file
                _state.update {
                    it.copy(
                        downloading = false,
                        downloadProgress = 100,
                        statusMessage = "APKの署名・バージョンを確認しました"
                    )
                }
                requestInstall(activity)
            }
            .onFailure { error ->
                pendingApk = null
                installState.edit().putBoolean(KEY_AWAITING_UNKNOWN_SOURCE_PERMISSION, false).apply()
                updateTargetFile().delete()
                _state.update {
                    it.copy(
                        downloading = false,
                        downloadProgress = null,
                        error = error.message ?: "APKのダウンロードまたは検証に失敗しました",
                        statusMessage = null
                    )
                }
            }
    }

    fun resumePendingInstall(activity: Activity) {
        val awaitingPermission = installState.getBoolean(KEY_AWAITING_UNKNOWN_SOURCE_PERMISSION, false)
        val file = pendingApk ?: if (awaitingPermission) updateTargetFile().takeIf { it.exists() } else null
        if (file == null) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !activity.packageManager.canRequestPackageInstalls()) {
            return
        }

        runCatching {
            DownloadedApkVerifier.verify(application, file, state.value.expectedApkSha256)
        }.onSuccess {
            pendingApk = file
            requestInstall(activity)
        }.onFailure { error ->
            pendingApk = null
            installState.edit().putBoolean(KEY_AWAITING_UNKNOWN_SOURCE_PERMISSION, false).apply()
            file.delete()
            _state.update {
                it.copy(
                    statusMessage = null,
                    error = error.message ?: "更新APKの再検証に失敗しました"
                )
            }
        }
    }

    private suspend fun fetchLatestRelease(): LatestRelease = withContext(Dispatchers.IO) {
        val endpoint = "https://api.github.com/repos/${BuildConfig.UPDATE_REPOSITORY}/releases/latest"
        val connection = (URL(endpoint).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15_000
            readTimeout = 15_000
            requestMethod = "GET"
            setRequestProperty("Accept", "application/vnd.github+json")
            setRequestProperty("User-Agent", "BOAT-AI/${BuildConfig.VERSION_NAME}")
            setRequestProperty("X-GitHub-Api-Version", "2022-11-28")
        }
        try {
            val code = connection.responseCode
            if (code !in 200..299) {
                throw IllegalStateException("更新サーバー応答エラー ($code)")
            }
            val body = connection.inputStream.bufferedReader().use { it.readText() }
            val json = JSONObject(body)
            val tag = json.optString("tag_name")
            if (tag.isBlank()) throw IllegalStateException("最新バージョン情報がありません")

            val assets = json.optJSONArray("assets")
                ?: throw IllegalStateException("更新APKが公開されていません")
            var apkUrl: String? = null
            var apkSha256: String? = null
            for (index in 0 until assets.length()) {
                val asset = assets.getJSONObject(index)
                val name = asset.optString("name")
                if (name.endsWith(".apk", ignoreCase = true)) {
                    apkUrl = asset.optString("browser_download_url").takeIf { it.isNotBlank() }
                    apkSha256 = asset.optString("digest")
                        .removePrefix("sha256:")
                        .lowercase()
                        .takeIf { it.matches(Regex("[0-9a-f]{64}")) }
                    if (apkUrl != null) break
                }
            }
            LatestRelease(
                version = tag.removePrefix("v").removePrefix("V"),
                notes = json.optString("body").takeIf { it.isNotBlank() },
                apkUrl = apkUrl ?: throw IllegalStateException("ReleaseにAPKが見つかりません"),
                apkSha256 = apkSha256
            )
        } finally {
            connection.disconnect()
        }
    }

    private suspend fun downloadApk(downloadUrl: String): File = withContext(Dispatchers.IO) {
        val target = updateTargetFile()
        target.parentFile?.mkdirs()
        if (target.exists()) target.delete()

        val connection = (URL(downloadUrl).openConnection() as HttpURLConnection).apply {
            connectTimeout = 20_000
            readTimeout = 60_000
            instanceFollowRedirects = true
            setRequestProperty("User-Agent", "BOAT-AI/${BuildConfig.VERSION_NAME}")
        }
        try {
            val code = connection.responseCode
            if (code !in 200..299) throw IllegalStateException("APK取得エラー ($code)")
            val total = connection.contentLengthLong
            connection.inputStream.use { input ->
                target.outputStream().use { output ->
                    val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                    var read: Int
                    var copied = 0L
                    while (input.read(buffer).also { read = it } >= 0) {
                        output.write(buffer, 0, read)
                        copied += read
                        if (total > 0) {
                            val progress = ((copied * 100) / total).toInt().coerceIn(0, 99)
                            _state.update { it.copy(downloadProgress = progress) }
                        }
                    }
                }
            }
            if (!target.exists() || target.length() == 0L) {
                throw IllegalStateException("APKファイルが空です")
            }
            target
        } finally {
            connection.disconnect()
        }
    }

    private fun requestInstall(activity: Activity) {
        val file = pendingApk ?: return
        if (!file.exists()) {
            pendingApk = null
            installState.edit().putBoolean(KEY_AWAITING_UNKNOWN_SOURCE_PERMISSION, false).apply()
            _state.update { it.copy(error = "更新APKが見つかりません", statusMessage = null) }
            return
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !activity.packageManager.canRequestPackageInstalls()) {
            installState.edit().putBoolean(KEY_AWAITING_UNKNOWN_SOURCE_PERMISSION, true).apply()
            _state.update {
                it.copy(statusMessage = "「この提供元のアプリを許可」をONにして、BOAT AIへ戻ってください")
            }
            val settingsIntent = Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:${activity.packageName}")
            )
            activity.startActivity(settingsIntent)
            return
        }

        val uri = FileProvider.getUriForFile(
            activity,
            "${activity.packageName}.fileprovider",
            file
        )
        val installIntent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        installState.edit().putBoolean(KEY_AWAITING_UNKNOWN_SOURCE_PERMISSION, false).apply()
        pendingApk = null
        _state.update {
            it.copy(statusMessage = "Androidの確認画面で「更新」を押してください")
        }
        activity.startActivity(installIntent)
    }

    private fun updateTargetFile(): File = File(File(application.cacheDir, "updates"), "BOAT-AI-update.apk")

    private data class LatestRelease(
        val version: String,
        val notes: String?,
        val apkUrl: String,
        val apkSha256: String?
    )

    companion object {
        private const val INSTALL_STATE_PREFS = "boat_ai_update_install_state"
        private const val KEY_AWAITING_UNKNOWN_SOURCE_PERMISSION = "awaiting_unknown_source_permission"
    }
}
