package jp.boatai.app

import kotlin.math.abs

/**
 * Minimal LightGBM v4 text-model evaluator for the numeric, non-linear trees used by
 * BOAT AI Model A. It deliberately rejects categorical / linear trees instead of
 * silently producing a different prediction.
 */
internal class LightGbmTextModel private constructor(
    val featureCount: Int,
    private val trees: List<Tree>
) {
    fun predict(features: DoubleArray): Double {
        require(features.size >= featureCount) {
            "Expected at least $featureCount features, got ${features.size}"
        }
        var sum = 0.0
        for (tree in trees) sum += tree.predict(features)
        return sum
    }

    val treeCount: Int get() = trees.size

    private data class Tree(
        val splitFeature: IntArray,
        val threshold: DoubleArray,
        val decisionType: IntArray,
        val leftChild: IntArray,
        val rightChild: IntArray,
        val leafValue: DoubleArray
    ) {
        fun predict(features: DoubleArray): Double {
            var node = 0
            var guard = 0
            while (node >= 0) {
                require(node < splitFeature.size) { "Invalid LightGBM child index $node" }
                val featureIndex = splitFeature[node]
                require(featureIndex in features.indices) {
                    "Feature index $featureIndex is outside row size ${features.size}"
                }
                val type = decisionType[node]
                require((type and CATEGORICAL_MASK) == 0) {
                    "Categorical LightGBM split is not supported by this evaluator"
                }
                val missingType = (type shr 2) and 3
                var value = features[featureIndex]
                if (value.isNaN() && missingType != MISSING_NAN) value = 0.0

                val missing = when (missingType) {
                    MISSING_NONE -> false
                    MISSING_ZERO -> abs(value) <= ZERO_THRESHOLD
                    MISSING_NAN -> value.isNaN()
                    else -> error("Unsupported LightGBM missing type $missingType")
                }
                node = if (missing) {
                    if ((type and DEFAULT_LEFT_MASK) != 0) leftChild[node] else rightChild[node]
                } else {
                    if (value <= threshold[node]) leftChild[node] else rightChild[node]
                }
                guard += 1
                require(guard <= splitFeature.size + 1) { "Cycle detected in LightGBM tree" }
            }
            val leaf = -node - 1
            require(leaf in leafValue.indices) { "Invalid LightGBM leaf index $leaf" }
            return leafValue[leaf]
        }
    }

    private class TreeBuilder {
        var numLeaves: Int? = null
        var numCat: Int? = null
        var splitFeature: IntArray? = null
        var threshold: DoubleArray? = null
        var decisionType: IntArray? = null
        var leftChild: IntArray? = null
        var rightChild: IntArray? = null
        var leafValue: DoubleArray? = null
        var isLinear: Int? = null

        fun build(): Tree {
            val leaves = requireNotNull(numLeaves) { "Missing num_leaves" }
            require(leaves >= 1) { "Invalid num_leaves=$leaves" }
            require((numCat ?: 0) == 0) { "Categorical LightGBM trees are not supported" }
            require((isLinear ?: 0) == 0) { "Linear LightGBM trees are not supported" }
            val splits = leaves - 1
            val sf = requireNotNull(splitFeature) { "Missing split_feature" }
            val th = requireNotNull(threshold) { "Missing threshold" }
            val dt = requireNotNull(decisionType) { "Missing decision_type" }
            val lc = requireNotNull(leftChild) { "Missing left_child" }
            val rc = requireNotNull(rightChild) { "Missing right_child" }
            val lv = requireNotNull(leafValue) { "Missing leaf_value" }
            require(sf.size == splits && th.size == splits && dt.size == splits && lc.size == splits && rc.size == splits) {
                "Malformed LightGBM tree arrays for $leaves leaves"
            }
            require(lv.size == leaves) { "Expected $leaves leaf values, got ${lv.size}" }
            return Tree(sf, th, dt, lc, rc, lv)
        }
    }

    companion object {
        private const val CATEGORICAL_MASK = 1
        private const val DEFAULT_LEFT_MASK = 2
        private const val MISSING_NONE = 0
        private const val MISSING_ZERO = 1
        private const val MISSING_NAN = 2
        private const val ZERO_THRESHOLD = 1e-35

        fun parse(text: String): LightGbmTextModel {
            var maxFeatureIndex: Int? = null
            var numClass: Int? = null
            var numTreePerIteration: Int? = null
            val trees = mutableListOf<Tree>()
            var current: TreeBuilder? = null

            fun finishTree() {
                current?.let { trees += it.build() }
                current = null
            }

            for (rawLine in text.lineSequence()) {
                val line = rawLine.trim()
                if (line.isEmpty()) continue
                if (line.startsWith("Tree=")) {
                    finishTree()
                    current = TreeBuilder()
                    continue
                }
                if (line == "end of trees") {
                    finishTree()
                    break
                }
                val equals = line.indexOf('=')
                if (equals <= 0) continue
                val key = line.substring(0, equals)
                val value = line.substring(equals + 1)
                val builder = current
                if (builder == null) {
                    when (key) {
                        "max_feature_idx" -> maxFeatureIndex = value.toInt()
                        "num_class" -> numClass = value.toInt()
                        "num_tree_per_iteration" -> numTreePerIteration = value.toInt()
                    }
                } else {
                    when (key) {
                        "num_leaves" -> builder.numLeaves = value.toInt()
                        "num_cat" -> builder.numCat = value.toInt()
                        "split_feature" -> builder.splitFeature = parseInts(value)
                        "threshold" -> builder.threshold = parseDoubles(value)
                        "decision_type" -> builder.decisionType = parseInts(value)
                        "left_child" -> builder.leftChild = parseInts(value)
                        "right_child" -> builder.rightChild = parseInts(value)
                        "leaf_value" -> builder.leafValue = parseDoubles(value)
                        "is_linear" -> builder.isLinear = value.toInt()
                    }
                }
            }
            finishTree()

            require(numClass == null || numClass == 1) { "Only single-output LightGBM models are supported" }
            require(numTreePerIteration == null || numTreePerIteration == 1) {
                "Only one tree per iteration is supported"
            }
            require(trees.isNotEmpty()) { "No LightGBM trees found" }
            val featureCount = (maxFeatureIndex ?: trees.maxOf { tree -> tree.splitFeature.maxOrNull() ?: -1 }) + 1
            require(featureCount > 0) { "Could not determine LightGBM feature count" }
            return LightGbmTextModel(featureCount, trees)
        }

        private fun parseInts(value: String): IntArray =
            if (value.isBlank()) IntArray(0) else value.trim().split(Regex("\\s+")).map(String::toInt).toIntArray()

        private fun parseDoubles(value: String): DoubleArray =
            if (value.isBlank()) DoubleArray(0) else value.trim().split(Regex("\\s+")).map(String::toDouble).toDoubleArray()
    }
}
