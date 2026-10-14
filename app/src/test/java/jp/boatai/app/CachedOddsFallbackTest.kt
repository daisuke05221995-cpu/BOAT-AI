package jp.boatai.app

import java.time.LocalDateTime
import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class CachedOddsFallbackTest {
    @Test
    fun popularOddsAreConservativelyReducedWhenSnapshotIsStale() {
        val observed = linkedMapOf(
            "1-2-3" to 10.0,
            "1-2-4" to 12.0,
            "1-3-2" to 15.0,
            "2-1-3" to 20.0,
            "2-1-4" to 30.0
        )

        val estimated = StartOddsEstimator.estimate(observed, minutesBeforeClose = 8.0)

        assertEquals(9.2, estimated.getValue("1-2-3"), 0.0001)
        assertEquals(10.3, estimated.getValue("1-2-4"), 0.0001)
        assertEquals(12.9, estimated.getValue("1-3-2"), 0.0001)
    }

    @Test
    fun nearCloseSnapshotGetsOnlySmallCorrection() {
        val observed = linkedMapOf("1-2-3" to 10.0)
        val estimated = StartOddsEstimator.estimate(observed, minutesBeforeClose = 2.0)

        assertEquals(9.8, estimated.getValue("1-2-3"), 0.0001)
    }

    @Test
    fun parserFinds120WayRaceAndKeepsOriginalFetchTime() {
        val race = race()
        val combinations = buildList {
            for (a in 1..6) for (b in 1..6) for (c in 1..6) {
                if (a != b && a != c && b != c) add("$a-$b-$c")
            }
        }
        val header = buildString {
            append("レースコード,レース日,レース場,レース回,締切時刻,取得日時")
            combinations.forEach { append(",3連単_").append(it) }
        }
        val row = buildString {
            append("202610142201,2026-10-14,22,01R,12:10,2026-10-14T12:04:00+09:00")
            combinations.forEachIndexed { index, _ -> append(",").append(5.0 + index) }
        }

        val snapshot = BoatraceCsvOddsFallback.parseRaceSnapshot("$header\n$row\n", race)

        assertNotNull(snapshot)
        requireNotNull(snapshot)
        assertEquals(120, snapshot.observedOdds.size)
        assertEquals(120, snapshot.estimatedOdds.size)
        assertTrue(snapshot.minutesBeforeClose in 5.9..6.1)
        val expected = LocalDateTime.of(2026, 10, 14, 12, 4)
            .atZone(ZoneId.of("Asia/Tokyo"))
            .toInstant()
            .toEpochMilli()
        assertEquals(expected, snapshot.fetchedAt)
    }

    private fun race() = RaceData(
        date = "2026-10-14",
        stadiumNumber = 22,
        raceNumber = 1,
        closedAt = "12:10",
        gradeNumber = null,
        title = "",
        subtitle = "",
        distance = null,
        dayNumber = null,
        racers = emptyList(),
        preview = null,
        result = null
    )
}
