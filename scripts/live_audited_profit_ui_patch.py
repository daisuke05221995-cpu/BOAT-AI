from pathlib import Path

path = Path("app/src/main/java/jp/boatai/app/CompactDashboardScreens.kt")
text = path.read_text()

old = '''    val recommended = ProfitAnalytics.summarize(selectedPredictions.filter { it.recommended })
    val all = ProfitAnalytics.summarize(selectedPredictions)
    val retrospective = ProfitAnalytics.summarize(selectedRetrospective)'''
new = '''    val recommended = ProfitAnalytics.summarize(selectedPredictions.filter { it.recommended })
    val all = ProfitAnalytics.summarize(selectedPredictions)
    val liveAuditCoverage = LiveAuditedPerformance.coverage(selectedPredictions)
    val auditedLiveRecords = LiveAuditedPerformance.eligible(selectedPredictions)
    val auditedLive = ProfitAnalytics.summarize(auditedLiveRecords)
    val retrospective = ProfitAnalytics.summarize(selectedRetrospective)'''
if text.count(old) != 1:
    raise SystemExit(f"summary anchor mismatch: {text.count(old)}")
text = text.replace(old, new, 1)

anchor = '''        item {
            Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Column(Modifier.padding(14.dp)) {
                    Text("Model A 過去仮想損益（確定払戻）", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)'''
replacement = '''        item {
            Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.tertiaryContainer)) {
                Column(Modifier.padding(14.dp)) {
                    Text("ライブ監査済みAI購入推奨", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)
                    if (auditedLive.races > 0) {
                        Text(signedCompactMoney(auditedLive.profit), fontWeight = FontWeight.Bold, style = MaterialTheme.typography.headlineMedium)
                        Text("${auditedLive.hits}/${auditedLive.races}的中 / 購入 ${compactMoney(auditedLive.stake)} / 払戻 ${compactMoney(auditedLive.payout)} / 回収率 ${compactPercent(auditedLive.roi)}")
                    } else {
                        Text("監査条件を満たす確定ライブBUYはまだありません。実運用データの蓄積後にここへ表示します。")
                    }
                    Text(
                        "監査済み ${liveAuditCoverage.auditedBuyCount} / ライブBUY ${liveAuditCoverage.liveBuyCount} / 完備率 ${compactPercent(liveAuditCoverage.coveragePercent)}",
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.SemiBold
                    )
                    if (liveAuditCoverage.missingAuditCount > 0) {
                        Text("監査情報不足 ${liveAuditCoverage.missingAuditCount}R はこの成績から除外しています。", style = MaterialTheme.typography.bodySmall)
                    }
                    Text(
                        "購入可能時間中の取得時刻・取得元・公式3連単120通り・選択買い目オッズ・実際の配分が揃ったvalue-v1の確定BUYだけを集計します。過去仮想損益とは混ぜません。",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }

''' + anchor
if text.count(anchor) != 1:
    raise SystemExit(f"retrospective card anchor mismatch: {text.count(anchor)}")
text = text.replace(anchor, replacement, 1)
path.write_text(text)
