#!/usr/bin/env python3
"""Independent frozen Python model probabilities on synthetic *race* features.

Input 6x82+24 vectors were constructed by the independent Python r2/r4
history feature script, not by the JS implementation. No holdouts, odds,
real race archives, model fitting, or strategy thresholds are accessed.
"""
import hashlib
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from v016_r2_model import COMBOS, PREFIXES, context, rows, softmax  # noqa: E402


def main():
    if lgb.__version__ != '4.6.0':
        raise RuntimeError(f'Pinned LightGBM version required: got {lgb.__version__}')

    fixture_dir = ROOT / 'cloud/forecast-worker/test/fixtures'
    features = json.loads((fixture_dir / 'python-model-a-features.json').read_text())
    cases = [case for case in features['cases'] if case['expected']['historyFreshForDay']]
    n = len(cases)
    if n != 2:
        raise RuntimeError(f'Unexpected fresh synthetic case count: {n}')
    boat = np.asarray([[[(np.nan if value is None else value) for value in row]
                        for row in case['expected']['boat']] for case in cases], dtype=np.float32)
    glob = np.asarray([[(np.nan if value is None else value) for value in case['expected']['global']]
                       for case in cases], dtype=np.float32)
    venues = np.asarray([case['race']['stadiumNumber'] for case in cases], dtype=np.int32)
    races = np.asarray([case['race']['raceNumber'] for case in cases], dtype=np.int32)
    ctx = context({'boat': boat, 'global_features': glob, 'venue': venues,
                   'race_number': races,
                   'market_p': np.full((n, 120), 1.0 / 120.0, dtype=np.float32)})

    model_paths = [ROOT / 'app/src/main/assets' / f'model_a_stage{stage}.txt'
                   for stage in range(3)]
    models = [lgb.Booster(model_file=str(path)) for path in model_paths]
    if [model.num_feature() for model in models] != [545, 715, 885]:
        raise RuntimeError('Frozen model feature widths drifted')

    conditional = []
    for stage in range(3):
        prefix = PREFIXES[stage]
        race_indices = np.repeat(np.arange(n), len(prefix))
        prefixes = np.tile(prefix, (n, 1))
        matrix, market, candidates = rows(ctx, race_indices, prefixes, 'fundamental')
        if not np.array_equal(market, np.zeros_like(market)):
            raise RuntimeError('Market features unexpectedly consumed by Model A')
        logits = models[stage].predict(matrix, raw_score=True, num_threads=2)
        probabilities = softmax(logits.reshape(-1, 6 - stage))
        table = np.zeros((n,) + (6,) * (stage + 1), dtype=np.float64)
        indices = [np.repeat(race_indices, 6 - stage)]
        indices.extend(np.repeat(prefixes[:, i], 6 - stage) for i in range(stage))
        indices.append(candidates.ravel())
        table[tuple(indices)] = probabilities.ravel()
        conditional.append(table)

    chain = conditional[0][:, COMBOS[:, 0]] * conditional[1][:, COMBOS[:, 0], COMBOS[:, 1]] * conditional[2][
        :, COMBOS[:, 0], COMBOS[:, 1], COMBOS[:, 2]]
    if not np.isfinite(chain).all() or not np.allclose(chain.sum(axis=1), 1.0, atol=1e-10):
        raise RuntimeError('Probability golden failed mass/finite validation')

    result = {
        'schema_version': 1,
        'source': 'Python v016_r2_model.py / v016_r4_player_history.py + LightGBM 4.6.0, synthetic only',
        'temperature': 1.0,
        'model_sha256': {f'stage{stage}': hashlib.sha256(path.read_bytes()).hexdigest()
                         for stage, path in enumerate(model_paths)},
        'cases': [{'feature_case_index': index, 'probabilities': [float(value) for value in chain[row]]}
                  for row, index in enumerate(i for i, case in enumerate(features['cases'])
                                               if case['expected']['historyFreshForDay'])],
    }
    output = fixture_dir / 'python-model-a-end-to-end.json'
    output.write_text(json.dumps(result, separators=(',', ':')) + '\n', encoding='utf8')
    print(f'Wrote {n} synthetic complete-race 120-way forecasts to {output.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
