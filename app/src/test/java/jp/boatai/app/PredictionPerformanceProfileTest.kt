package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PredictionPerformanceProfileTest {
    @Test
    fun excludesPredictionsCapturedAfterResultFromEvaluation() {
        val profile = PredictionPerformanceProfile.from(
            listOf(
                record(id = "eligible", eligible = true, hit = true),
                record(id = "ineligible", eligible = false, hit = true)
            )
        )

        assertEquals(1, profile.overall.races)
        assertEquals(1, profile.overall.hits)
    }

    @Test
    fun poorRepeatedContextCreatesPenaltyAndAutoSkip() {
        val records = (1..30).map { index ->
            record(id = "miss-$index", eligible = true, hit = false, venue = 2, rank = "A", confidence = 84, firstLane = 1)
        }
        val profile = PredictionPerformanceProfile.from(records)

        assertTrue(profile.penalty(2, 84, 1) < 0)
        assertNotNull(profile.autoSkipReason(2, 84, 1))
        assertTrue(profile.weakConditions().isNotEmpty())
    }

    @Test
    fun profitableContextIsNotPenalized() {
        val records = (1..30).map { index ->
            record(id = "hit-$index", eligible = true, hit = true, venue = 6, rank = "A", confidence = 84, firstLane = 1)
        }
        val profile = PredictionPerformanceProfile.from(records)

        assertEquals(0, profile.penalty(6, 84, 1))
        assertNull(profile.autoSkipReason(6, 84, 1))
    }

    @Test
    fun mergingProfilesKeepsPreviousAndCurrentVersionSamples() {
        val previous = PredictionPerformanceProfile.from(
            (1..20).map { index ->
                record(id = "old-$index", eligible = true, hit = false, venue = 2, rank = "A", confidence = 84, firstLane = 1)
            }
        )
        val current = PredictionPerformanceProfile.from(
            (1..10).map { index ->
                record(id = "new-$index", eligible = true, hit = true, venue = 2, rank = "A", confidence = 84, firstLane = 1)
            }
        )

        val merged = previous.mergedWith(current)

        assertEquals(30, merged.overall.races)
        assertEquals(10, merged.overall.hits)
        assertEquals(30, merged.byVenue.getValue(2).races)
        assertEquals(30, merged.byContext.getValue("2:A:1").races)
    }

    private fun record(
        id: String,
        eligible: Boolean,
        hit: Boolean,
        venue: Int = 1,
        rank: String = "A",
        confidence: Int = 84,
        firstLane: Int = 1
    ): PredictionRecord = PredictionRecord(
        id = id,
        date = "2026-09-22",
        stadiumNumber = venue,
        raceNumber = 1,
        combinations = listOf("1-2-3", "1-3-2", "1-2-4", "1-4-2"),
        stakePerPick = 300,
        resultCombination = if (hit) "1-2-3" else "2-1-3",
        trifectaPayout = if (hit) 2000 else 5000,
        settled = true,
        createdAt = 1L,
        confidence = confidence,
        rank = rank,
        firstLane = firstLane,
        evaluationEligible = eligible
    )
}
