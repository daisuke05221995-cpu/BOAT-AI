from pathlib import Path
import re

ROOT = Path("app/src/main/java/jp/boatai/app")
MAIN = ROOT / "MainActivity.kt"
DASH = ROOT / "CompactDashboardScreens.kt"
NOTIFY = ROOT / "NotificationScheduler.kt"
TRACK = ROOT / "PredictionTrackingScheduler.kt"
SETTINGS = ROOT / "SettingsScreen.kt"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: target not found")
    return text.replace(old, new, 1)


def patch_main() -> None:
    text = MAIN.read_text()

    if "import androidx.activity.compose.BackHandler" not in text:
        text = replace_once(
            text,
            "import androidx.activity.ComponentActivity\n",
            "import androidx.activity.ComponentActivity\nimport androidx.activity.compose.BackHandler\n",
            "BackHandler import",
        )
    if "import androidx.compose.material.icons.filled.Settings" not in text:
        text = replace_once(
            text,
            "import androidx.compose.material.icons.filled.ShoppingCart\n",
            "import androidx.compose.material.icons.filled.ShoppingCart\nimport androidx.compose.material.icons.filled.Settings\n",
            "Settings icon import",
        )
    if "import androidx.compose.runtime.mutableStateOf" not in text:
        text = replace_once(
            text,
            "import androidx.compose.runtime.mutableIntStateOf\n",
            "import androidx.compose.runtime.mutableIntStateOf\nimport androidx.compose.runtime.mutableStateOf\n",
            "mutableStateOf import",
        )
    if "import androidx.compose.runtime.saveable.rememberSaveable" not in text:
        text = replace_once(
            text,
            "import androidx.compose.runtime.remember\n",
            "import androidx.compose.runtime.remember\nimport androidx.compose.runtime.saveable.rememberSaveable\n",
            "rememberSaveable import",
        )

    old_state = """    val selected = ui.selectedRace
    val selectedVenue = ui.selectedVenue

    Scaffold(
"""
    new_state = """    val selected = ui.selectedRace
    val selectedVenue = ui.selectedVenue
    var settingsOpen by rememberSaveable { mutableStateOf(false) }

    BackHandler(enabled = true) {
        when {
            settingsOpen -> settingsOpen = false
            selected != null -> vm.closeRace()
            selectedVenue != null -> vm.closeVenue()
            ui.tab != 0 -> vm.setTab(0)
            else -> Unit
        }
    }

    Scaffold(
"""
    if "var settingsOpen by rememberSaveable" not in text:
        text = replace_once(text, old_state, new_state, "settings state and back handling")

    if 'settingsOpen -> "設定"' not in text:
        text = replace_once(
            text,
            """                        when {
                            selected != null -> "${selected.venueName} ${selected.raceNumber}R"
""",
            """                        when {
                            settingsOpen -> "設定"
                            selected != null -> "${selected.venueName} ${selected.raceNumber}R"
""",
            "settings title",
        )

    old_nav = """                navigationIcon = {
                    if (selected != null || selectedVenue != null) {
                        IconButton(onClick = if (selected != null) vm::closeRace else vm::closeVenue) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "戻る")
                        }
                    }
                },
"""
    new_nav = """                navigationIcon = {
                    if (settingsOpen || selected != null || selectedVenue != null) {
                        IconButton(onClick = {
                            when {
                                settingsOpen -> settingsOpen = false
                                selected != null -> vm.closeRace()
                                else -> vm.closeVenue()
                            }
                        }) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "戻る")
                        }
                    }
                },
"""
    if old_nav in text:
        text = text.replace(old_nav, new_nav, 1)

    old_actions = """                actions = {
                    if (selected == null && selectedVenue == null && ui.tab in 0..2) {
                        IconButton(onClick = vm::refresh) {
                            Icon(Icons.Default.Refresh, contentDescription = "更新")
                        }
                    }
                }
"""
    new_actions = """                actions = {
                    if (!settingsOpen && selected == null && selectedVenue == null) {
                        if (ui.tab in 0..2) {
                            IconButton(onClick = vm::refresh) {
                                Icon(Icons.Default.Refresh, contentDescription = "更新")
                            }
                        }
                        IconButton(onClick = { settingsOpen = true }) {
                            Icon(Icons.Default.Settings, contentDescription = "設定")
                        }
                    }
                }
"""
    if "Icon(Icons.Default.Settings, contentDescription = \"設定\")" not in text:
        text = replace_once(text, old_actions, new_actions, "top app bar settings action")

    text = text.replace(
        "if (selected == null && selectedVenue == null) {\n                NavigationBar {",
        "if (!settingsOpen && selected == null && selectedVenue == null) {\n                NavigationBar {",
        1,
    )

    old_route = """            when {
                selected != null -> RaceDetailScreen(ui, vm)
"""
    new_route = """            when {
                settingsOpen -> SettingsScreen(ui, vm)
                selected != null -> RaceDetailScreen(ui, vm)
"""
    if "settingsOpen -> SettingsScreen(ui, vm)" not in text:
        text = replace_once(text, old_route, new_route, "settings screen route")

    MAIN.write_text(text)


