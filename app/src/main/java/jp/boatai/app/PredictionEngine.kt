package jp.boatai.app

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.max

object PredictionEngine {
    const val BUY_THRESHOLD = 80

    @Volatile private var learningProfile = LearningProfile()
    @Volatile private var persistentPerformanceProfile = PredictionPerformanceProfile()
    @Volatile private var performanceProfile = PredictionPerformanceProfile()
    @Volatile private var valueStrategyModel: ValueStrategyModel? = null
    private val valueSelections = ConcurrentHashMap<String, ValueSelection>()

    fun installLearningProfile(profile: LearningProfile) {
        learningProfile = profile
    }

    fun installPersistentPerformanceProfile(profile: PredictionPerformanceProfile) {
        persistentPerformanceProfile = profile
    }

    fun installPerformanceProfile(profile: PredictionPerformanceProfile) {
        performanceProfile = persistentPerformanceProfile.mergedWith(profile)
    }

    /**
     * The independently validated value model is optional. Stable releases without the
     * promoted asset continue to use the legacy engine unchanged.
     */
    internal fun installValueStrategyModel(model: ValueStrategyModel?) {
        valueStrategyModel = model
        valueSelections.clear()
    }

    fun hasValueStrategyModel(): Boolean = valueStrategyModel != null
    fun hasAiForecastMode(): Boolean = AverageRoiReferenceStrategy.FORECAST_ENABLED
    fun hasAverageRoiReferenceStrategy(): Boolean = AverageRoiReferenceStrategy.PURCHASE_RECOMMENDATION_ENABLED
    fun averageRoiOddsCombinations(): List<String> = AverageRoiReferenceStrategy.allCombinations()
    internal fun hasAverageRoiSelection(race: RaceData): Boolean = AverageRoiReferenceStrategy.cached(race) != null
    internal fun applyAverageRoiOdds(race: RaceData, odds: Map<String, Double>, budget: Int): ValueSelection =
        AverageRoiReferenceStrategy.evaluateAndCache(race, odds, budget)

    fun valueOddsCombinations(): List<String> = valueStrategyModel?.allCombinations().orEmpty()

    fun clearValueSelections() {
        valueSelections.clear()
        AverageRoiReferenceStrategy.clear()
    }

    /** Restore only decisions recorded by this strategy; legacy records must not masquerade as value decisions. */
    internal fun restoreValueSelections(records: List<PredictionRecord>) {
        if (valueStrategyModel == null) return
        records.filter { it.strategyId == "value-v1" && it.evaluationEligible }.forEach { record ->
            val picks = if (record.recommended) {
                record.combinations.mapIndexed { index, combination ->
                    PredictionPick(
                        combination = combination,
                        score = 0.0,
                        recommendedStake = record.stakes.getOrNull(index) ?: record.stakePerPick,
                        reason = "事前に確定した買い目"
                    )
                }
            } else emptyList()
            valueSelections.putIfAbsent(
                record.id,
                ValueSelection(
                    picks = picks,
                    recommendation = record.recommendation,
                    reason = record.recommendationReason ?: "事前に確定したAI判定"
                )
            )
        }
    }

    internal fun cachedValueSelection(race: RaceData): ValueSelection? = valueSelections[race.id]

    internal fun applyValueOdds(
        race: RaceData,
        odds: Map<String, Double>,
        learningOverride: LearningProfile? = null
    ): ValueSelection? {
        val model = valueStrategyModel ?: return null
        if (odds.count { it.value > 0.0 } < 100) {
            return model.select(race, learningOverride ?: learningProfile, odds)
        }
        return valueSelections.computeIfAbsent(race.id) {
            model.select(race, learningOverride ?: learningProfile, odds)
        }
    }

    /** 内部判定用の0〜100スコア。画面には直接出さず、購入推奨/見送りへ丸める。 */
    fun confidence(race: RaceData): Int {
        val raw = rawConfidence(race)
        if (raw == 0) return 0
        val firstLane = leadingLane(race)
        val penalty = performanceProfile.penalty(race.stadiumNumber, raw, firstLane)
        return (raw + penalty).coerceIn(20, 97)
    }

    fun rawConfidence(race: RaceData): Int {
        if (race.racers.size < 3) return 0
        val scored = race.racers.map {
            it to (racerScore(it) + learningProfile.bonus(race, it))
        }.sortedByDescending { it.second }
        val leader = scored[0]
        val runnerUp = scored[1]
        val scoreGap = (leader.second - runnerUp.second).coerceAtLeast(0.0)
        val winGap = ((leader.first.nationalWinRate ?: 0.0) -
            (runnerUp.first.nationalWinRate ?: 0.0)).coerceAtLeast(0.0)
        val motorGap = ((leader.first.motorTop2 ?: 0.0) -
            (runnerUp.first.motorTop2 ?: 0.0)).coerceAtLeast(0.0)
        val startEdge = ((runnerUp.first.averageStart ?: 0.20) -
            (leader.first.averageStart ?: 0.20)).coerceAtLeast(0.0)
        val laneBonus = when (leader.first.lane) {
            1 -> 12.0
            2 -> 5.0
            3 -> 2.0
            else -> 0.0
        }
        val previewSpread = race.racers.mapNotNull { it.preview?.exhibitionTime }
            .let { times -> if (times.size >= 3) ((times.maxOrNull() ?: 0.0) - (times.minOrNull() ?: 0.0)) * 18.0 else 0.0 }
        return (32.0 + scoreGap * 2.25 + winGap * 2.8 + motorGap * 0.32 +
            startEdge * 90.0 + laneBonus + previewSpread).toInt().coerceIn(35, 97)
    }

