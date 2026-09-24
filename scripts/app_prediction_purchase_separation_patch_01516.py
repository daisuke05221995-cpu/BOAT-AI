#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def replace_once(path: Path, old: str, new: str):
    text=path.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'pattern not found in {path}: {old[:100]!r}')
    if text.count(old)!=1:
        raise SystemExit(f'pattern not unique in {path}: {text.count(old)}')
    path.write_text(text.replace(old,new,1),encoding='utf-8')

avg=ROOT/'app/src/main/java/jp/boatai/app/AverageRoiReferenceStrategy.kt'
avg.write_text(r'''package jp.boatai.app

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.exp
import kotlin.math.max

/**
 * Pure AI finish-order forecast used by v0.15.16.
 *
 * Prediction and purchase selection are intentionally separate. The v0.15.15
 * purchase-value ranking bought 99.5% of usable July-August 2025 races in the
 * sealed-safe diagnostic and returned 68.5% archived-odds ROI, so automatic BUY
 * recommendations are paused instead of being presented as prediction.
 *
 * Forecast probability uses only pre-race racer/form/course information. Odds never
 * change the ordering of forecast picks. A future purchase policy must be validated
 * separately before PURCHASE_RECOMMENDATION_ENABLED can be turned on.
 */
internal object AverageRoiReferenceStrategy {
    const val FORECAST_ENABLED = true
    const val PURCHASE_RECOMMENDATION_ENABLED = false
    const val ENABLED = PURCHASE_RECOMMENDATION_ENABLED
    const val RELEASE_QUALIFIED = false

    // Historical comparison only; neither number is a claim for the v0.15.16 forecast.
    const val HISTORICAL_ROI = 117.3
    const val HISTORICAL_PURCHASES = 2_407
    const val HISTORICAL_HITS = 45
    const val HISTORICAL_ROI_APPLIES_TO_CURRENT = false

    const val BUDGET = 1_200
    const val FORECAST_POINTS = 4
    private const val SCORE_TEMPERATURE = 14.0

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

    internal fun formScore(racer: Racer): Double {
        val national = (racer.nationalWinRate ?: 0.0) * 5.2
        val local = (racer.localWinRate ?: 0.0) * 2.6
        val motor = (racer.motorTop2 ?: 0.0) * 0.22
        val boat = (racer.boatTop2 ?: 0.0) * 0.08
        val start = racer.averageStart?.let { max(0.0, (0.22 - it) * 58.0) } ?: 0.0
        val exhibition = racer.preview?.exhibitionTime?.let { max(-5.0, (6.95 - it) * 18.0) } ?: 0.0
        val previewStart = racer.preview?.startTiming?.let { max(-4.0, (0.18 - it) * 32.0) } ?: 0.0
        return national + local + motor + boat + start + exhibition + previewStart
    }

    private fun coursePrior(racer: Racer): Double {
        val course = racer.preview?.course ?: racer.lane
        return when (course) {
            1 -> 8.0
            2 -> 4.0
            3 -> 2.0
            4 -> 0.0
            5 -> -1.5
            6 -> -3.0
            else -> 0.0
        }
    }

    /**
     * Top trifecta outcomes by the AI model probability only. Official odds are not an
     * input, so favourite/longshot pricing cannot move a combination up or down here.
     */
    internal fun forecast(race: RaceData, maxPicks: Int = FORECAST_POINTS): List<PredictionPick> {
        if (!FORECAST_ENABLED || race.racers.size != 6) return emptyList()
        val racers = race.racers.associateBy { it.lane }
        val rawScores = (1..6).associateWith { lane ->
            val racer = racers[lane] ?: return@associateWith Double.NEGATIVE_INFINITY
            formScore(racer) + coursePrior(racer)
        }
        val finiteScores = rawScores.values.filter { it.isFinite() }
        val maxScore = finiteScores.maxOrNull() ?: return emptyList()
        val weights = (1..6).associateWith { lane ->
            val score = rawScores[lane] ?: Double.NEGATIVE_INFINITY
            if (score.isFinite()) exp((score - maxScore) / SCORE_TEMPERATURE) else 0.0
        }
        val weightTotal = weights.values.sum()
        if (weightTotal <= 0.0) return emptyList()

        return combinations.mapNotNull { combo ->
            val lanes = combo.split('-').mapNotNull(String::toIntOrNull)
            if (lanes.size != 3) return@mapNotNull null
            val firstWeight = weights[lanes[0]] ?: 0.0
            val secondWeight = weights[lanes[1]] ?: 0.0
            val thirdWeight = weights[lanes[2]] ?: 0.0
            val secondDenom = weightTotal - firstWeight
            val thirdDenom = secondDenom - secondWeight
            if (firstWeight <= 0.0 || secondDenom <= 0.0 || thirdDenom <= 0.0) return@mapNotNull null
            val probability =
                (firstWeight / weightTotal) *
                    (secondWeight / secondDenom) *
                    (thirdWeight / thirdDenom)
            PredictionPick(
                combination = combo,
                score = probability,
                reason = "AI着順確率 ${"%.1f".format(probability * 100.0)}%"
            )
        }.sortedByDescending { it.score }
            .take(maxPicks.coerceIn(1, FORECAST_POINTS))
    }

    /** Automatic purchase policy is deliberately paused after the v0.15.15 audit. */
    internal fun evaluate(
        race: RaceData,
        officialOdds: Map<String, Double>,
        budget: Int = BUDGET
    ): ValueSelection = skip(
        "v0.15.15購入ロジックは過去診断不合格のため自動推奨を停止中。AI予想と手動購入は利用できます"
    )

    private fun skip(detail: String) = ValueSelection(
        picks = emptyList(),
        recommendation = RaceRecommendation.SKIP,
        reason = "購入判定：$detail"
    )
}
''',encoding='utf-8')

