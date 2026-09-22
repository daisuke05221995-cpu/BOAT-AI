package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LearningProfileTest {
    @Test
    fun windBucketGroupsExpectedRanges() {
        assertEquals("0-2", LearningProfile.windBucket(0))
        assertEquals("0-2", LearningProfile.windBucket(2))
        assertEquals("3-4", LearningProfile.windBucket(3))
        assertEquals("3-4", LearningProfile.windBucket(4))
        assertEquals("5+", LearningProfile.windBucket(5))
        assertEquals("5+", LearningProfile.windBucket(9))
    }

    @Test
    fun contextualBonusUsesActualCourseWhenEnoughSamplesExist() {
        val key = LearningProfile.windCourseKey(stadium = 2, windSpeed = 5, course = 2)
        val profile = LearningProfile(
            windCourseStarts = mapOf(key to 20),
            windCourseWins = mapOf(key to 8)
        )
        val racer = Racer(
            lane = 4,
            name = "test",
            registrationNumber = null,
            rank = "A1",
            branch = null,
            age = null,
            weight = null,
            averageStart = null,
            nationalWinRate = null,
            nationalTop2 = null,
            nationalTop3 = null,
            localWinRate = null,
            localTop2 = null,
            localTop3 = null,
            motorNumber = null,
            motorTop2 = null,
            motorTop3 = null,
            boatNumber = null,
            boatTop2 = null,
            boatTop3 = null,
            preview = PreviewRacer(
                course = 2,
                startTiming = null,
                weight = null,
                weightAdjustment = null,
                exhibitionTime = null,
                tilt = null
            )
        )
        val race = RaceData(
            date = "2026-09-22",
            stadiumNumber = 2,
            raceNumber = 1,
            closedAt = "12:00",
            gradeNumber = null,
            title = "test",
            subtitle = "",
            distance = 1800,
            dayNumber = 1,
            racers = listOf(racer),
            preview = PreviewData(
                windSpeed = 5,
                windDirection = null,
                waveHeight = null,
                weather = null,
                airTemperature = null,
                waterTemperature = null
            ),
            result = null
        )

        assertTrue(profile.bonus(race, racer) > profile.bonus(race.stadiumNumber, racer.lane))
    }
}