    fun rank(race: RaceData): String = PredictionPerformanceProfile.rankFor(confidence(race))

    fun autoSkipReason(race: RaceData): String? {
        val raw = rawConfidence(race)
        if (raw == 0) return null
        return performanceProfile.autoSkipReason(race.stadiumNumber, raw, leadingLane(race))
    }

    /**
     * 購入推奨を固定保存してよいだけの直前情報が揃っているか。
     * 展示前に「見送り」を固定してしまわないため、事前予想履歴の保存側でも利用する。
     */
    fun isDecisionReady(race: RaceData): Boolean {
        if (race.racers.size != 6 || race.preview == null) return false
        val previewReady = race.racers.count { racer ->
            racer.preview?.exhibitionTime != null && racer.preview.course != null
        }
        return previewReady >= 5
    }

    fun buyThreshold(race: RaceData): Int {
        var threshold = BUY_THRESHOLD
        val wind = race.preview?.windSpeed ?: 0
        val wave = race.preview?.waveHeight ?: 0
        if (wind >= 5) threshold += 4
        if (wave >= 8) threshold += 2
        val leader = leadingLane(race)?.let { lane -> race.racers.firstOrNull { it.lane == lane } }
        if (leader?.preview?.course != null && leader.preview.course != leader.lane) threshold += 3
        return threshold.coerceAtMost(90)
    }

    fun recommendation(race: RaceData): RecommendationDecision {
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
        if (valueStrategyModel != null) {
            valueSelections[race.id]?.let { selection ->
                return RecommendationDecision(selection.recommendation, selection.reason)
            }
            if (isDecisionReady(race) && race.isPurchasable()) {
                return RecommendationDecision(
                    RaceRecommendation.SKIP,
                    "公式3連単オッズを取得して期待値を判定中"
                )
            }
        }

        if (race.racers.size < 6) {
            return RecommendationDecision(RaceRecommendation.SKIP, "6艇分の出走データが揃っていないため見送り")
        }
        if (!isDecisionReady(race)) {
            return RecommendationDecision(RaceRecommendation.SKIP, "展示・進入など直前情報が揃うまで見送り")
        }
        autoSkipReason(race)?.let { learnedReason ->
            return RecommendationDecision(RaceRecommendation.SKIP, learnedReason)
        }

        val threshold = buyThreshold(race)
        val score = confidence(race)
        return if (score >= threshold) {
            RecommendationDecision(
                RaceRecommendation.BUY,
                "選手力・コース・機力・展示・進入・蓄積実績が厳選購入基準を満たす"
            )
        } else {
            val risk = buildList {
                if ((race.preview?.windSpeed ?: 0) >= 5) add("強風")
                if ((race.preview?.waveHeight ?: 0) >= 8) add("高波")
                val leader = leadingLane(race)?.let { lane -> race.racers.firstOrNull { it.lane == lane } }
                if (leader?.preview?.course != null && leader.preview.course != leader.lane) add("進入変化")
            }
            RecommendationDecision(
                RaceRecommendation.SKIP,
                if (risk.isEmpty()) {
                    "総合評価が厳選購入基準に届かない"
                } else {
                    "${risk.joinToString("・")}を考慮すると厳選購入基準に届かない"
                }
            )
        }
    }

    fun isRecommended(race: RaceData): Boolean = recommendation(race).recommended

    fun racerScore(racer: Racer): Double {
        val laneBase = when (racer.lane) {
            1 -> 30.0
            2 -> 18.0
            3 -> 14.0
            4 -> 10.0
            5 -> 7.0
            else -> 5.0
        }
        val national = (racer.nationalWinRate ?: 0.0) * 5.2
        val local = (racer.localWinRate ?: 0.0) * 2.6
        val motor = (racer.motorTop2 ?: 0.0) * 0.22
        val boat = (racer.boatTop2 ?: 0.0) * 0.08
        val start = racer.averageStart?.let { max(0.0, (0.22 - it) * 58.0) } ?: 0.0

        val exhibition = racer.preview?.exhibitionTime?.let { max(-5.0, (6.95 - it) * 18.0) } ?: 0.0
        val previewStart = racer.preview?.startTiming?.let { max(-4.0, (0.18 - it) * 32.0) } ?: 0.0
        val course = racer.preview?.course?.let { actual ->
            when (actual) {
                1 -> 7.0
                2 -> 3.5
                3 -> 2.0
                4 -> 0.5
                5 -> -1.0
                6 -> -2.0
                else -> 0.0
            }
        } ?: 0.0

        return laneBase + national + local + motor + boat + start + exhibition + previewStart + course
    }

