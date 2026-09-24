package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import kotlin.system.measureNanoTime

class ModelAPerformanceSmokeTest {
    @Test
    fun frozenModelAndHistoryHavePracticalJvmSmokePerformance() {
        val rootPath = System.getenv("BOAT_AI_PARITY_DIR")
        assumeTrue("BOAT_AI_PARITY_DIR is only set by the dedicated parity workflow", !rootPath.isNullOrBlank())
        val root = File(requireNotNull(rootPath))

        lateinit var stage0: LightGbmTextModel
        lateinit var stage1: LightGbmTextModel
        lateinit var stage2: LightGbmTextModel
        val modelParseMs = measureNanoTime {
            stage0 = LightGbmTextModel.parse(File(root, "stage0.txt").readText())
            stage1 = LightGbmTextModel.parse(File(root, "stage1.txt").readText())
            stage2 = LightGbmTextModel.parse(File(root, "stage2.txt").readText())
        } / 1_000_000.0

        lateinit var state: ModelAPlayerHistory.State
        val historyBytes = File(root, "history-state.bin").readBytes()
        val historyDecodeMs = measureNanoTime {
            state = ModelAHistoryStateCodec.decode(historyBytes)
        } / 1_000_000.0

        val firstLine = File(root, "chain.csv").useLines { lines -> lines.first { it.isNotBlank() } }
        val sections = firstLine.split('|')
        val flatBoat = sections[0].split(',').map(String::toDouble)
        val global = sections[1].split(',').map(String::toDouble).toDoubleArray()
        val input = ModelAConditionalPredictor.Input(
            boat = Array(6) { lane -> DoubleArray(82) { feature -> flatBoat[lane * 82 + feature] } },
            global = global,
            venue = sections[2].toInt(),
            raceNumber = sections[3].toInt()
        )
        val predictor = ModelAConditionalPredictor(stage0, stage1, stage2, 1.0)

        repeat(3) { predictor.predict(input) }
        val samples = DoubleArray(20)
        repeat(samples.size) { index ->
            samples[index] = measureNanoTime { predictor.predict(input) } / 1_000_000.0
        }
        samples.sort()
        val medianMs = (samples[9] + samples[10]) / 2.0
        val p95Ms = samples[18]

        val forecast = predictor.predict(input)
        assertEquals(120, forecast.probabilities.size)
        assertEquals(1.0, forecast.probabilities.sum(), 1e-10)
        assertEquals(3_485_687, historyBytes.size)
        assertEquals(1_670, state.recent.size)

        // Very loose regression ceilings: this is a CI/JVM smoke gate, not an Android-device benchmark.
        assertTrue("Model parse unexpectedly slow: $modelParseMs ms", modelParseMs < 15_000.0)
        assertTrue("History decode unexpectedly slow: $historyDecodeMs ms", historyDecodeMs < 15_000.0)
        assertTrue("Forecast unexpectedly slow: p95=$p95Ms ms", p95Ms < 5_000.0)

        println(
            "MODEL_A_PERF modelParseMs=%.3f historyDecodeMs=%.3f forecastMedianMs=%.3f forecastP95Ms=%.3f historyBytes=%d".format(
                modelParseMs, historyDecodeMs, medianMs, p95Ms, historyBytes.size
            )
        )
    }
}