def patch_dashboards() -> None:
    text = DASH.read_text()
    text = text.replace("    var showSettings by remember { mutableStateOf(false) }\n", "", 1)

    pattern = re.compile(
        r'''\n        item \{\n            OutlinedButton\(onClick = \{ showSettings = !showSettings \}, modifier = Modifier\.fillMaxWidth\(\)\) \{\n                Text\(if \(showSettings\) "設定を閉じる ▲" else "通知・バックアップ設定 ▼"\)\n            \}\n        \}\n        if \(showSettings\) \{\n            item \{ BackupCard\(ui, vm\) \}\n            item \{ NotificationSettingsCard\(ui, vm\) \}\n        \}\n'''
    )
    text, count = pattern.subn("\n", text, count=1)
    if count == 0 and "通知・バックアップ設定" in text:
        raise RuntimeError("profit settings block not removed")
    DASH.write_text(text)


def patch_notifications() -> None:
    text = NOTIFY.read_text()

    text = text.replace('const val CHANNEL = "boat_ai_events"', 'const val CHANNEL = "boat_ai_events_visual_v3"')
    text = text.replace('const val ALERT_CHANNEL = "boat_ai_buy_alerts_silent_v2"', 'const val ALERT_CHANNEL = "boat_ai_buy_alerts_visual_v3"')
    text = text.replace('const val SERVICE_CHANNEL = "boat_ai_alert_checks_silent_v2"', 'const val SERVICE_CHANNEL = "boat_ai_alert_checks_visual_v3"')

    old_general = """        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "レース・更新通知", NotificationManager.IMPORTANCE_DEFAULT)
        )
"""
    new_general = """        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "BOAT AI通知（表示のみ）", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "BOAT AIからの通知を音・振動なしで表示します"
                setSound(null, null)
                enableVibration(false)
            }
        )
"""
    if old_general in text:
        text = text.replace(old_general, new_general, 1)

    text = text.replace(
        'NotificationChannel(ALERT_CHANNEL, "購入推奨アラート（無音）", NotificationManager.IMPORTANCE_HIGH)',
        'NotificationChannel(ALERT_CHANNEL, "購入推奨アラート（表示のみ）", NotificationManager.IMPORTANCE_HIGH)',
    )
    text = text.replace(
        'NotificationChannel(SERVICE_CHANNEL, "購入推奨判定処理（無音）", NotificationManager.IMPORTANCE_LOW)',
        'NotificationChannel(SERVICE_CHANNEL, "購入推奨判定処理（表示のみ）", NotificationManager.IMPORTANCE_LOW)',
    )
    text = text.replace(
        '"購入推奨判定処理（無音）",\n                    NotificationManager.IMPORTANCE_LOW',
        '"購入推奨判定処理（表示のみ）",\n                    NotificationManager.IMPORTANCE_LOW',
    )

    purchase_marker = """            .setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
            .setSilent(true)
"""
    purchase_new = """            .setCategory(NotificationCompat.CATEGORY_RECOMMENDATION)
            .setDefaults(0)
            .setVibrate(longArrayOf(0L))
            .setSilent(true)
"""
    if purchase_marker in text and ".setVibrate(longArrayOf(0L))" not in text[text.find("val notification = NotificationCompat.Builder(context, ALERT_CHANNEL)"):text.find("fun recordCheck")]:
        text = text.replace(purchase_marker, purchase_new, 1)

    old_basic = """    private fun basicNotification(title: String, body: String) = NotificationCompat.Builder(context, CHANNEL)
        .setSmallIcon(android.R.drawable.ic_dialog_info)
        .setContentTitle(title)
        .setContentText(body)
        .setAutoCancel(true)
        .build()
"""
    new_basic = """    private fun basicNotification(title: String, body: String) = NotificationCompat.Builder(context, CHANNEL)
        .setSmallIcon(android.R.drawable.ic_dialog_info)
        .setContentTitle(title)
        .setContentText(body)
        .setPriority(NotificationCompat.PRIORITY_DEFAULT)
        .setDefaults(0)
        .setVibrate(longArrayOf(0L))
        .setSilent(true)
        .setAutoCancel(true)
        .build()
"""
    if old_basic in text:
        text = text.replace(old_basic, new_basic, 1)

    service_marker = """            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setSilent(true)
            .setOngoing(true)
"""
    service_new = """            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setDefaults(0)
            .setVibrate(longArrayOf(0L))
            .setSilent(true)
            .setOngoing(true)
"""
    # Replace only the foreground service block; purchase recommendation already has HIGH priority.
    service_pos = text.find("val notification = NotificationCompat.Builder(this, NotificationScheduler.SERVICE_CHANNEL)")
    if service_pos >= 0:
        tail = text[service_pos:]
        if service_marker in tail and ".setVibrate(longArrayOf(0L))" not in tail[:tail.find(".build()") + 8]:
            tail = tail.replace(service_marker, service_new, 1)
            text = text[:service_pos] + tail

    NOTIFY.write_text(text)