    /**
     * AI strategy picks. Once the promoted value model is installed, a SKIP or an
     * as-yet unevaluated race intentionally returns no picks. It must never silently
     * fall back to the legacy four-point strategy in automated/history paths.
     */
    fun predict(race: RaceData, maxPicks: Int = 4): List<PredictionPick> {
        if (valueStrategyModel == null && AverageRoiReferenceStrategy.FORECAST_ENABLED) {
            return AverageRoiReferenceStrategy.forecast(race, maxPicks)
        }
        if (valueStrategyModel != null) {
            val selection = valueSelections[race.id] ?: return emptyList()
            return if (selection.recommendation == RaceRecommendation.BUY) {
                selection.picks.take(maxPicks.coerceAtLeast(1))
            } else {
                emptyList()
            }
        }
        return legacyPrediction(race, maxPicks, BetStrategy.DEFAULT_BUDGET)
    }

    /**
     * Explicit manual override for a user who chooses to buy a race the validated
     * value strategy marked SKIP. This is never used for AI recommendation/history.
     */
    fun manualOverridePicks(
        race: RaceData,
        budget: Int = BetStrategy.DEFAULT_BUDGET,
        maxPicks: Int = 4
    ): List<PredictionPick> = legacyPrediction(race, maxPicks, budget)

    private fun legacyPrediction(race: RaceData, maxPicks: Int, budget: Int): List<PredictionPick> {
        if (race.racers.size < 3) return emptyList()
        val scores = race.racers.associate {
            it.lane to (racerScore(it) + learningProfile.bonus(race, it))
        }
        val picks = mutableListOf<PredictionPick>()

        for (first in 1..6) {
            if (scores[first] == null) continue
            for (second in 1..6) {
                if (second == first || scores[second] == null) continue
                for (third in 1..6) {
                    if (third == first || third == second || scores[third] == null) continue
                    val firstScore = scores.getValue(first)
                    val secondScore = scores.getValue(second)
                    val thirdScore = scores.getValue(third)
                    val orderScore = firstScore * 1.00 + secondScore * 0.58 + thirdScore * 0.31
                    picks += PredictionPick("$first-$second-$third", orderScore)
                }
            }
        }

        return BetStrategy.allocate(
            race,
            picks.sortedByDescending { it.score }.take(maxPicks.coerceAtLeast(1)),
            budget
        )
    }

    fun withOdds(
        race: RaceData,
        picks: List<PredictionPick>,
        odds: Map<String, Double>,
        budget: Int = BetStrategy.DEFAULT_BUDGET,
        learningOverride: LearningProfile? = null
    ): List<PredictionPick> {
        if (valueStrategyModel == null && AverageRoiReferenceStrategy.FORECAST_ENABLED) {
            val count = picks.size.coerceAtLeast(1)
            val forecast = AverageRoiReferenceStrategy.forecast(race, count)
                .map { pick -> pick.copy(odds = odds[pick.combination]) }
            return BetStrategy.allocate(race, forecast, budget)
        }
        if (valueStrategyModel != null) {
            val valueSelection = applyValueOdds(race, odds, learningOverride) ?: return emptyList()
            return if (valueSelection.recommendation == RaceRecommendation.BUY) {
                BetStrategy.allocate(race, valueSelection.picks, budget)
            } else {
                emptyList()
            }
        }
        return BetStrategy.allocate(
            race,
            picks.map { it.copy(odds = odds[it.combination]) },
            budget
        )
    }

    fun missReason(race: RaceData, combinations: List<String>): String? {
        val result = race.result?.trifectaCombination ?: return null
        if (result in combinations) return null
        val predictedFirst = combinations.firstOrNull()?.substringBefore("-")
        val actualFirst = result.substringBefore("-")
        val actualWinner = actualFirst.toIntOrNull()?.let { lane -> race.racers.firstOrNull { it.lane == lane } }
        val courseChanged = actualWinner?.preview?.course?.let { it != actualWinner.lane } == true
        return when {
            race.preview == null -> "展示・直前情報が未取得の状態で予想"
            courseChanged -> "進入変化があり、会場・風速帯・実進入コースの傾向へ学習"
            (race.preview.windSpeed ?: 0) >= 5 -> "強風で通常と異なる展開。風速帯別コース傾向へ学習"
            predictedFirst != actualFirst -> "1着候補の評価を外したため、会場別コース成績へ学習"
            else -> "1着は一致、2・3着の順序評価を外した"
        }
    }

    private fun leadingLane(race: RaceData): Int? = race.racers
        .maxByOrNull { racerScore(it) + learningProfile.bonus(race, it) }
        ?.lane
}