engine=ROOT/'app/src/main/java/jp/boatai/app/PredictionEngine.kt'
replace_once(engine,
'''    fun hasValueStrategyModel(): Boolean = valueStrategyModel != null
    fun hasAverageRoiReferenceStrategy(): Boolean = AverageRoiReferenceStrategy.ENABLED
    fun averageRoiOddsCombinations(): List<String> = AverageRoiReferenceStrategy.allCombinations()
''',
'''    fun hasValueStrategyModel(): Boolean = valueStrategyModel != null
    fun hasAiForecastMode(): Boolean = AverageRoiReferenceStrategy.FORECAST_ENABLED
    fun hasAverageRoiReferenceStrategy(): Boolean = AverageRoiReferenceStrategy.PURCHASE_RECOMMENDATION_ENABLED
    fun averageRoiOddsCombinations(): List<String> = AverageRoiReferenceStrategy.allCombinations()
''')
replace_once(engine,
'''    fun recommendation(race: RaceData): RecommendationDecision {
        if (AverageRoiReferenceStrategy.ENABLED) {
            AverageRoiReferenceStrategy.cached(race)?.let { selection ->
                return RecommendationDecision(selection.recommendation, selection.reason)
            }
        }
''',
'''    fun recommendation(race: RaceData): RecommendationDecision {
        if (AverageRoiReferenceStrategy.FORECAST_ENABLED &&
            !AverageRoiReferenceStrategy.PURCHASE_RECOMMENDATION_ENABLED
        ) {
            return RecommendationDecision(
                RaceRecommendation.SKIP,
                "AI着順予想は表示中。v0.15.15購入ロジックの過去診断不合格を受け、自動購入推奨は再検証まで停止中"
            )
        }
        if (AverageRoiReferenceStrategy.PURCHASE_RECOMMENDATION_ENABLED) {
            AverageRoiReferenceStrategy.cached(race)?.let { selection ->
                return RecommendationDecision(selection.recommendation, selection.reason)
            }
        }
''')
replace_once(engine,
'''    fun predict(race: RaceData, maxPicks: Int = 4): List<PredictionPick> {
        if (AverageRoiReferenceStrategy.ENABLED) {
            AverageRoiReferenceStrategy.cached(race)?.let { selection ->
                return if (selection.recommendation == RaceRecommendation.BUY) {
                    selection.picks.take(maxPicks.coerceAtLeast(1))
                } else emptyList()
            }
        }
        if (valueStrategyModel != null) {
''',
'''    fun predict(race: RaceData, maxPicks: Int = 4): List<PredictionPick> {
        if (valueStrategyModel == null && AverageRoiReferenceStrategy.FORECAST_ENABLED) {
            return AverageRoiReferenceStrategy.forecast(race, maxPicks)
        }
        if (valueStrategyModel != null) {
''')
replace_once(engine,
'''        if (AverageRoiReferenceStrategy.ENABLED) {
            val selection = AverageRoiReferenceStrategy.evaluateAndCache(race, odds, budget)
            return if (selection.recommendation == RaceRecommendation.BUY) {
                BetStrategy.allocate(race, selection.picks, budget)
            } else emptyList()
        }
        if (valueStrategyModel != null) {
''',
'''        if (valueStrategyModel == null && AverageRoiReferenceStrategy.FORECAST_ENABLED) {
            val count = picks.size.coerceAtLeast(1)
            val forecast = AverageRoiReferenceStrategy.forecast(race, count)
                .map { pick -> pick.copy(odds = odds[pick.combination]) }
            return BetStrategy.allocate(race, forecast, budget)
        }
        if (valueStrategyModel != null) {
''')

