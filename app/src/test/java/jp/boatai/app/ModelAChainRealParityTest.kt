package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import kotlin.math.abs

class ModelAChainRealParityTest {
    @Test
    fun frozenPythonAndKotlinMatchOnActualJulyAugustPreRaceFeatures() {
        val rootPath = System.getenv("BOAT_AI_PARITY_DIR")
        assumeTrue("BOAT_AI_PARITY_DIR is only set by the dedicated parity workflow", !rootPath.isNullOrBlank())
        val root = File(requireNotNull(rootPath))
        val fixture = File(root, "chain.csv")
        assertTrue("Missing $fixture", fixture.isFile)

        val predictor = ModelAConditionalPredictor(
            stage0 = LightGbmTextModel.parse(File(root, "stage0.txt").readText()),
            stage1 = LightGbmTextModel.parse(File(root, "stage1.txt").readText()),
            stage2 = LightGbmTextModel.parse(File(root, "stage2.txt").readText()),
            temperature = 1.0
        )

        var races = 0
        var probabilitiesChecked = 0
        var maxError = 0.0
        fixture.useLines { lines ->
            lines.filter { it.isNotBlank() }.forEach { line ->
                val sections = line.split('|')
                assertEquals(5, sections.size)
                val flatBoat = sections[0].split(',').map(String::toDouble)
                val global = sections[1].split(',').map(String::toDouble).toDoubleArray()
                val venue = sections[2].toInt()
                val raceNumber = sections[3].toInt()
                val expected = sections[4].split(',').map(String::toDouble).toDoubleArray()

                assertEquals(6 * 82, flatBoat.size)
                assertEquals(24, global.size)
                assertEquals(120, expected.size)

                val boat = Array(6) { lane ->
                    DoubleArray(82) { feature -> flatBoat[lane * 82 + feature] }
                }
                val actual = predictor.predict(
                    ModelAConditionalPredictor.Input(
                        boat = boat,
                        global = global,
                        venue = venue,
                        raceNumber = raceNumber
                    )
                )

                assertEquals(120, actual.probabilities.size)
                assertEquals(1.0, actual.probabilities.sum(), 1e-10)
                for (index in 0 until 120) {
                    val error = abs(actual.probabilities[index] - expected[index])
                    if (error > maxError) maxError = error
                    probabilitiesChecked += 1
                }
                races += 1
            }
        }

        assertEquals(64, races)
        assertEquals(64 * 120, probabilitiesChecked)
        assertTrue("120-way Model A max probability error=$maxError", maxError <= 5e-7)
    }
}