def patch_tracking() -> None:
    text = TRACK.read_text()
    text = text.replace(
        'const val SERVICE_CHANNEL = "boat_ai_prediction_tracking"',
        'const val SERVICE_CHANNEL = "boat_ai_prediction_tracking_visual_v2"',
    )
    text = text.replace(
        '"事前予想の自動記録",\n                    NotificationManager.IMPORTANCE_LOW',
        '"事前予想の自動記録（表示のみ）",\n                    NotificationManager.IMPORTANCE_LOW',
    )
    marker = """            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setSilent(true)
            .setOngoing(true)
"""
    replacement = """            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setDefaults(0)
            .setVibrate(longArrayOf(0L))
            .setSilent(true)
            .setOngoing(true)
"""
    if marker in text and ".setVibrate(longArrayOf(0L))" not in text:
        text = text.replace(marker, replacement, 1)
    TRACK.write_text(text)


def create_settings_screen() -> None:
    SETTINGS.write_text('''package jp.boatai.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@Composable
fun SettingsScreen(ui: BoatUiState, vm: BoatViewModel) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("BOAT AI 設定", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text("普段の予想・購入・結果・損益から設定を分離しました。", style = MaterialTheme.typography.bodySmall)
                    Text("v${BuildConfig.VERSION_NAME}", style = MaterialTheme.typography.labelMedium)
                }
            }
        }

        item {
            Text("通知・自動記録", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        }
        item { NotificationSettingsCard(ui, vm) }

        item {
            Text("データ・バックアップ", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
        }
        item { BackupCard(ui, vm) }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("戻る操作", fontWeight = FontWeight.Bold)
                    Text("端末の戻るキーは画面を1段ずつ戻します。予想ホームでは誤操作でアプリを終了しません。", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}
''')


if __name__ == "__main__":
    patch_main()
    patch_dashboards()
    patch_notifications()
    patch_tracking()
    create_settings_screen()
    print("Applied settings/back/silent-notification UX fixes")
