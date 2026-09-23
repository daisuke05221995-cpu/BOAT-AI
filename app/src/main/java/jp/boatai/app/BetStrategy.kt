package jp.boatai.app

import kotlin.math.floor

object BetStrategy {
    const val DEFAULT_BUDGET = 1_200
    const val MIN_BUDGET = 1_000
    const val MAX_BUDGET = 3_000
    const val MAX_PICKS = 10

    fun allocate(race: RaceData, picks: List<PredictionPick>, requestedBudget: Int): List<PredictionPick> {
        if (picks.isEmpty()) return emptyList()
        val limited = picks.take(MAX_PICKS)
        val budget = requestedBudget.coerceIn(MIN_BUDGET, MAX_BUDGET).roundDown100()
        // If the upstream strategy already allocated stakes (for example the validated
        // value strategy's equal/probability allocation), preserve that ratio. This
        // keeps Android execution aligned with the strategy that selected the tickets.
        val stakes = scaleExistingAllocation(limited, budget) ?: allocateByRank(limited.size, budget)

        return limited.mapIndexed { index, pick ->
            val odds = pick.odds
            val tier = when {
                index == 0 && (odds == null || odds < 15.0) -> BetTier.MAIN
                odds != null && odds >= 35.0 -> BetTier.LONG
                index >= 3 -> BetTier.LONG
                else -> BetTier.MID
            }
            pick.copy(
                recommendedStake = stakes[index],
                tier = tier,
                reason = pick.reason.ifBlank { reasonFor(race, pick, index) }
            )
        }
    }

    private fun scaleExistingAllocation(picks: List<PredictionPick>, budget: Int): List<Int>? {
        if (picks.isEmpty() || picks.any { it.recommendedStake < 100 || it.recommendedStake % 100 != 0 }) {
            return null
        }
        val sourceUnits = picks.map { it.recommendedStake / 100 }
        val sourceTotal = sourceUnits.sum()
        if (sourceTotal <= 0) return null
        val targetUnits = budget / 100
        if (targetUnits < picks.size) return null

        val raw = sourceUnits.map { source -> targetUnits * source.toDouble() / sourceTotal }
        val units = raw.map { floor(it).toInt().coerceAtLeast(1) }.toMutableList()
        while (units.sum() < targetUnits) {
            val index = units.indices.maxByOrNull { idx -> raw[idx] - floor(raw[idx]) } ?: 0
            units[index] += 1
        }
        while (units.sum() > targetUnits) {
            val index = units.indices
                .filter { units[it] > 1 }
                .minByOrNull { idx -> raw[idx] - floor(raw[idx]) }
                ?: return null
            units[index] -= 1
        }
        return units.map { it * 100 }
    }

    /**
     * 1〜10点を100円単位で配分し、合計を必ず指定予算に一致させる。
     * 1〜4点は従来の本線重視比率を維持し、5点以上は順位に応じて緩やかに逓減する。
     */
    internal fun allocateByRank(pointCount: Int, requestedBudget: Int): List<Int> {
        val count = pointCount.coerceIn(1, MAX_PICKS)
        val budget = requestedBudget.coerceIn(MIN_BUDGET, MAX_BUDGET).roundDown100()
        val totalUnits = budget / 100
        require(totalUnits >= count) { "100円未満の買い目は作成できません" }

        val weights = when (count) {
            1 -> listOf(1.0)
            2 -> listOf(0.6, 0.4)
            3 -> listOf(0.5, 0.3, 0.2)
            4 -> listOf(0.4, 0.3, 0.2, 0.1)
            else -> (count downTo 1).map(Int::toDouble)
        }
        val weightTotal = weights.sum().coerceAtLeast(1.0)
        val rawUnits = weights.map { totalUnits * it / weightTotal }
        val units = rawUnits.map { floor(it).toInt().coerceAtLeast(1) }.toMutableList()

        while (units.sum() < totalUnits) {
            val index = units.indices.maxByOrNull { idx -> rawUnits[idx] - floor(rawUnits[idx]) }
                ?: 0
            units[index] += 1
        }
        while (units.sum() > totalUnits) {
            val index = units.indices
                .filter { units[it] > 1 }
                .minByOrNull { idx -> rawUnits[idx] - floor(rawUnits[idx]) }
                ?: break
            units[index] -= 1
        }
        return units.map { it * 100 }
    }

    fun reasonFor(race: RaceData, pick: PredictionPick, rankIndex: Int): String {
        val lanes = pick.combination.split("-").mapNotNull(String::toIntOrNull)
        val winner = lanes.firstOrNull()?.let { lane -> race.racers.firstOrNull { it.lane == lane } }
        val reasons = buildList {
            if (winner?.lane == 1) add("イン有利")
            winner?.nationalWinRate?.let { if (it >= 6.0) add("全国勝率${"%.2f".format(it)}") }
            winner?.motorTop2?.let { if (it >= 35.0) add("モーター2連率${"%.1f".format(it)}%") }
            winner?.averageStart?.let { if (it <= 0.16) add("平均ST${"%.2f".format(it)}") }
            winner?.preview?.exhibitionTime?.let { add("展示${"%.2f".format(it)}") }
            race.preview?.windSpeed?.let { if (it >= 5) add("強風${it}m補正") }
            if (rankIndex == 0) add("総合評価1位")
        }
        return reasons.take(3).joinToString("・").ifBlank { "選手力・コース・機力の総合評価" }
    }

    fun oddsDecision(picks: List<PredictionPick>): String {
        if (picks.isEmpty() || picks.any { it.odds == null }) return "オッズ取得後に最終判断を更新します"
        val total = picks.sumOf { it.recommendedStake }.coerceAtLeast(1)
        val returns = picks.map { (it.odds ?: 0.0) * it.recommendedStake }
        val mainReturn = returns.firstOrNull() ?: 0.0
        val profitableCount = returns.count { it >= total * 1.20 }
        val strongUpsideCount = returns.count { it >= total * 2.0 }
        return when {
            returns.all { it < total } -> "見送り：どの買い目が的中しても購入額を下回ります"
            mainReturn >= total * 1.50 && profitableCount >= 2 ->
                "購入推奨：本線150%以上かつ複数買い目に十分な払戻余地があります"
            mainReturn >= total * 1.30 && strongUpsideCount >= 2 ->
                "購入推奨：本線130%以上かつ中穴側にも十分な払戻余地があります"
            else -> "見送り：払戻余地が厳選購入基準に届きません"
        }
    }

    fun oddsChange(before: List<PredictionPick>, after: List<PredictionPick>): String? {
        val changes = after.mapNotNull { next ->
            val old = before.firstOrNull { it.combination == next.combination }?.odds ?: return@mapNotNull null
            val current = next.odds ?: return@mapNotNull null
            val percent = if (old > 0) (current - old) * 100.0 / old else 0.0
            if (kotlin.math.abs(percent) >= 10.0) "${next.combination} ${if (percent >= 0) "+" else ""}${"%.0f".format(percent)}%" else null
        }
        return changes.takeIf { it.isNotEmpty() }?.joinToString(" / ", prefix = "前回比 ")
    }

    private fun Int.roundDown100(): Int = this / 100 * 100
}
