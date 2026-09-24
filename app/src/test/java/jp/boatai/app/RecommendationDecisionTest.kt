package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Test

class RecommendationDecisionTest {
    @Test
    fun strongRaceStillHasForecastWhileAutoPurchaseIsPaused() {
        resetProfiles()
        val race = race(
            racers = listOf(
                racer(1, 8.0, 8.0, 50.0, 0.12, 6.70),
                racer(2, 4.5, 4.0, 25.0, 0.18, 6.84),
                racer(3, 4.2, 4.0, 25.0, 0.18, 6.86),
                racer(4, 4.0, 3.8, 24.0, 0.19, 6.88),
                racer(5, 3.8, 3.6, 23.0, 0.19, 6.90),
                racer(6, 3.5, 3.4, 22.0, 0.20, 6.92)
            )
        )

        assertEquals(RaceRecommendation.SKIP, PredictionEngine.recommendation(race).recommendation)
        check(PredictionEngine.predict(race).isNotEmpty())
    }

    @Test
    fun missingPreviewIsSkipRecommendation() {
        resetProfiles()
        val race = race(
            racers = (1..6).map { lane -> racer(lane, 7.0, 6.5, 40.0, 0.14, null) },
            preview = null
        )

        assertEquals(RaceRecommendation.SKIP, PredictionEngine.recommendation(race).recommendation)
    }

    @Test
    fun lowAdvantageRaceIsSkipRecommendation() {
        resetProfiles()
        val race = race(
            racers = listOf(
                racer(1, 4.8, 4.5, 30.0, 0.18, 6.84),
                racer(2, 5.0, 5.0, 31.0, 0.17, 6.83),
                racer(3, 5.0, 5.0, 30.0, 0.17, 6.84),
                racer(4, 4.9, 4.8, 30.0, 0.18, 6.85),
                racer(5, 4.8, 4.7, 29.0, 0.18, 6.86),
                racer(6, 4.7, 4.6, 28.0, 0.19, 6.87)
            )
        )

        assertEquals(RaceRecommendation.SKIP, PredictionEngine.recommendation(race).recommendation)
    }

    private fun resetProfiles() {
        PredictionEngine.installLearningProfile(LearningProfile())
        PredictionEngine.installPersistentPerformanceProfile(PredictionPerformanceProfile())
        PredictionEngine.installPerformanceProfile(PredictionPerformanceProfile())
    }

    private fun race(
        racers: List<Racer>,
        preview: PreviewData? = PreviewData(
            windSpeed = 2,
            windDirection = "北",
            waveHeight = 2,
            weather = "晴",
            airTemperature = 25.0,
            waterTemperature = 24.0
        )
    ) = RaceData(
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
        preview = preview,
        result = null
    )

    private fun racer(
        lane: Int,
        national: Double,
        local: Double,
        motor: Double,
        start: Double,
        exhibition: Double?
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
        preview = exhibition?.let {
            PreviewRacer(
                course = lane,
                startTiming = start,
                weight = null,
                weightAdjustment = null,
                exhibitionTime = it,
                tilt = 0.0
            )
        }
    )
}
