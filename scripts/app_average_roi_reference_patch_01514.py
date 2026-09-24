#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app/src/main/java/jp/boatai/app"
TEST = ROOT / "app/src/test/java/jp/boatai/app"


def replace_required(path: Path, old: str, new: str, count: int | None = None) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found == 0:
        raise RuntimeError(f"{path}: missing expected text: {old[:100]!r}")
    if count is not None and found != count:
        raise RuntimeError(f"{path}: expected {count} occurrences, found {found}: {old[:100]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


# Rename the temporary r3-reference API everywhere in Android sources/tests.
renames = {
    "ReferenceR3Strategy": "AverageRoiReferenceStrategy",
    "hasReferenceR3Strategy": "hasAverageRoiReferenceStrategy",
    "referenceOddsCombinations": "averageRoiOddsCombinations",
    "hasReferenceSelection": "hasAverageRoiSelection",
    "applyReferenceOdds": "applyAverageRoiOdds",
}
for base in (APP, TEST):
    for path in base.glob("*.kt"):
        text = path.read_text(encoding="utf-8")
        for old, new in renames.items():
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")

# Make the bulk-refresh variable self-documenting as well.
boat_vm = APP / "BoatViewModel.kt"
text = boat_vm.read_text(encoding="utf-8").replace("referenceMode", "averageRoiMode")
boat_vm.write_text(text, encoding="utf-8")

# Replace the tiny-sample r3 reference with the frozen high-average-ROI v12 operating policy.
old_strategy = APP / "ReferenceR3Strategy.kt"
if old_strategy.exists():
    old_strategy.unlink()
new_strategy = APP / "AverageRoiReferenceStrategy.kt"
new_strategy.write_text(r'''package jp.boatai.app

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.exp
import kotlin.math.ln

/**
 * Reference-only live approximation of the frozen 2026 v12 operating policy.
 *
 * Historical development evidence (2026-05..09): 2,407 purchase races, 45 hits,
 * combined ROI 117.3%, four positive months out of five, worst month ROI 94.7%.
 * The original research model did NOT pass independent multi-year validation, so this
 * strategy is deliberately labelled reference-only and MUST NOT be described as a
 * production-qualified or profit-guaranteed model.
 *
 * The historical model was a monthly conditional finish-order model. Android does not
 * ship those monthly learned weights, therefore the model probability below is a
 * transparent live approximation derived from the current BOAT AI racer scores. The
 * historical v12 market blend and ticket gate themselves are kept frozen:
 * alpha=0.25, minEV=1.05, minProbability=0.005, maxOdds=150, maxPoints=2, equal stake.
 */
internal object AverageRoiReferenceStrategy {
    const val ENABLED = true
    const val RELEASE_QUALIFIED = false
    const val HISTORICAL_ROI = 117.3
    const val HISTORICAL_PURCHASES = 2_407
    const val HISTORICAL_HITS = 45
    const val POSITIVE_MONTHS = 4
    const val TOTAL_MONTHS = 5
    const val WORST_MONTH_ROI = 94.7

    const val BUDGET = 1_200
    const val MAX_POINTS = 2
    const val ALPHA = 0.25
    const val MIN_EV = 1.05
    const val MIN_PROBABILITY = 0.005
    const val MAX_ODDS = 150.0

    private val selections = ConcurrentHashMap<String, ValueSelection>()
    private val combinations = buildList(120) {
        for (first in 1..6) for (second in 1..6) for (third in 1..6) {
            if (first != second && first != third && second != third) add("$first-$second-$third")
        }
    }

    fun allCombinations(): List<String> = combinations
    fun cached(race: RaceData): ValueSelection? = selections[race.id]
    fun clear() = selections.clear()

    fun evaluateAndCache(
        race: RaceData,
        officialOdds: Map<String, Double>,
        budget: Int = BUDGET
    ): ValueSelection = selections.computeIfAbsent(race.id) {
        evaluate(race, officialOdds, budget)
    }

    internal fun evaluate(
        race: RaceData,
        officialOdds: Map<String, Double>,
        budget: Int = BUDGET
    ): ValueSelection {
        if (race.racers.size != 6 || officialOdds.count { it.value > 1.0 } < 100) {
            return skip("公式3連単オッズが十分に取得できていません")
        }

        val inverseOdds = combinations.associateWith { combo ->
            officialOdds[combo]?.takeIf { it > 1.0 }?.let { 1.0 / it } ?: 0.0
        }
        val marketTotal = inverseOdds.values.sum()
        if (marketTotal <= 0.0) return skip("公式オッズを市場確率へ変換できません")

        val racers = race.racers.associateBy { it.lane }
        val rawScores = (1..6).associateWith { lane ->
            racers[lane]?.let(PredictionEngine::racerScore) ?: 0.0
        }
        val maxScore = rawScores.values.maxOrNull() ?: 0.0
        val weights = (1..6).associateWith { lane ->
            exp(((rawScores[lane] ?: 0.0) - maxScore) / 18.0)
        }
        val weightTotal = weights.values.sum()
        if (weightTotal <= 0.0) return skip("AI確率を計算できません")

        data class BlendRow(
            val combination: String,
            val odds: Double,
            val rawBlend: Double
        )

        val rows = buildList(120) {
            for (combo in combinations) {
                val lanes = combo.split('-').mapNotNull(String::toIntOrNull)
                if (lanes.size != 3) continue
                val first = lanes[0]
                val second = lanes[1]
                val third = lanes[2]
                val odds = officialOdds[combo]?.takeIf { it > 1.0 } ?: continue

                val firstWeight = weights[first] ?: 0.0
                val secondWeight = weights[second] ?: 0.0
                val thirdWeight = weights[third] ?: 0.0
                val secondDenom = weightTotal - firstWeight
                val thirdDenom = secondDenom - secondWeight
                if (firstWeight <= 0.0 || secondDenom <= 0.0 || thirdDenom <= 0.0) continue

                val modelProbability =
                    (firstWeight / weightTotal) *
                    (secondWeight / secondDenom) *
                    (thirdWeight / thirdDenom)
                val marketProbability = (inverseOdds[combo] ?: 0.0) / marketTotal
                if (modelProbability <= 0.0 || marketProbability <= 0.0) continue

                val rawBlend = exp(
                    ALPHA * ln(modelProbability.coerceAtLeast(1e-12)) +
                        (1.0 - ALPHA) * ln(marketProbability.coerceAtLeast(1e-12))
                )
                add(BlendRow(combo, odds, rawBlend))
            }
        }
        val blendTotal = rows.sumOf { it.rawBlend }
        if (blendTotal <= 0.0) return skip("AIと市場の混合確率を計算できません")

        data class Candidate(
            val combination: String,
            val probability: Double,
            val odds: Double,
            val ev: Double
        )

        val selected = rows.mapNotNull { row ->
            val probability = row.rawBlend / blendTotal
            val ev = probability * row.odds
            if (row.odds > MAX_ODDS || probability < MIN_PROBABILITY || ev < MIN_EV) {
                null
            } else {
                Candidate(row.combination, probability, row.odds, ev)
            }
        }.sortedWith(
            compareByDescending<Candidate> { it.ev }.thenByDescending { it.probability }
        ).take(MAX_POINTS)

        if (selected.isEmpty()) {
            return skip("平均ROI参考条件（EV・確率・オッズ上限）に該当する買い目がありません")
        }

        val stakes = BetStrategy.allocateEvenly(selected.size, budget.coerceIn(1_000, 3_000))
        val picks = selected.mapIndexed { index, candidate ->
            PredictionPick(
                combination = candidate.combination,
                score = candidate.ev,
                odds = candidate.odds,
                recommendedStake = stakes[index],
                tier = when {
                    index == 0 && candidate.odds < 15.0 -> BetTier.MAIN
                    candidate.odds >= 80.0 -> BetTier.LONG
                    else -> BetTier.MID
                },
                reason = "平均ROI参考 α${"%.2f".format(ALPHA)} EV${"%.2f".format(candidate.ev)}"
            )
        }
        return ValueSelection(
            picks = picks,
            recommendation = RaceRecommendation.BUY,
            reason = "参考購入：2026年5〜9月の平均ROI固定条件を現行AIで近似（2,407購入・ROI117.3%、複数年検証は不合格）"
        )
    }

    private fun skip(detail: String) = ValueSelection(
        picks = emptyList(),
        recommendation = RaceRecommendation.SKIP,
        reason = "参考見送り：$detail（平均ROI条件は複数年検証不合格）"
    )
}
''', encoding="utf-8")

# Replace/rename the unit test so the frozen average-ROI policy cannot drift silently.
old_test = TEST / "ReferenceR3StrategyTest.kt"
if old_test.exists():
    old_test.unlink()
new_test = TEST / "AverageRoiReferenceStrategyTest.kt"
new_test.write_text(r'''package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AverageRoiReferenceStrategyTest {
    @Test
    fun exposesFrozenAverageRoiPolicyAndAllCombinations() {
        assertEquals(120, AverageRoiReferenceStrategy.allCombinations().distinct().size)
        assertEquals(1_200, AverageRoiReferenceStrategy.BUDGET)
        assertEquals(2, AverageRoiReferenceStrategy.MAX_POINTS)
        assertEquals(0.25, AverageRoiReferenceStrategy.ALPHA, 0.00001)
        assertEquals(1.05, AverageRoiReferenceStrategy.MIN_EV, 0.00001)
        assertEquals(0.005, AverageRoiReferenceStrategy.MIN_PROBABILITY, 0.00001)
        assertEquals(150.0, AverageRoiReferenceStrategy.MAX_ODDS, 0.00001)
        assertEquals(2_407, AverageRoiReferenceStrategy.HISTORICAL_PURCHASES)
        assertEquals(45, AverageRoiReferenceStrategy.HISTORICAL_HITS)
        assertEquals(117.3, AverageRoiReferenceStrategy.HISTORICAL_ROI, 0.00001)
        assertEquals(4, AverageRoiReferenceStrategy.POSITIVE_MONTHS)
        assertEquals(5, AverageRoiReferenceStrategy.TOTAL_MONTHS)
        assertFalse(AverageRoiReferenceStrategy.RELEASE_QUALIFIED)
    }

    @Test
    fun evaluationNeverReturnsMoreThanTwoPicksAndKeepsBudget() {
        val odds = AverageRoiReferenceStrategy.allCombinations().associateWith { 20.0 }
        val result = AverageRoiReferenceStrategy.evaluate(testRace(), odds, 1_200)
        assertTrue(result.picks.size <= 2)
        if (result.recommendation == RaceRecommendation.BUY) {
            assertEquals(1_200, result.picks.sumOf { it.recommendedStake })
            assertTrue(result.picks.all { (it.odds ?: 999.0) <= 150.0 })
            assertTrue(result.reason.contains("2,407購入"))
            assertTrue(result.reason.contains("複数年検証は不合格"))
        }
    }

    private fun testRace() = RaceData(
        date = "2026-09-24", stadiumNumber = 1, raceNumber = 1, closedAt = "23:59",
        gradeNumber = null, title = "test", subtitle = "", distance = 1800, dayNumber = 1,
        racers = (1..6).map { lane ->
            Racer(
                lane = lane, name = "r$lane", registrationNumber = 4000 + lane, rank = "A1",
                branch = null, age = null, weight = 52.0, averageStart = 0.15 + lane * 0.001,
                nationalWinRate = 7.0 - lane * 0.2, nationalTop2 = null, nationalTop3 = null,
                localWinRate = 6.5 - lane * 0.15, localTop2 = null, localTop3 = null,
                motorNumber = lane, motorTop2 = 40.0 - lane, motorTop3 = null,
                boatNumber = lane, boatTop2 = 35.0, boatTop3 = null,
                preview = PreviewRacer(lane, 0.12 + lane * 0.005, 52.0, 0.0, 6.70 + lane * 0.01, 0.0)
            )
        },
        preview = PreviewData(2, null, 2, null, null, null), result = null
    )
}
''', encoding="utf-8")

main_activity = APP / "MainActivity.kt"
replace_required(
    main_activity,
    "現在はr3 place-smallの固定条件を参考運用中です。過去ROI258.5%は24購入・3的中で検証不合格のため、最終判断は必ずご自身で行ってください。",
    "現在は2026年5〜9月の平均ROI固定条件を参考運用中です。過去検証は2,407購入・ROI117.3%・5か月中4か月プラスですが、複数年検証は不合格のため最終判断は必ずご自身で行ってください。",
    1,
)

build_gradle = ROOT / "app/build.gradle.kts"
replace_required(build_gradle, 'versionCode = 31', 'versionCode = 32', 1)
replace_required(build_gradle, 'versionName = "0.15.13"', 'versionName = "0.15.14"', 1)
replace_required(
    build_gradle,
    '// v0.15.13: official-app purchase handoff + temporary r3 reference mode.',
    '// v0.15.14: replace tiny-sample r3 reference with frozen average-ROI reference policy.',
    1,
)

# Guard against accidentally leaving the old tiny-sample reference wired in.
for path in list(APP.glob("*.kt")) + list(TEST.glob("*.kt")):
    text = path.read_text(encoding="utf-8")
    if "ReferenceR3Strategy" in text or "hasReferenceR3Strategy" in text or "r3 place-small" in text:
        raise RuntimeError(f"old r3 reference remains in {path}")

print("v0.15.14 average-ROI reference patch applied")
