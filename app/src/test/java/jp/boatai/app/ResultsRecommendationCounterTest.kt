package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ResultsRecommendationCounterTest {
    @Test
    fun countsOnlyRecommendedRacesAndRecommendedHits() {
        val results = (1..5).map { race(it, "1-2-3") }
        val records = listOf(
            prediction(1, recommended = true, combinations = listOf("1-2-3")),
            prediction(2, recommended = true, combinations = listOf("2-1-3")),
            prediction(3, recommended = false, combinations = listOf("1-2-3")),
            prediction(4, recommended = false, combinations = emptyList()),
            prediction(5, recommended = true, combinations = listOf("1-2-3"), eligible = false)
        ).associateBy { it.id }

        val summary = ResultsRecommendationCounter.count(results, records)

        assertEquals(2, summary.recommended)
        assertEquals(1, summary.hits)
        assertFalse(ResultsRecommendationCounter.isHit(results[2], records[results[2].id]))
    }

    @Test
    fun usesConfirmedRaceResultEvenBeforeHistorySettlement() {
        val result = race(1, "1-2-3")
        val stored = prediction(1, recommended = true, combinations = listOf("1-2-3"))
        assertFalse(stored.settled)

        assertTrue(ResultsRecommendationCounter.isHit(result, stored))
        assertEquals(RecommendedResultCount(1, 1), ResultsRecommendationCounter.count(listOf(result), mapOf(stored.id to stored)))
    }

    @Test
    fun ignoresUnconfirmedRacesAndDoesNotIncludeRetrospectiveRecords() {
        val confirmed = race(1, "1-2-3")
        val pending = race(2, null)
        val virtualRecord = prediction(1, recommended = true, combinations = listOf("1-2-3"))
            .copy(strategyId = ModelARecentVirtualRepository.STRATEGY_ID)
        val pendingRecord = prediction(2, recommended = true, combinations = listOf("1-2-3"))

        assertEquals(RecommendedResultCount(0, 0), ResultsRecommendationCounter.count(listOf(confirmed), mapOf(virtualRecord.id to virtualRecord)))
        assertEquals(RecommendedResultCount(0, 0), ResultsRecommendationCounter.count(listOf(pending), mapOf(pendingRecord.id to pendingRecord)))
        assertEquals(RecommendedResultCount(0, 0), ResultsRecommendationCounter.count(listOf(confirmed), emptyMap()))
    }

    private fun race(number: Int, result: String?) = RaceData(
        date = "2026-10-27", stadiumNumber = 1, raceNumber = number, closedAt = "12:00",
        gradeNumber = null, title = "", subtitle = "", distance = null, dayNumber = null,
        racers = emptyList(), preview = null,
        result = result?.let { RaceResultData(it, 1000, null) }
    )

    private fun prediction(number: Int, recommended: Boolean, combinations: List<String>, eligible: Boolean = true) = PredictionRecord(
        id = "2026-10-27-01-$number", date = "2026-10-27", stadiumNumber = 1, raceNumber = number,
        combinations = combinations, stakePerPick = 300, resultCombination = null,
        trifectaPayout = 0, settled = false, createdAt = 1L,
        evaluationEligible = eligible, recommended = recommended
    )
}