vm=ROOT/'app/src/main/java/jp/boatai/app/BoatViewModel.kt'
replace_once(vm,
'''                            oddsDecision = if (PredictionEngine.hasValueStrategyModel() || PredictionEngine.hasAverageRoiReferenceStrategy()) {
''',
'''                            oddsDecision = if (PredictionEngine.hasValueStrategyModel() || PredictionEngine.hasAiForecastMode()) {
''')
replace_once(vm,
'''                oddsDecision = if (race != null && !PredictionEngine.hasValueStrategyModel()) {
                    BetStrategy.oddsDecision(predictions)
                } else {
                    state.oddsDecision
                }
''',
'''                oddsDecision = if (race != null && !PredictionEngine.hasValueStrategyModel() && !PredictionEngine.hasAiForecastMode()) {
                    BetStrategy.oddsDecision(predictions)
                } else if (race != null && PredictionEngine.hasAiForecastMode()) {
                    PredictionEngine.recommendation(race).reason
                } else {
                    state.oddsDecision
                }
''')

main=ROOT/'app/src/main/java/jp/boatai/app/MainActivity.kt'
replace_once(main,
'''            Text("v0.15.15から着順予想はAI主体です。1号艇のコース有利と市場人気をそのまま本命化せず、選手力・当地・モーター・ST・展示で上積みがある艇を評価します。旧v0.15.14のROI117.3%は比較用の旧方式実績で、現ロジックの実績ではありません。", style = MaterialTheme.typography.bodySmall)
''',
'''            Text("v0.15.16では予想と購入判定を分離しました。予想はオッズを見ず、選手力・当地・モーター・ST・展示・進入からAI着順確率上位4点を表示します。v0.15.15の購入判定は2025年7〜8月診断で99.5% BUY・ROI68.5%だったため、自動購入推奨は次の検証済み戦略まで停止中です。予想からの手動購入は利用できます。", style = MaterialTheme.typography.bodySmall)
''')

build=ROOT/'app/build.gradle.kts'
replace_once(build,'versionCode = 33','versionCode = 34')
replace_once(build,'versionName = "0.15.15"','versionName = "0.15.16"')
replace_once(build,
'// v0.15.15: AI-first prediction with market-edge gate to reduce automatic lane-1 following.',
'// v0.15.16: separate pure AI forecast from purchase recommendation; pause failed auto-BUY policy.')

