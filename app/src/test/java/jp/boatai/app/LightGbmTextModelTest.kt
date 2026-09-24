package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LightGbmTextModelTest {
    @Test
    fun parsesNumericTreeAndMatchesLightGbmMissingRouting() {
        val model = LightGbmTextModel.parse(
            """
            tree
            version=v4
            num_class=1
            num_tree_per_iteration=1
            max_feature_idx=1

            Tree=0
            num_leaves=3
            num_cat=0
            split_feature=0 1
            threshold=1.5 0.0
            decision_type=2 10
            left_child=-1 -2
            right_child=1 -3
            leaf_value=0.25 1.5 -2.0
            is_linear=0
            shrinkage=1

            end of trees
            """.trimIndent()
        )

        assertEquals(1, model.treeCount)
        assertEquals(2, model.featureCount)
        assertEquals(0.25, model.predict(doubleArrayOf(1.0, 99.0)), 0.0)
        assertEquals(1.5, model.predict(doubleArrayOf(2.0, Double.NaN)), 0.0)
        assertEquals(1.5, model.predict(doubleArrayOf(2.0, -0.1)), 0.0)
        assertEquals(-2.0, model.predict(doubleArrayOf(2.0, 0.1)), 0.0)
    }

    @Test
    fun sumsTreeOutputsLikeRawScorePrediction() {
        val model = LightGbmTextModel.parse(
            """
            tree
            version=v4
            num_class=1
            num_tree_per_iteration=1
            max_feature_idx=0

            Tree=0
            num_leaves=2
            num_cat=0
            split_feature=0
            threshold=0
            decision_type=2
            left_child=-1
            right_child=-2
            leaf_value=0.3 0.7
            is_linear=0

            Tree=1
            num_leaves=2
            num_cat=0
            split_feature=0
            threshold=1
            decision_type=8
            left_child=-1
            right_child=-2
            leaf_value=-0.2 0.4
            is_linear=0

            end of trees
            """.trimIndent()
        )

        assertEquals(0.1, model.predict(doubleArrayOf(-1.0)), 1e-12)
        assertEquals(0.5, model.predict(doubleArrayOf(0.5)), 1e-12)
        // decision_type=8 means NaN-missing with default-right in LightGBM v4.
        assertEquals(1.1, model.predict(doubleArrayOf(Double.NaN)), 1e-12)
    }

    @Test
    fun rejectsModelShapesThatPrototypeDoesNotSupport() {
        val categorical = """
            tree
            num_class=1
            num_tree_per_iteration=1
            max_feature_idx=0
            Tree=0
            num_leaves=2
            num_cat=1
            split_feature=0
            threshold=0
            decision_type=1
            left_child=-1
            right_child=-2
            leaf_value=0 1
            is_linear=0
            end of trees
        """.trimIndent()

        val failure = runCatching { LightGbmTextModel.parse(categorical) }.exceptionOrNull()
        assertTrue(failure is IllegalArgumentException)
    }
}
