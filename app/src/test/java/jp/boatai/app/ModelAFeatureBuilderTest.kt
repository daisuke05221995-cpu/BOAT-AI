package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class ModelAFeatureBuilderTest {
    @Test
    fun buildsFrozenCurrentHistoryReactionAndGlobalShapes() {
        val date = LocalDate.of(2026, 9, 24)
        val day = ModelAFeatureBuilder.pythonOrdinal(date)
        val history = ModelAPlayerHistory(ModelAPlayerHistory.State(lastDay = day - 1))
        val result = ModelAFeatureBuilder(history).build(race(date))

        assertTrue(result.usable)
        assertTrue(result.historyFreshForDay)
        assertEquals(day, result.predictionDayOrdinal)
        assertEquals(day - 1, result.historyThroughDayOrdinal)
        assertEquals(6, result.laneHistory.size)
        val input = requireNotNull(result.input)
        assertEquals(6, input.boat.size)
        input.boat.forEach { assertEquals(82, it.size) }
        assertEquals(24, input.global.size)

        val lane1 = input.boat[0]
        assertEquals(f32(7.10), lane1[0], 0.0)
        assertEquals(f32(6.10), lane1[1], 0.0)
        assertEquals(f32(0.0), lane1[11], 0.0)
        assertEquals(f32(0.0), lane1[12], 0.0)
        assertEquals(f32(30.0), lane1[13], 0.0)
        assertEquals(f32(52.0), lane1[14], 0.0)
        assertEquals(f32(6.70), lane1[15], 0.0)
        assertEquals(f32(0.10), lane1[16], 0.0)
        assertEquals(f32(1.0), lane1[17], 0.0)
        assertEquals(f32(1.0), lane1[20], 0.0)
        assertEquals(f32(0.0), lane1[21], 0.0)
        assertEquals(f32(0.0), lane1[24], 0.0)
        assertEquals(f32(1.0), lane1[25], 0.0)
        assertEquals(f32(1.0), lane1[26], 0.0)
        assertEquals(f32(0.0), lane1[27], 0.0)
        assertEquals(f32(-0.05), lane1[28], 1e-6)
        assertEquals(f32(0.0), lane1[29], 0.0)

        assertEquals(f32(0.0), lane1[30], 0.0)
        assertEquals(f32(1.0 / 6.0), lane1[31], 0.0)
        assertEquals(f32(6.8), lane1[38], 0.0)
        assertEquals(f32(6.70 - 6.8), lane1[62], 1e-6)

        assertEquals(f32(3.0), input.global[0], 0.0)
        assertEquals(f32(4.0), input.global[1], 0.0)
        assertEquals(f32(25.5), input.global[2], 0.0)
        assertEquals(f32(24.0), input.global[3], 0.0)
        for (direction in 1..16) {
            assertEquals(if (direction == 3) 1.0 else 0.0, input.global[3 + direction], 0.0)
        }
        assertEquals(12.0, input.global[22], 0.0)
        assertEquals(7.0, input.global[23], 0.0)
        assertTrue(input.global.all { it.isFinite() })
    }

    @Test
    fun staleHistoryIsExplicitlyMarkedAndNeverPretendsToBeFresh() {
        val date = LocalDate.of(2026, 9, 24)
        val history = ModelAPlayerHistory(ModelAPlayerHistory.State(lastDay = ModelAFeatureBuilder.pythonOrdinal(date) - 10))
        val result = ModelAFeatureBuilder(history).build(race(date))

        assertTrue(result.usable)
        assertFalse(result.historyFreshForDay)
        assertNotNull(result.input)
    }

    @Test
    fun missingRequiredPreviewInputMakesRaceUnusable() {
        val date = LocalDate.of(2026, 9, 24)
        val day = ModelAFeatureBuilder.pythonOrdinal(date)
        val history = ModelAPlayerHistory(ModelAPlayerHistory.State(lastDay = day - 1))
        val race = race(date)
        val broken = race.copy(
            racers = race.racers.map { racer ->
                if (racer.lane == 4) racer.copy(preview = racer.preview?.copy(exhibitionTime = null)) else racer
            }
        )

        val result = ModelAFeatureBuilder(history).build(broken)
        assertFalse(result.usable)
        assertNull(result.input)
        assertEquals("Missing required Model A pre-race input", result.reason)
    }

    @Test
    fun previewCoursesMustBePermutationOneThroughSix() {
        val date = LocalDate.of(2026, 9, 24)
        val day = ModelAFeatureBuilder.pythonOrdinal(date)
        val history = ModelAPlayerHistory(ModelAPlayerHistory.State(lastDay = day - 1))
        val race = race(date)
        val broken = race.copy(
            racers = race.racers.map { racer ->
                if (racer.lane == 6) racer.copy(preview = racer.preview?.copy(course = 5)) else racer
            }
        )

        val result = ModelAFeatureBuilder(history).build(broken)
        assertFalse(result.usable)
        assertNull(result.input)
    }

    private fun race(date: LocalDate): RaceData = RaceData(
        date = date.toString(),
        stadiumNumber = 12,
        raceNumber = 7,
        closedAt = "${date} 17:00:00",
        gradeNumber = 3,
        title = "test",
        subtitle = "",
        distance = 1800,
        dayNumber = 1,
        racers = (1..6).map { lane ->
            Racer(
                lane = lane,
                name = "R$lane",
                registrationNumber = 5000 + lane,
                rank = when (lane) { 1 -> "A1"; 2 -> "A2"; 3, 4 -> "B1"; else -> "B2" },
                branch = "1",
                age = 29 + lane,
                weight = 51.0 + lane,
                averageStart = 0.14 + lane * 0.005,
                nationalWinRate = 7.0 + lane * 0.1,
                nationalTop2 = 40.0 + lane,
                nationalTop3 = 60.0 + lane,
                localWinRate = 6.0 + lane * 0.1,
                localTop2 = 35.0 + lane,
                localTop3 = 55.0 + lane,
                motorNumber = 10 + lane,
                motorTop2 = 30.0 + lane,
                motorTop3 = 50.0 + lane,
                boatNumber = 20 + lane,
                boatTop2 = 28.0 + lane,
                boatTop3 = 48.0 + lane,
                preview = PreviewRacer(
                    course = lane,
                    startTiming = 0.08 + lane * 0.02,
                    weight = 51.0 + lane,
                    weightAdjustment = 0.0,
                    exhibitionTime = 6.69 + lane * 0.01,
                    tilt = 0.0
                ),
                classNumber = when (lane) { 1 -> 1; 2 -> 2; 3, 4 -> 3; else -> 4 },
                flyingCount = if (lane == 6) 1 else 0,
                lateCount = 0
            )
        },
        preview = PreviewData(
            windSpeed = 3,
            windDirection = "北東",
            waveHeight = 4,
            weather = "晴",
            airTemperature = 25.5,
            waterTemperature = 24.0,
            windDirectionNumber = 3
        ),
        result = null
    )

    private fun f32(value: Double): Double = value.toFloat().toDouble()
}
