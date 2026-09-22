package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Test

class RecommendationDecisionTest {
    @Test
    fun strongRaceIsBuyRecommendation() {
        resetProfiles()
        val race = race(
            racers = listOf(
                racer(1, 8.0, 8.0, 50.0, 0.12),
                racer(2, 4.5, 4.0, 25.0, 0.18),
                racer(3, 4.2, 4.0, 25.0, 0.18)
            )
        )

        assertEquals(RaceRecommendation.BUY, PredictionEngine.recommendation(race).recommendation)
    }

    @Test
    fun lowAdvantageRaceIsSkipRecommendation() {
        resetProfiles()
        val race = race(
            racers = listOf(
                racer(1, 0.0, 0.0, 0.0, 0.22),
                racer(2, 5.0, 5.0, 30.0, 0.16),
                racer(3, 5.0, 5.0, 30.0, 0.16)
            )
        )

        assertEquals(RaceRecommendation.SKIP, PredictionEngine.recommendation(race).recommendation)
    }

    private fun resetProfiles() {
        PredictionEngine.installLearningProfile(LearningProfile())
        PredictionEngine.installPersistentPerformanceProfile(PredictionPerformanceProfile())
        PredictionEngine.installPerformanceProfile(PredictionPerformanceProfile())
    }

    private fun race(racers: List<Racer>) = RaceData(
        date = "2026-09-22",
        stadiumNumber = 1,
        raceNumber = 1,
        closedAt = "23:59",
        gradeNumber = null,
        title = "test",
        subtitle = "",
        distance = 1800,
        dayNumber = 1,
        racers = racers,
        preview = null,
        result = null
    )

    private fun racer(
        lane: Int,
        national: Double,
        local: Double,
        motor: Double,
        start: Double
    ) = Racer(
        lane = lane,
        name = "R$lane",
        registrationNumber = lane,
        rank = "A1",
        branch = null,
        age = null,
        weight = null,
        averageStart = start,
        nationalWinRate = national,
        nationalTop2 = null,
        nationalTop3 = null,
        localWinRate = local,
        localTop2 = null,
        localTop3 = null,
        motorNumber = null,
        motorTop2 = motor,
        motorTop3 = null,
        boatNumber = null,
        boatTop2 = 30.0,
        boatTop3 = null,
        preview = null
    )
}
