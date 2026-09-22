package jp.boatai.app

import kotlin.math.max

object PredictionEngine {
    const val BUY_THRESHOLD = 70

    @Volatile private var learningProfile = LearningProfile()
    @Volatile private var persistentPerformanceProfile = PredictionPerformanceProfile()
    @Volatile private var performanceProfile = PredictionPerformanceProfile()

    fun installLearningProfile(profile: LearningProfile) {
        learningProfile = profile
    }

    fun installPersistentPerformanceProfile(profile: PredictionPerformanceProfile) {
        persistentPerformanceProfile = profile
    }

    fun installPerformanceProfile(profile: PredictionPerformanceProfile) {
        performanceProfile = persistentPerformanceProfile.mergedWith(profile)
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

    fun recommendation(race: RaceData): RecommendationDecision {
        if (race.racers.size < 3) {
            return RecommendationDecision(RaceRecommendation.SKIP, "予想に必要な出走データが不足")
        }
        autoSkipReason(race)?.let { learnedReason ->
            return RecommendationDecision(RaceRecommendation.SKIP, learnedReason)
        }
        return if (confidence(race) >= BUY_THRESHOLD) {
            RecommendationDecision(
                RaceRecommendation.BUY,
                "選手力・コース・機力・直前情報と蓄積実績が購入基準を満たす"
            )
        } else {
            RecommendationDecision(
                RaceRecommendation.SKIP,
                "総合評価が購入基準に届かない"
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

    fun predict(race: RaceData, maxPicks: Int = 4): List<PredictionPick> {
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

        return BetStrategy.allocate(race, picks.sortedByDescending { it.score }.take(maxPicks), BetStrategy.DEFAULT_BUDGET)
    }

    fun withOdds(
        race: RaceData,
        picks: List<PredictionPick>,
        odds: Map<String, Double>,
        budget: Int = BetStrategy.DEFAULT_BUDGET
    ): List<PredictionPick> = BetStrategy.allocate(
        race,
        picks.map { it.copy(odds = odds[it.combination]) },
        budget
    )

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
