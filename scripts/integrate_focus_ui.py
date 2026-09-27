from pathlib import Path

path = Path("app/src/main/java/jp/boatai/app/MainActivity.kt")
text = path.read_text()

if "FocusPredictionCard(" in text:
    print("FocusPredictionCard already wired")
    raise SystemExit(0)

expected = '''        item { Text("出走データ", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium) }
        items(race.racers, key = { it.lane }) { racer -> RacerCard(racer) }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
'''

replacement = '''        item { Text("出走データ", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium) }
        items(race.racers, key = { it.lane }) { racer -> RacerCard(racer) }

        item {
            FocusPredictionCard(
                race = race,
                raceBudget = ui.raceBudget,
                purchased = ui.records.any {
                    it.date == race.date && it.stadiumNumber == race.stadiumNumber && it.raceNumber == race.raceNumber
                },
                pendingPurchaseExists = ui.pendingPurchase != null
            )
        }

        item {
            Card(modifier = Modifier.fillMaxWidth()) {
'''

if expected not in text:
    raise SystemExit("Race detail insertion point not found")

path.write_text(text.replace(expected, replacement, 1))
print("FocusPredictionCard wired into RaceDetailScreen")