test=ROOT/'app/src/test/java/jp/boatai/app/AverageRoiReferenceStrategyTest.kt'
test.write_text(r'''package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AverageRoiReferenceStrategyTest {
    @Test
    fun forecastIsEnabledAndFailedPurchasePolicyIsPaused() {
        assertTrue(AverageRoiReferenceStrategy.FORECAST_ENABLED)
        assertFalse(AverageRoiReferenceStrategy.PURCHASE_RECOMMENDATION_ENABLED)
        assertFalse(AverageRoiReferenceStrategy.ENABLED)
        assertFalse(AverageRoiReferenceStrategy.RELEASE_QUALIFIED)
        assertFalse(AverageRoiReferenceStrategy.HISTORICAL_ROI_APPLIES_TO_CURRENT)
        assertEquals(4, AverageRoiReferenceStrategy.FORECAST_POINTS)
    }

    @Test
    fun forecastDoesNotNeedOddsAndWeakLaneOneIsNotForcedToFirst() {
        val race = weakLaneOneRace()
        val picks = AverageRoiReferenceStrategy.forecast(race, 4)
        assertEquals(4, picks.size)
        assertTrue(picks.first().combination.startsWith("3-"))
        assertTrue(picks.first().reason.startsWith("AI着順確率"))
        assertTrue(picks.zipWithNext().all { (a,b) -> a.score >= b.score })
    }

    @Test
    fun genuinelyStrongLaneOneCanStillLeadForecast() {
        val picks = AverageRoiReferenceStrategy.forecast(strongLaneOneRace(), 4)
        assertEquals(4, picks.size)
        assertTrue(picks.first().combination.startsWith("1-"))
    }

    @Test
    fun automaticPurchaseEvaluationIsAlwaysPaused() {
        val odds = AverageRoiReferenceStrategy.allCombinations().associateWith { 20.0 }
        val result = AverageRoiReferenceStrategy.evaluate(strongLaneOneRace(), odds, 1_200)
        assertEquals(RaceRecommendation.SKIP, result.recommendation)
        assertTrue(result.picks.isEmpty())
        assertTrue(result.reason.contains("自動推奨を停止中"))
    }

    private fun weakLaneOneRace() = baseRace { lane ->
        when (lane) {
            1 -> racer(lane, 4.2, 3.8, 26.0, 0.19, 6.88, 0.18)
            3 -> racer(lane, 8.4, 8.0, 48.0, 0.11, 6.62, 0.08)
            4 -> racer(lane, 7.8, 7.4, 44.0, 0.12, 6.66, 0.10)
            else -> racer(lane, 6.0, 5.8, 34.0, 0.16, 6.78, 0.14)
        }
    }

    private fun strongLaneOneRace() = baseRace { lane ->
        when (lane) {
            1 -> racer(lane, 9.0, 8.7, 52.0, 0.10, 6.58, 0.07)
            2 -> racer(lane, 7.0, 6.8, 38.0, 0.14, 6.72, 0.12)
            3 -> racer(lane, 6.8, 6.5, 36.0, 0.15, 6.75, 0.13)
            else -> racer(lane, 5.7, 5.4, 32.0, 0.17, 6.82, 0.16)
        }
    }

    private fun baseRace(factory: (Int) -> Racer) = RaceData(
        date = "2026-09-24", stadiumNumber = 1, raceNumber = 1, closedAt = "23:59",
        gradeNumber = null, title = "test", subtitle = "", distance = 1800, dayNumber = 1,
        racers = (1..6).map(factory),
        preview = PreviewData(2, null, 2, null, null, null), result = null
    )

    private fun racer(
        lane: Int,
        national: Double,
        local: Double,
        motor: Double,
        averageStart: Double,
        exhibition: Double,
        previewStart: Double
    ) = Racer(
        lane = lane, name = "r$lane", registrationNumber = 4000 + lane, rank = "A1",
        branch = null, age = null, weight = 52.0, averageStart = averageStart,
        nationalWinRate = national, nationalTop2 = null, nationalTop3 = null,
        localWinRate = local, localTop2 = null, localTop3 = null,
        motorNumber = lane, motorTop2 = motor, motorTop3 = null,
        boatNumber = lane, boatTop2 = 35.0, boatTop3 = null,
        preview = PreviewRacer(lane, previewStart, 52.0, 0.0, exhibition, 0.0)
    )
}
''',encoding='utf-8')

print('v0.15.16 separation patch applied')
