#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)

main = Path("app/src/main/java/jp/boatai/app/MainActivity.kt")
text = main.read_text()
text = replace_once(text,
    "import androidx.compose.material.icons.filled.ShoppingCart\n",
    "import androidx.compose.material.icons.filled.ShoppingCart\nimport androidx.compose.material.icons.filled.Settings\n",
    "settings icon import")
text = replace_once(text,
    "import androidx.compose.runtime.mutableIntStateOf\n",
    "import androidx.compose.runtime.mutableIntStateOf\nimport androidx.compose.runtime.mutableStateOf\n",
    "mutableStateOf import")
text = replace_once(text,
    "    val selected = ui.selectedRace\n    val selectedVenue = ui.selectedVenue\n",
    "    val selected = ui.selectedRace\n    val selectedVenue = ui.selectedVenue\n    var settingsOpen by remember { mutableStateOf(false) }\n",
    "settings state")
text = replace_once(text,
    "                        when {\n                            selected != null -> \"${selected.venueName} ${selected.raceNumber}R\"\n",
    "                        when {\n                            settingsOpen -> \"設定\"\n                            selected != null -> \"${selected.venueName} ${selected.raceNumber}R\"\n",
    "settings title")
text = replace_once(text,
    "                navigationIcon = {\n                    if (selected != null || selectedVenue != null) {\n                        IconButton(onClick = if (selected != null) vm::closeRace else vm::closeVenue) {\n                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = \"戻る\")\n                        }\n                    }\n                },\n                actions = {\n                    if (selected == null && selectedVenue == null && ui.tab in 0..2) {\n                        IconButton(onClick = vm::refresh) {\n                            Icon(Icons.Default.Refresh, contentDescription = \"更新\")\n                        }\n                    }\n                }\n",
    "                navigationIcon = {\n                    when {\n                        settingsOpen -> IconButton(onClick = { settingsOpen = false }) {\n                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = \"設定を閉じる\")\n                        }\n                        selected != null || selectedVenue != null -> {\n                            IconButton(onClick = if (selected != null) vm::closeRace else vm::closeVenue) {\n                                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = \"戻る\")\n                            }\n                        }\n                    }\n                },\n                actions = {\n                    if (!settingsOpen) {\n                        if (selected == null && selectedVenue == null && ui.tab in 0..2) {\n                            IconButton(onClick = vm::refresh) {\n                                Icon(Icons.Default.Refresh, contentDescription = \"更新\")\n                            }\n                        }\n                        if (selected == null && selectedVenue == null) {\n                            IconButton(onClick = { settingsOpen = true }) {\n                                Icon(Icons.Default.Settings, contentDescription = \"設定\")\n                            }\n                        }\n                    }\n                }\n",
    "top app bar settings")
text = replace_once(text,
    "            if (selected == null && selectedVenue == null) {\n                NavigationBar {\n",
    "            if (!settingsOpen && selected == null && selectedVenue == null) {\n                NavigationBar {\n",
    "hide nav in settings")
text = replace_once(text,
    "            when {\n                selected != null -> RaceDetailScreen(ui, vm)\n",
    "            when {\n                settingsOpen -> SettingsScreen(ui, vm)\n                selected != null -> RaceDetailScreen(ui, vm)\n",
    "settings route")
main.write_text(text)

compact = Path("app/src/main/java/jp/boatai/app/CompactDashboardScreens.kt")
text = compact.read_text()
text = replace_once(text,
    "    var showAiDetails by remember { mutableStateOf(false) }\n    var showSettings by remember { mutableStateOf(false) }\n",
    "    var showAiDetails by remember { mutableStateOf(false) }\n",
    "remove inline settings state")
text = replace_once(text,
    "\n        item {\n            OutlinedButton(onClick = { showSettings = !showSettings }, modifier = Modifier.fillMaxWidth()) {\n                Text(if (showSettings) \"設定を閉じる ▲\" else \"通知・バックアップ設定 ▼\")\n            }\n        }\n        if (showSettings) {\n            item { BackupCard(ui, vm) }\n            item { NotificationSettingsCard(ui, vm) }\n        }\n",
    "\n",
    "remove inline settings UI")
compact.write_text(text)
print("settings UI patch applied")
