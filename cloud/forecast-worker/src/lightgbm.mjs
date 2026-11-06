// Numeric LightGBM v4 text-model evaluator matching Android LightGbmTextModel.
// Explicitly rejects categorical and linear trees; no model re-training.
const numberList = text => text.trim() ? text.trim().split(/\s+/).map(Number) : [];

function assertNumbers(values, integer = false) {
  if (values.some(value => !Number.isFinite(value) || (integer && !Number.isInteger(value)))) {
    throw new Error('MALFORMED_LIGHTGBM_VALUES');
  }
  return values;
}

function finishTree(builder) {
  const leaves = builder.num_leaves;
  if (!Number.isInteger(leaves) || leaves < 1 || builder.num_cat !== 0 ||
      (builder.is_linear ?? 0) !== 0) throw new Error('UNSUPPORTED_LIGHTGBM_TREE');
  const fields = ['split_feature', 'threshold', 'decision_type', 'left_child', 'right_child'];
  for (const field of fields) {
    if (!Array.isArray(builder[field]) || builder[field].length !== leaves - 1) {
      throw new Error(`MALFORMED_LIGHTGBM_${field}`);
    }
  }
  if (!Array.isArray(builder.leaf_value) || builder.leaf_value.length !== leaves) {
    throw new Error('MALFORMED_LIGHTGBM_LEAVES');
  }
  return builder;
}

export class LightGbmTextModel {
  constructor(featureCount, trees) {
    if (!Number.isInteger(featureCount) || featureCount <= 0 || !trees.length) {
      throw new Error('INVALID_LIGHTGBM_MODEL');
    }
    this.featureCount = featureCount;
    this.trees = trees;
    this.treeCount = trees.length;
  }

  static parse(text) {
    if (typeof text !== 'string') throw new Error('INVALID_LIGHTGBM_TEXT');
    let maxFeatureIndex;
    let numClass;
    let treesPerIteration;
    const trees = [];
    let current = null;
    const integers = new Set(['num_leaves', 'num_cat', 'is_linear']);
    const integerArrays = new Set(['split_feature', 'decision_type', 'left_child', 'right_child']);
    const floatArrays = new Set(['threshold', 'leaf_value']);
    const finish = () => {
      if (current) trees.push(finishTree(current));
      current = null;
    };
    for (const raw of text.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line) continue;
      if (line.startsWith('Tree=')) { finish(); current = {}; continue; }
      if (line === 'end of trees') { finish(); break; }
      const at = line.indexOf('=');
      if (at <= 0) continue;
      const key = line.slice(0, at);
      const value = line.slice(at + 1);
      if (current) {
        if (integers.has(key)) {
          const n = Number(value);
          if (!Number.isInteger(n)) throw new Error('MALFORMED_LIGHTGBM_INTEGER');
          current[key] = n;
        } else if (integerArrays.has(key) || floatArrays.has(key)) {
          current[key] = assertNumbers(numberList(value), integerArrays.has(key));
        }
      } else {
        if (key === 'max_feature_idx') maxFeatureIndex = Number(value);
        if (key === 'num_class') numClass = Number(value);
        if (key === 'num_tree_per_iteration') treesPerIteration = Number(value);
      }
    }
    finish();
    if ((numClass != null && numClass !== 1) ||
        (treesPerIteration != null && treesPerIteration !== 1)) throw new Error('UNSUPPORTED_LIGHTGBM_OUTPUT');
    const featureCount = (maxFeatureIndex ?? Math.max(...trees.flatMap(tree => tree.split_feature), -1)) + 1;
    return new LightGbmTextModel(featureCount, trees);
  }

  predict(features) {
    if (!Array.isArray(features) || features.length < this.featureCount) {
      throw new Error('LIGHTGBM_FEATURE_WIDTH_MISMATCH');
    }
    let result = 0;
    for (const tree of this.trees) {
      let node = 0;
      let guard = 0;
      while (node >= 0) {
        if (node >= tree.split_feature.length) throw new Error('LIGHTGBM_CHILD_OUT_OF_RANGE');
        const featureIndex = tree.split_feature[node];
        if (featureIndex < 0 || featureIndex >= features.length) throw new Error('LIGHTGBM_FEATURE_OUT_OF_RANGE');
        const type = tree.decision_type[node];
        if ((type & 1) !== 0) throw new Error('LIGHTGBM_CATEGORICAL_NOT_SUPPORTED');
        const missingType = (type >> 2) & 3;
        let value = features[featureIndex];
        if (Number.isNaN(value) && missingType !== 2) value = 0;
        const missing = missingType === 0 ? false :
          missingType === 1 ? Math.abs(value) <= 1e-35 :
          missingType === 2 ? Number.isNaN(value) : null;
        if (missing == null) throw new Error('LIGHTGBM_MISSING_TYPE_UNSUPPORTED');
        node = missing
          ? (type & 2) !== 0 ? tree.left_child[node] : tree.right_child[node]
          : value <= tree.threshold[node] ? tree.left_child[node] : tree.right_child[node];
        if (++guard > tree.split_feature.length + 1) throw new Error('LIGHTGBM_TREE_CYCLE');
      }
      const leaf = -node - 1;
      if (leaf >= tree.leaf_value.length) throw new Error('LIGHTGBM_LEAF_OUT_OF_RANGE');
      result += tree.leaf_value[leaf];
    }
    return result;
  }
}
