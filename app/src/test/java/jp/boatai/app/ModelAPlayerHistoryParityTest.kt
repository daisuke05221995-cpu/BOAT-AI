package jp.boatai.app

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

class ModelAPlayerHistoryParityTest {
    @Test
    fun kotlinHistoryMatchesFrozenPythonSyntheticTimeline() {
        val rootPath = System.getenv("BOAT_AI_PARITY_DIR")
        assumeTrue("BOAT_AI_PARITY_DIR is only set by the dedicated parity workflow", !rootPath.isNullOrBlank())
        val fixture = File(requireNotNull(rootPath), "history.txt")
        assertTrue("Missing $fixture", fixture.isFile)

        val history = ModelAPlayerHistory()
        var snapshots = 0
        var commits = 0
        var previousSnapshotDay = -1
        var committedCurrentDay = false

        fixture.forEachLine { line ->
            if (line.isBlank()) return@forEachLine
            val fields = line.split('|')
            when (fields[0]) {
                "S" -> {
                    assertEquals(14, fields.size)
                    val day = fields[1].toInt()
                    if (day != previousSnapshotDay) {
                        previousSnapshotDay = day
                        committedCurrentDay = false
                    }
                    assertFalse("Snapshot appeared after same-day commit", committedCurrentDay)

                    val snapshot = history.snapshot(
                        player = fields[3].toInt(),
                        course = fields[4].toInt(),
                        racerClass = fields[5].toInt(),
                        exhibitionTime = fields[6].toDouble(),
                        previewStartTiming = fields[7].toDouble(),
                        courseChanged = fields[8] == "1",
                        day = day
                    )
                    val expectedHistory = fields[9].split(',').map(String::toDouble).toDoubleArray()
                    val expectedReaction = fields[10].split(',').map(String::toDouble).toDoubleArray()
                    assertEquals(32, expectedHistory.size)
                    assertEquals(20, expectedReaction.size)
                    assertArrayEquals("History mismatch day=$day lane=${fields[2]}", expectedHistory, snapshot.history, 1e-6)
                    assertArrayEquals("Reaction mismatch day=$day lane=${fields[2]}", expectedReaction, snapshot.reaction, 1e-6)
                    assertEquals(fields[11] == "1", snapshot.flags.fastExhibition)
                    assertEquals(fields[12] == "1", snapshot.flags.goodPreviewStart)
                    assertEquals(fields[13] == "1", snapshot.flags.courseChanged)
                    snapshots += 1
                }

                "C" -> {
                    assertEquals(3, fields.size)
                    val day = fields[1].toInt()
                    val updates = fields[2].split(';').filter { it.isNotBlank() }.map { encoded ->
                        val v = encoded.split(',')
                        assertEquals(11, v.size)
                        ModelAPlayerHistory.OutcomeUpdate(
                            player = v[0].toInt(),
                            course = v[1].toInt(),
                            racerClass = v[2].toInt(),
                            exhibitionTime = v[3].toDouble(),
                            previewStartTiming = v[4].toDouble(),
                            win = v[5] == "1",
                            top2 = v[6] == "1",
                            top3 = v[7] == "1",
                            flags = ModelAPlayerHistory.Flags(
                                fastExhibition = v[8] == "1",
                                goodPreviewStart = v[9] == "1",
                                courseChanged = v[10] == "1"
                            )
                        )
                    }
                    assertEquals(6, updates.size)
                    history.commitDay(day, updates)
                    committedCurrentDay = true
                    commits += 1
                }

                else -> error("Unknown fixture row ${fields[0]}")
            }
        }

        assertEquals(48, snapshots)
        assertEquals(8, commits)
        assertEquals(182, history.lastDay)
        assertEquals(8, history.updateRaces)
        assertEquals(6, history.registeredPlayers)
    }
}
