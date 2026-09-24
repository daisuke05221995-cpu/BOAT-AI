package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import kotlin.math.abs

class ModelARealParityTest {
    @Test
    fun frozenModelARawScoresMatchPinnedLightGbmFixtures() {
        val rootPath = System.getenv("BOAT_AI_PARITY_DIR")
        assumeTrue("BOAT_AI_PARITY_DIR is only set by the dedicated parity workflow", !rootPath.isNullOrBlank())
        val root = File(requireNotNull(rootPath))
        assertTrue(root.isDirectory)

        var totalRows = 0
        var globalMaxError = 0.0
        val expectedFeatures = intArrayOf(545, 715, 885)

        for (stage in 0..2) {
            val modelFile = File(root, "stage$stage.txt")
            val fixtureFile = File(root, "stage$stage.csv")
            assertTrue("Missing $modelFile", modelFile.isFile)
            assertTrue("Missing $fixtureFile", fixtureFile.isFile)

            val model = LightGbmTextModel.parse(modelFile.readText())
            assertEquals(expectedFeatures[stage], model.featureCount)

            var stageRows = 0
            var stageMaxError = 0.0
            fixtureFile.useLines { lines ->
                lines.filter { it.isNotBlank() }.forEach { line ->
                    val values = line.split(',')
                    assertEquals(model.featureCount + 1, values.size)
                    val features = DoubleArray(model.featureCount) { index -> values[index].toDouble() }
                    val expected = values.last().toDouble()
                    val actual = model.predict(features)
                    val error = abs(actual - expected)
                    if (error > stageMaxError) stageMaxError = error
                    stageRows += 1
                }
            }
            assertTrue("stage $stage fixture too small: $stageRows", stageRows >= 1024)
            assertTrue("stage $stage raw-score max error=$stageMaxError", stageMaxError <= 1e-10)
            totalRows += stageRows
            if (stageMaxError > globalMaxError) globalMaxError = stageMaxError
        }

        assertEquals(3072, totalRows)
        assertTrue("global raw-score max error=$globalMaxError", globalMaxError <= 1e-10)
    }
}
