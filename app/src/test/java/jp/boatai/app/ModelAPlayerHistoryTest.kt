package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelAPlayerHistoryTest {
    @Test
    fun freshSnapshotMatchesFrozenPythonPriors() {
        val history = ModelAPlayerHistory()
        val snapshot = history.snapshot(
            player = 1001,
            course = 1,
            racerClass = 3,
            exhibitionTime = 6.70,
            previewStartTiming = 0.15,
            courseChanged = false,
            day = 1
        )

        assertEquals(32, snapshot.history.size)
        assertEquals(20, snapshot.reaction.size)
        assertEquals(0.0, snapshot.history[0], 0.0)
        assertEquals(1.0 / 6.0, snapshot.history[1], 1e-6)
        assertEquals(1.0 / 3.0, snapshot.history[2], 1e-6)
        assertEquals(1.0 / 2.0, snapshot.history[3], 1e-6)
        assertEquals(0.0, snapshot.history[4], 0.0)
        assertEquals(6.8, snapshot.history[8], 1e-6)
        assertEquals(0.15, snapshot.history[9], 1e-6)
        assertEquals(0.17, snapshot.history[10], 1e-6)
        assertEquals(0.08, snapshot.history[11], 1e-6)
        assertEquals(0.0, snapshot.history[16], 0.0)
        assertEquals(0.0, snapshot.history[20], 0.0)
        assertEquals(0.0, snapshot.history[24], 0.0)
        assertEquals(0.0, snapshot.history[28], 0.0)

        assertEquals(-0.10, snapshot.reaction[0], 1e-6)
        assertEquals(-2.0 / 3.0, snapshot.reaction[1], 1e-6)
        assertEquals(-0.02, snapshot.reaction[2], 1e-6)
        assertEquals(-0.25, snapshot.reaction[3], 1e-6)
        assertTrue(snapshot.flags.fastExhibition)
        assertTrue(snapshot.flags.goodPreviewStart)
        assertFalse(snapshot.flags.courseChanged)
    }

    @Test
    fun dayIsCommittedOnlyAfterAllSnapshotsAndCannotLeakBackIntoSameDay() {
        val history = ModelAPlayerHistory()
        val snapshots = (0 until 6).map { lane ->
            history.snapshot(
                player = 2000 + lane,
                course = lane + 1,
                racerClass = 2,
                exhibitionTime = 6.70 + lane * 0.01,
                previewStartTiming = 0.14 + lane * 0.01,
                courseChanged = false,
                day = 10
            )
        }
        // Snapshotting itself is read-only; every lane saw the same pre-day state.
        snapshots.forEach { assertEquals(0.0, it.history[0], 0.0) }

        val updates = snapshots.mapIndexed { lane, snapshot ->
            ModelAPlayerHistory.OutcomeUpdate(
                player = 2000 + lane,
                course = lane + 1,
                racerClass = 2,
                exhibitionTime = 6.70 + lane * 0.01,
                previewStartTiming = 0.14 + lane * 0.01,
                win = lane == 0,
                top2 = lane <= 1,
                top3 = lane <= 2,
                flags = snapshot.flags
            )
        }
        history.commitDay(10, updates)

        assertEquals(10, history.lastDay)
        assertEquals(1, history.updateRaces)
        assertEquals(6, history.registeredPlayers)
        assertTrue(
            runCatching {
                history.snapshot(2000, 1, 2, 6.7, 0.14, false, 10)
            }.exceptionOrNull() is IllegalArgumentException
        )

        val nextDay = history.snapshot(2000, 1, 2, 6.7, 0.14, false, 11)
        assertEquals(1.0, nextDay.history[0], 0.0)
        assertEquals(1.0, nextDay.history[4], 0.0)
        assertEquals(1.0, nextDay.history[16], 0.0)
        assertEquals(1.0, nextDay.history[20], 0.0)
        assertEquals(1.0, nextDay.history[24], 0.0)
        assertEquals(1.0, nextDay.history[28], 0.0)
    }

    @Test
    fun rollingWindowsUseSameLeftInclusiveBoundaryAsPythonBisect() {
        val history = ModelAPlayerHistory()
        val snapshots = (0 until 6).map { lane ->
            history.snapshot(3000 + lane, lane + 1, 1, 6.8, 0.17, false, 1)
        }
        history.commitDay(
            1,
            snapshots.mapIndexed { lane, snapshot ->
                ModelAPlayerHistory.OutcomeUpdate(
                    player = 3000 + lane,
                    course = lane + 1,
                    racerClass = 1,
                    exhibitionTime = 6.8,
                    previewStartTiming = 0.17,
                    win = lane == 0,
                    top2 = lane <= 1,
                    top3 = lane <= 2,
                    flags = snapshot.flags
                )
            }
        )

        val day31 = history.snapshot(3000, 1, 1, 6.8, 0.17, false, 31)
        assertEquals(1.0, day31.history[16], 0.0) // day 1 is included in [day-30, day)

        val day32 = history.snapshot(3000, 1, 1, 6.8, 0.17, false, 32)
        assertEquals(0.0, day32.history[16], 0.0)
        assertEquals(1.0, day32.history[20], 0.0)
        assertEquals(1.0, day32.history[24], 0.0)
        assertEquals(1.0, day32.history[28], 0.0)
    }

    @Test
    fun incompleteRaceCannotAdvanceHistory() {
        val history = ModelAPlayerHistory()
        val flags = ModelAPlayerHistory.Flags(false, false, false)
        val oneLane = ModelAPlayerHistory.OutcomeUpdate(
            player = 4000,
            course = 1,
            racerClass = 1,
            exhibitionTime = 6.8,
            previewStartTiming = 0.17,
            win = true,
            top2 = true,
            top3 = true,
            flags = flags
        )
        assertTrue(runCatching { history.commitDay(1, listOf(oneLane)) }.isFailure)
        assertEquals(0, history.lastDay)
        assertEquals(0, history.updateRaces)
    }
}
