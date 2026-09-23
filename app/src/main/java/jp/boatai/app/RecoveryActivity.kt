package jp.boatai.app

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

class RecoveryActivity : ComponentActivity() {
    private val recoveryStore by lazy { CrashRecoveryStore(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        if (recoveryStore.normalBootEnabled) {
            launchNormalMode()
            return
        }

        setContent {
            BoatAiTheme {
                RecoveryScreen(
                    crashLog = recoveryStore.lastCrash(),
                    onLaunchNormal = {
                        recoveryStore.enableNormalBoot()
                        launchNormalMode()
                    },
                    onCopyCrash = { copyCrashLog() },
                    onClearCrash = {
                        recoveryStore.clearCrash()
                        recreate()
                    }
                )
            }
        }
    }

    private fun launchNormalMode() {
        startActivity(Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
        })
        finish()
    }

    private fun copyCrashLog() {
        val log = recoveryStore.lastCrash() ?: return
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText("BOAT AI crash log", log))
        Toast.makeText(this, "クラッシュ情報をコピーしました", Toast.LENGTH_SHORT).show()
    }
}

@Composable
private fun RecoveryScreen(
    crashLog: String?,
    onLaunchNormal: () -> Unit,
    onCopyCrash: () -> Unit,
    onClearCrash: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp, vertical = 28.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(
            "BOAT AI 復旧モード",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold
        )
        Text("v${BuildConfig.VERSION_NAME}")

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(
                Modifier.padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                Text("端末データは削除していません", fontWeight = FontWeight.Bold)
                Text("この版では原因切り分けのため、自動予想追跡・購入推奨通知などのバックグラウンド処理を一時停止しています。")
                Text("「通常モードを試す」で本体を起動します。再度クラッシュした場合は、次の起動でこの画面へ戻り、下に原因ログが表示されます。")
            }
        }

        Button(onClick = onLaunchNormal, modifier = Modifier.fillMaxWidth()) {
            Text("通常モードを試す")
        }

        if (crashLog != null) {
            Text("前回のクラッシュ情報", fontWeight = FontWeight.Bold)
            Card(modifier = Modifier.fillMaxWidth()) {
                Text(
                    crashLog,
                    modifier = Modifier.padding(12.dp),
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace
                )
            }
            Button(onClick = onCopyCrash, modifier = Modifier.fillMaxWidth()) {
                Text("クラッシュ情報をコピー")
            }
            OutlinedButton(onClick = onClearCrash, modifier = Modifier.fillMaxWidth()) {
                Text("表示中のクラッシュ記録だけ消す")
            }
        } else {
            Text("クラッシュ記録はまだありません。まず通常モードを試してください。")
        }
    }
}
