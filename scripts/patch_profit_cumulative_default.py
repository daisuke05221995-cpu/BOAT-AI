from pathlib import Path

path = Path('app/src/main/java/jp/boatai/app/CompactDashboardScreens.kt')
text = path.read_text(encoding='utf-8')

text = text.replace(
    '    var period by remember { mutableIntStateOf(0) }\n',
    '    var period by remember { mutableIntStateOf(ProfitPeriod.entries.indexOf(ProfitPeriod.ALL)) }\n',
    1,
)

old = '''    val actualSettled = selectedActual.filter { it.settled }
    val actualStake = actualSettled.sumOf { it.stake }
    val actualPayout = actualSettled.sumOf { it.payout }
    val actualRoi = if (actualStake > 0) actualPayout * 100.0 / actualStake else 0.0
    val pendingStake = selectedActual.filterNot { it.settled }.sumOf { it.stake }
'''
new = '''    val actualSettled = selectedActual.filter { it.settled }
    val actualStake = actualSettled.sumOf { it.stake }
    val actualPayout = actualSettled.sumOf { it.payout }
    val actualRoi = if (actualStake > 0) actualPayout * 100.0 / actualStake else 0.0
    val actualRaceGroups = actualSettled.groupBy { "${it.date}-${it.stadiumNumber}-${it.raceNumber}" }
    val actualRaceCount = actualRaceGroups.size
    val actualHitRaceCount = actualRaceGroups.count { (_, tickets) -> tickets.any { it.payout > 0 } }
    val actualHitRate = if (actualRaceCount > 0) actualHitRaceCount * 100.0 / actualRaceCount else 0.0
    val pendingStake = selectedActual.filterNot { it.settled }.sumOf { it.stake }
'''
if old not in text:
    raise SystemExit('actual accounting anchor not found')
text = text.replace(old, new, 1)

old_card = '''                    Text("実購入累計", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text(signedCompactMoney(actualPayout - actualStake), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineMedium)
                    Text("購入 ${compactMoney(actualStake)} / 払戻 ${compactMoney(actualPayout)} / 回収率 ${compactPercent(actualRoi)}")
                    if (pendingStake > 0) Text("結果待ち ${compactMoney(pendingStake)}", style = MaterialTheme.typography.bodySmall)
'''
new_card = '''                    Text("実購入累計（${selectedPeriod.label}）", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    Text(signedCompactMoney(actualPayout - actualStake), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineMedium)
                    Text("購入 ${compactMoney(actualStake)} / 払戻 ${compactMoney(actualPayout)} / 回収率 ${compactPercent(actualRoi)}")
                    Text("的中 ${actualHitRaceCount}/${actualRaceCount}R / 的中率 ${compactPercent(actualHitRate)}", style = MaterialTheme.typography.bodySmall)
                    if (pendingStake > 0) Text("結果待ち ${compactMoney(pendingStake)}", style = MaterialTheme.typography.bodySmall)
'''
if old_card not in text:
    raise SystemExit('actual card anchor not found')
text = text.replace(old_card, new_card, 1)

text = text.replace(
    '                    Text("AIライブ累計", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)\n',
    '                    Text("AIライブ累計（${selectedPeriod.label}）", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)\n',
    1,
)

path.write_text(text, encoding='utf-8')
print('Patched Profit screen to default to all-time and show actual race hit totals.')
# One-shot trigger for CI validation.
