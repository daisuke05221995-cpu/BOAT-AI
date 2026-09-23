#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)

path = Path('app/src/main/java/jp/boatai/app/MainActivity.kt')
text = path.read_text()
text = replace_once(
    text,
    'import androidx.activity.compose.LocalActivity\n',
    'import androidx.activity.compose.BackHandler\nimport androidx.activity.compose.LocalActivity\n',
    'BackHandler import'
)
text = replace_once(
    text,
    '    val selected = ui.selectedRace\n    val selectedVenue = ui.selectedVenue\n    var settingsOpen by remember { mutableStateOf(false) }\n\n    Scaffold(\n',
    '    val selected = ui.selectedRace\n    val selectedVenue = ui.selectedVenue\n    var settingsOpen by remember { mutableStateOf(false) }\n\n    BackHandler {\n        when {\n            settingsOpen -> settingsOpen = false\n            selected != null -> vm.closeRace()\n            selectedVenue != null -> vm.closeVenue()\n            ui.tab != 0 -> vm.setTab(0)\n            else -> Unit\n        }\n    }\n\n    Scaffold(\n',
    'BackHandler routing'
)
path.write_text(text)
print('back navigation patch applied')
