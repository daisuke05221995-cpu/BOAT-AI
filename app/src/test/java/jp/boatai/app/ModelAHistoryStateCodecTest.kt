package jp.boatai.app

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelAHistoryStateCodecTest {
    @Test
    fun roundTripPreservesExactStateAndFutureSnapshots() {
        val history = ModelAPlayerHistory()
        for (day in listOf(1, 4, 35, 70)) {
            val snapshots = (0 until 6).map { lane ->
                history.snapshot(
                    player = 8000 + lane,
                    course = ((lane + day) % 6) + 1,
                    racerClass = 1 + ((lane + day) % 4),
                    exhibitionTime = 6.65 + lane * 0.02,
                    previewStartTiming = 0.11 + lane * 0.01,
                    courseChanged = lane == day % 6,
                    day = day
                )
            }
            history.commitDay(
                day,
                snapshots.mapIndexed { lane, snapshot ->
                    val rank = (lane + day) % 6
                    ModelAPlayerHistory.OutcomeUpdate(
                        player = 8000 + lane,
                        course = ((lane + day) % 6) + 1,
                        racerClass = 1 + ((lane + day) % 4),
                        exhibitionTime = 6.65 + lane * 0.02,
                        previewStartTiming = 0.11 + lane * 0.01,
                        win = rank == 0,
                        top2 = rank < 2,
                        top3 = rank < 3,
                        flags = snapshot.flags
                    )
                }
            )
        }

        val original = history.exportState()
        val bytes = ModelAHistoryStateCodec.encode(original)
        val decoded = ModelAHistoryStateCodec.decode(bytes)
        val reloaded = ModelAPlayerHistory(decoded)

        assertEquals(original.lastDay, decoded.lastDay)
        assertEquals(original.updateRaces, decoded.updateRaces)
        assertEquals(original.stats.keys, decoded.stats.keys)
        assertEquals(original.recent.keys, decoded.recent.keys)
        for (key in original.stats.keys) {
            assertArrayEquals(original.stats.getValue(key), decoded.stats.getValue(key), 0.0)
        }
        for (player in original.recent.keys) {
            val before = original.recent.getValue(player)
            val after = decoded.recent.getValue(player)
            assertEquals(before.days, after.days)
            assertEquals(before.cumulative.size, after.cumulative.size)
            before.cumulative.indices.forEach { index ->
                assertArrayEquals(before.cumulative[index], after.cumulative[index])
            }
        }

        val originalNext = history.snapshot(8000, 5, 3, 6.72, 0.13, false, 71)
        val decodedNext = reloaded.snapshot(8000, 5, 3, 6.72, 0.13, false, 71)
        assertArrayEquals(originalNext.history, decodedNext.history, 0.0)
        assertArrayEquals(originalNext.reaction, decodedNext.reaction, 0.0)
        assertEquals(originalNext.flags, decodedNext.flags)
    }

    @Test
    fun recentEncodingIsMuchSmallerThanNaiveCumulativeTriples() {
        val state = ModelAPlayerHistory.State(lastDay = 1000, updateRaces = 500)
        val recent = ModelAPlayerHistory.Recent()
        var counts = intArrayOf(0, 0, 0)
        repeat(1000) { index ->
            recent.days += index + 1
            val rank = index % 6
            val delta = intArrayOf(if (rank == 0) 1 else 0, if (rank < 2) 1 else 0, if (rank < 3) 1 else 0)
            counts = IntArray(3) { metric -> counts[metric] + delta[metric] }
            recent.cumulative += counts.copyOf()
        }
        state.recent["9999"] = recent

        val bytes = ModelAHistoryStateCodec.encode(state)
        val naiveRecentPayload = 1000 * (4 + 3 * 4)
        assertTrue("compact=${bytes.size} naive=$naiveRecentPayload", bytes.size < naiveRecentPayload / 3)

        val metadata = ModelAHistoryStateCodec.metadata(bytes, state)
        assertEquals(1000, metadata.appearances)
        assertEquals(1, metadata.players)
        assertEquals(1000, metadata.lastDay)
    }
}
