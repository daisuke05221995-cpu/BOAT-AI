package jp.boatai.app

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

class ModelAHistoryAssetParityTest {
    @Test
    fun pythonEncodedFrozenHistoryDecodesAndReencodesByteIdentically() {
        val rootPath = System.getenv("BOAT_AI_PARITY_DIR")
        assumeTrue("BOAT_AI_PARITY_DIR is only set by the dedicated parity workflow", !rootPath.isNullOrBlank())
        val file = File(requireNotNull(rootPath), "history-state.bin")
        assertTrue("Missing $file", file.isFile)
        val bytes = file.readBytes()

        val state = ModelAHistoryStateCodec.decode(bytes)
        val metadata = ModelAHistoryStateCodec.metadata(bytes, state)

        assertEquals(739_494, metadata.lastDay)
        assertEquals(87_491, metadata.updateRaces)
        assertEquals(32_196, metadata.stats)
        assertEquals(1_670, metadata.players)
        assertEquals(524_946, metadata.appearances)
        assertEquals(3_485_687, metadata.bytes)
        assertTrue(metadata.bytes < 4 * 1024 * 1024)

        val reencoded = ModelAHistoryStateCodec.encode(state)
        assertArrayEquals("Python/Kotlin compact history bytes differ", bytes, reencoded)

        // Confirm the decoded frozen state can immediately supply a next-day snapshot.
        val history = ModelAPlayerHistory(state)
        val player = state.recent.keys.first().toInt()
        val snapshot = history.snapshot(
            player = player,
            course = 1,
            racerClass = 1,
            exhibitionTime = 6.8,
            previewStartTiming = 0.17,
            courseChanged = false,
            day = state.lastDay + 1
        )
        assertEquals(32, snapshot.history.size)
        assertEquals(20, snapshot.reaction.size)
        assertTrue(snapshot.history.all { it.isFinite() })
        assertTrue(snapshot.reaction.all { it.isFinite() })
    }
}
