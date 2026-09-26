from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, got {count}")
    p.write_text(text.replace(old, new, 1))


path = "app/src/main/java/jp/boatai/app/MainActivity.kt"
replace_once(
    path,
    '''            Text("v0.16.0では、2025年9月の独立検証と2025年10〜12月の最終検証を通過した市場非入力Model Aで3連単確率上位4点を表示します。履歴オッズの締切前取得時刻を証明できないため自動購入推奨は停止中です。AI予想からの手動購入は利用できます。", style = MaterialTheme.typography.bodySmall)''',
    '''            Text("市場非入力Model Aの予想と、現在の公式3連単オッズを別レイヤーで評価します。120通りオッズと展示・進入などの直前情報が揃った購入可能レースだけAI購入推奨を出し、条件不足は安全側で見送ります。外部投票の自動実行はせず、最終購入は公式画面で行います。", style = MaterialTheme.typography.bodySmall)'''
)

path = "app/src/main/java/jp/boatai/app/CompactDashboardScreens.kt"
replace_once(
    path,
    '''                                            when {
                                                prediction == null -> "事前予想：記録なし"
                                                prediction.hit -> "✓ 的中  ${prediction.combinations.joinToString(" / ")}"
                                                else -> "予想  ${prediction.combinations.joinToString(" / ")}"
                                            },''',
    '''                                            when {
                                                prediction == null -> "事前予想：記録なし"
                                                prediction.hit -> "✓ 的中  ${prediction.combinations.joinToString(" / ")}"
                                                !prediction.recommended && prediction.combinations.isEmpty() -> "AI見送り：${prediction.recommendationReason ?: prediction.autoSkipReason ?: "購入条件を満たさず"}"
                                                else -> "予想  ${prediction.combinations.joinToString(" / ")}"
                                            },'''
)

replace_once(
    path,
    '''                                        if (prediction?.strategyId == ModelARecentVirtualRepository.STRATEGY_ID) {
                                            Text("Model A仮想 ${compactMoney(prediction.simulatedStake)} → ${compactMoney(prediction.simulatedPayout)} / ${signedCompactMoney(prediction.simulatedProfit)}", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
                                        }
                                        if (purchases.isNotEmpty()) {''',
    '''                                        if (prediction?.strategyId == ModelARecentVirtualRepository.STRATEGY_ID) {
                                            Text("Model A仮想 ${compactMoney(prediction.simulatedStake)} → ${compactMoney(prediction.simulatedPayout)} / ${signedCompactMoney(prediction.simulatedProfit)}", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
                                        }
                                        prediction?.liveOddsFetchedAt?.let { fetchedAt ->
                                            val fetchedTime = java.time.Instant.ofEpochMilli(fetchedAt)
                                                .atZone(ZoneId.of("Asia/Tokyo"))
                                                .format(DateTimeFormatter.ofPattern("HH:mm:ss"))
                                            val source = prediction.liveOddsSource ?: "取得元不明"
                                            val countText = if (prediction.liveOddsCount > 0) " / ${prediction.liveOddsCount}点" else ""
                                            Text("ライブ判定 $fetchedTime / $source$countText", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
                                            if (prediction.livePickOdds.size == prediction.combinations.size && prediction.livePickOdds.isNotEmpty()) {
                                                Text(
                                                    prediction.combinations.zip(prediction.livePickOdds).joinToString(" / ") { (combination, odds) ->
                                                        "$combination @${String.format(Locale.US, "%.1f", odds)}倍"
                                                    },
                                                    style = MaterialTheme.typography.labelSmall,
                                                    maxLines = 2,
                                                    overflow = TextOverflow.Ellipsis
                                                )
                                            }
                                        }
                                        if (purchases.isNotEmpty()) {'''
)
