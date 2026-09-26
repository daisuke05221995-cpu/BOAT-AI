from pathlib import Path

path = Path('app/src/main/java/jp/boatai/app/CompactDashboardScreens.kt')
text = path.read_text(encoding='utf-8')

old_filter = '''    val dateText = ui.date.toString()
    val weekStart = ui.date.minusDays(6).toString()
    val monthPrefix = String.format(Locale.US, "%04d-%02d", ui.date.year, ui.date.monthValue)

    val settledPredictions = ui.predictionHistory.filter { it.settled && it.evaluationEligible }
    val retrospectivePredictions = ui.modelARecentVirtualRecords.filter { it.settled && it.evaluationEligible }
    val selectedRetrospective = when (period) {
        0 -> retrospectivePredictions.filter { it.date == dateText }
        1 -> retrospectivePredictions.filter { it.date >= weekStart && it.date <= dateText }
        2 -> retrospectivePredictions.filter { it.date.startsWith(monthPrefix) }
        else -> retrospectivePredictions
    }
    val selectedPredictions = when (period) {
        0 -> settledPredictions.filter { it.date == dateText }
        1 -> settledPredictions.filter { it.date >= weekStart && it.date <= dateText }
        2 -> settledPredictions.filter { it.date.startsWith(monthPrefix) }
        else -> settledPredictions
    }
    val selectedActual = when (period) {
        0 -> ui.records.filter { it.date == dateText }
        1 -> ui.records.filter { it.date >= weekStart && it.date <= dateText }
        2 -> ui.records.filter { it.date.startsWith(monthPrefix) }
        else -> ui.records
    }
'''
new_filter = '''    val dateText = ui.date.toString()
    val periods = ProfitPeriod.entries
    val selectedPeriod = periods.getOrElse(period) { ProfitPeriod.TODAY }

    val settledPredictions = ui.predictionHistory.filter { it.settled && it.evaluationEligible }
    val retrospectivePredictions = ui.modelARecentVirtualRecords.filter { it.settled && it.evaluationEligible }
    val selectedRetrospective = retrospectivePredictions.filter {
        ProfitPeriodFilter.includes(selectedPeriod, it.date, ui.date)
    }
    val selectedPredictions = settledPredictions.filter {
        ProfitPeriodFilter.includes(selectedPeriod, it.date, ui.date)
    }
    val selectedActual = ui.records.filter {
        ProfitPeriodFilter.includes(selectedPeriod, it.date, ui.date)
    }
'''
if old_filter not in text:
    raise SystemExit('period filter anchor not found')
text = text.replace(old_filter, new_filter, 1)

old_buttons = '''            Card(modifier = Modifier.fillMaxWidth()) {
                Row(Modifier.fillMaxWidth().padding(4.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
                    listOf("今日", "7日", "月", "全期間").forEachIndexed { index, label ->
                        TextButton(onClick = { period = index }) {
                            Text(label, fontWeight = if (period == index) FontWeight.Bold else FontWeight.Normal)
                        }
                    }
                }
            }
'''
new_buttons = '''            Card(modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth().padding(4.dp)) {
                    periods.chunked(3).forEach { rowPeriods ->
                        Row(Modifier.fillMaxWidth()) {
                            rowPeriods.forEach { option ->
                                val index = periods.indexOf(option)
                                TextButton(
                                    onClick = { period = index },
                                    modifier = Modifier.weight(1f)
                                ) {
                                    Text(option.label, fontWeight = if (selectedPeriod == option) FontWeight.Bold else FontWeight.Normal)
                                }
                            }
                        }
                    }
                }
            }
'''
if old_buttons not in text:
    raise SystemExit('period button anchor not found')
text = text.replace(old_buttons, new_buttons, 1)

old_audit_vars = '''    val liveAuditCoverage = LiveAuditedPerformance.coverage(selectedPredictions)
    val auditedLiveRecords = LiveAuditedPerformance.eligible(selectedPredictions)
    val auditedLive = ProfitAnalytics.summarize(auditedLiveRecords)
'''
new_audit_vars = '''    val liveAuditCoverage = LiveAuditedPerformance.coverage(selectedPredictions)
    val liveAuditFailureCounts = LiveAuditedPerformance.failureCounts(selectedPredictions)
    val auditedLiveRecords = LiveAuditedPerformance.eligible(selectedPredictions)
    val auditedLive = ProfitAnalytics.summarize(auditedLiveRecords)
'''
if old_audit_vars not in text:
    raise SystemExit('audit variable anchor not found')
text = text.replace(old_audit_vars, new_audit_vars, 1)

text = text.replace('Text("実購入", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)',
                    'Text("実購入累計", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)', 1)
text = text.replace('Text("ライブ監査済みAI購入推奨", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)',
                    'Text("AIライブ累計", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleMedium)', 1)

old_missing = '''                    if (liveAuditCoverage.missingAuditCount > 0) {
                        Text("監査情報不足 ${liveAuditCoverage.missingAuditCount}R はこの成績から除外しています。", style = MaterialTheme.typography.bodySmall)
                    }
'''
new_missing = '''                    if (liveAuditCoverage.missingAuditCount > 0) {
                        Text("監査情報不足 ${liveAuditCoverage.missingAuditCount}R はこの成績から除外しています。", style = MaterialTheme.typography.bodySmall)
                        if (liveAuditFailureCounts.isNotEmpty()) {
                            val reasonText = LiveAuditFailure.entries.mapNotNull { reason ->
                                liveAuditFailureCounts[reason]?.takeIf { it > 0 }?.let { count -> "${reason.label} $count" }
                            }.joinToString(" / ")
                            Text("不足内訳: $reasonText", style = MaterialTheme.typography.labelSmall)
                        }
                    }
'''
if old_missing not in text:
    raise SystemExit('missing audit anchor not found')
text = text.replace(old_missing, new_missing, 1)

# Keep the default Profit view focused on real money. Research cards stay available
# from the existing AI analysis/validation section instead of dominating the main flow.
research_title = 'Text("Model A 過去仮想損益（確定払戻）"'
research_pos = text.find(research_title)
if research_pos == -1:
    raise SystemExit('research card anchor not found')
research_start = text.rfind('\n        item {', 0, research_pos)
analytics_marker = '''        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AnalyticsMiniCard("AI購入推奨", recommended, Modifier.weight(1f))
                AnalyticsMiniCard("全予想", all, Modifier.weight(1f))
            }
        }
'''
analytics_pos = text.find(analytics_marker, research_pos)
if research_start == -1 or analytics_pos == -1:
    raise SystemExit('research block boundary not found')
research_end = analytics_pos + len(analytics_marker)
text = text[:research_start] + '\n' + text[research_end:]

path.write_text(text, encoding='utf-8')
print('Patched CompactProfitScreen for cumulative money-first UI.')
