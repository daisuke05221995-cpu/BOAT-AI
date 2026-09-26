package jp.boatai.app

import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import java.io.File
import java.security.MessageDigest

/**
 * Verifies that an APK downloaded for in-app update is safe to hand to Android's
 * package installer as an overwrite update of the currently installed BOAT AI.
 */
object DownloadedApkVerifier {
    data class VerifiedApk(
        val packageName: String,
        val versionCode: Long,
        val sha256: String
    )

    fun verify(
        context: Context,
        apkFile: File,
        expectedSha256: String? = null
    ): VerifiedApk {
        require(apkFile.exists() && apkFile.isFile && apkFile.length() > 0L) {
            "更新APKが見つからないか、ファイルが空です"
        }

        val actualSha256 = sha256(apkFile)
        expectedSha256
            ?.trim()
            ?.lowercase()
            ?.takeIf { it.matches(Regex("[0-9a-f]{64}")) }
            ?.let { expected ->
                require(actualSha256 == expected) { "更新APKのSHA-256がRelease情報と一致しません" }
            }

        val packageManager = context.packageManager
        val flags = signingFlags()
        val downloaded = packageManager.getPackageArchiveInfo(apkFile.absolutePath, flags)
            ?: throw IllegalStateException("更新APKのパッケージ情報を読み取れません")
        val installed = packageManager.getPackageInfo(context.packageName, flags)

        require(downloaded.packageName == context.packageName) {
            "更新APKのパッケージ名がBOAT AIと一致しません"
        }

        val downloadedVersionCode = versionCode(downloaded)
        val installedVersionCode = versionCode(installed)
        require(downloadedVersionCode > installedVersionCode) {
            "更新APKが現在のバージョンより新しくありません"
        }

        val currentSigners = signerDigests(installed)
        val downloadedSigners = signerDigests(downloaded)
        require(currentSigners.isNotEmpty() && downloadedSigners.isNotEmpty()) {
            "更新APKの署名を確認できません"
        }
        require(currentSigners == downloadedSigners) {
            "更新APKの署名が現在のBOAT AIと一致しません"
        }

        return VerifiedApk(
            packageName = downloaded.packageName,
            versionCode = downloadedVersionCode,
            sha256 = actualSha256
        )
    }

    private fun signingFlags(): Int = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        PackageManager.GET_SIGNING_CERTIFICATES
    } else {
        @Suppress("DEPRECATION")
        PackageManager.GET_SIGNATURES
    }

    private fun versionCode(info: PackageInfo): Long = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        info.longVersionCode
    } else {
        @Suppress("DEPRECATION")
        info.versionCode.toLong()
    }

    private fun signerDigests(info: PackageInfo): Set<String> {
        val signatures = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val signingInfo = info.signingInfo ?: return emptySet()
            if (signingInfo.hasMultipleSigners()) {
                signingInfo.apkContentsSigners
            } else {
                signingInfo.apkContentsSigners
            }
        } else {
            @Suppress("DEPRECATION")
            info.signatures ?: emptyArray()
        }
        return signatures.map { signature ->
            MessageDigest.getInstance("SHA-256")
                .digest(signature.toByteArray())
                .joinToString("") { "%02x".format(it) }
        }.toSet()
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val read = input.read(buffer)
                if (read <= 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
