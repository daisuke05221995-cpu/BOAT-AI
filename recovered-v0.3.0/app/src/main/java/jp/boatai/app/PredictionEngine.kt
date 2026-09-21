package jp.boatai.app

import kotlin.math.max

object PredictionEngine {
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
        val scores = race.racers.associate { it.lane to racerScore(it) }
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

        return picks.sortedByDescending { it.score }.take(maxPicks)
    }

    fun withOdds(picks: List<PredictionPick>, odds: Map<String, Double>): List<PredictionPick> =
        picks.map { it.copy(odds = odds[it.combination]) }
}
