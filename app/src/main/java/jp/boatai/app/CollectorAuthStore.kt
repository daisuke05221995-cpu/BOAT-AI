package jp.boatai.app

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Pairing secret stays encrypted in Android Keystore; never in app backup or GitHub. */
internal class CollectorAuthStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun deviceId(): String {
        prefs.getString(KEY_ID, null)?.let { return it }
        val generated = UUID.randomUUID().toString()
        prefs.edit().putString(KEY_ID, generated).apply()
        return generated
    }

    fun hasToken(): Boolean = readToken() != null

    fun saveToken(token: String) {
        require(token.length in 32..200 && token.all {
            it in 'a'..'z' || it in 'A'..'Z' || it in '0'..'9' || it == '-' || it == '_'
        }) {
            "共有キーは英数字・-・_で32〜200文字を指定してください"
        }
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val encrypted = cipher.iv + cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        prefs.edit().putString(KEY_TOKEN, Base64.encodeToString(encrypted, Base64.NO_WRAP)).apply()
    }

    fun removeToken() { prefs.edit().remove(KEY_TOKEN).apply() }

    fun readToken(): String? = runCatching {
        val payload = prefs.getString(KEY_TOKEN, null) ?: return null
        val bytes = Base64.decode(payload, Base64.NO_WRAP)
        require(bytes.size > 12)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
        String(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8)
    }.getOrNull()

    private fun key(): SecretKey {
        val keystore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keystore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build())
        }.generateKey()
    }

    private companion object {
        const val PREFS = "boat_ai_collector_pairing_v1"
        const val KEY_ALIAS = "boat_ai_collector_aes_v1"
        const val KEY_ID = "device_id"
        const val KEY_TOKEN = "encrypted_token"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
