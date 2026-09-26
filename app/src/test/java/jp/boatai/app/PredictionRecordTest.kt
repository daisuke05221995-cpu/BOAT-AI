package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PredictionRecordTest {
    @Test
    fun hitRecordCalculatesSimulatedPayoutAndProfit() {
        val record = PredictionRecord(
            id = "2026-09-22-01-1",
            date = "2026-09-22",
            stadiumNumber = 1,
            raceNumber = 1,
            combinations = listOf("1-2-3", "1-3-2", "1-2-4", "1-4-2"),
            stakePerPick = 300,
            resultCombination = "1-3-2",
            trifectaPayout = 2450,
            settled = true,
            createdAt = 1L
        )

        assertTrue(record.hit)
        assertEquals(1200, record.simulatedStake)
        assertEquals(7350, record.simulatedPayout)
        assertEquals(6150, record.simulatedProfit)
    }

    @Test
    fun missRecordReturnsZeroPayout() {
        val record = PredictionRecord(
            id = "2026-09-22-01-2",
            date = "2026-09-22",
            stadiumNumber = 1,
            raceNumber = 2,
            combinations = listOf("1-2-3", "1-3-2", "1-2-4", "1-4-2"),
            stakePerPick = 300,
            resultCombination = "2-1-3",
            trifectaPayout = 5000,
            settled = true,
            createdAt = 2L
        )

        assertFalse(record.hit)
        assertEquals(0, record.simulatedPayout)
        assertEquals(-1200, record.simulatedProfit)
    }

    @Test
    fun jsonRoundTripKeepsPredictionData() {
        val original = PredictionRecord(
            id = "2026-09-22-02-3",
            date = "2026-09-22",
            stadiumNumber = 2,
            raceNumber = 3,
            combinations = listOf("1-2-3", "1-3-2"),
            stakePerPick = 500,
            resultCombination = null,
            trifectaPayout = 0,
            settled = false,
            createdAt = 1234L
        )

        val restored = PredictionRecord.fromJson(original.toJson())
        assertEquals(original, restored)
    }

    @Test
    fun valueStrategyKeepsPerCombinationStakesForVirtualPayout() {
        val record = PredictionRecord(
            id = "2026-09-23-01-1", date = "2026-09-23", stadiumNumber = 1, raceNumber = 1,
            combinations = listOf("1-2-3", "1-3-2", "2-1-3"), stakePerPick = 300,
            resultCombination = "1-3-2", trifectaPayout = 2_450, settled = true,
            createdAt = 3L, stakes = listOf(500, 600, 100)
        )

        assertEquals(1_200, record.simulatedStake)
        assertEquals(14_700, record.simulatedPayout)
        assertEquals(13_500, record.simulatedProfit)
        assertEquals(record, PredictionRecord.fromJson(record.toJson()))
    }
    @Test
    fun jsonRoundTripKeepsLiveOddsAuditSnapshot() {
        val record = PredictionRecord(
            id = "2026-09-26-01-8",
            date = "2026-09-26",
            stadiumNumber = 1,
            raceNumber = 8,
            combinations = listOf("1-2-3", "1-3-2"),
            stakePerPick = 500,
            resultCombination = null,
            trifectaPayout = 0,
            settled = false,
            createdAt = 99L,
            recommended = true,
            stakes = listOf(600, 400),
            strategyId = "value-v1",
            liveOddsFetchedAt = 1_797_000_000_000L,
            liveOddsSource = "公式PC版",
            liveOddsCount = 120,
            livePickOdds = listOf(12.4, 18.7)
        )

        val restored = PredictionRecord.fromJson(record.toJson())
        assertEquals(record, restored)
    }

    @Test
    fun legacyJsonKeepsLiveOddsAuditDefaultsEmpty() {
        val original = PredictionRecord(
            id = "2026-09-20-02-4",
            date = "2026-09-20",
            stadiumNumber = 2,
            raceNumber = 4,
            combinations = listOf("1-2-3"),
            stakePerPick = 300,
            resultCombination = null,
            trifectaPayout = 0,
            settled = false,
            createdAt = 1L
        )
        val json = original.toJson().apply {
            remove("liveOddsFetchedAt")
            remove("liveOddsSource")
            remove("liveOddsCount")
            remove("livePickOdds")
        }

        val restored = PredictionRecord.fromJson(json)
        assertEquals(null, restored.liveOddsFetchedAt)
        assertEquals(null, restored.liveOddsSource)
        assertEquals(0, restored.liveOddsCount)
        assertTrue(restored.livePickOdds.isEmpty())
    }

}
