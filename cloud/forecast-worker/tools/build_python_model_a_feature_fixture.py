#!/usr/bin/env python3
"""Independent frozen Python r4 golden 6x82 + 24 feature rows, synthetic only.

Does not open race archives, real outcomes, odds, or any historical holdout.
"""

import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from v016_r4_player_history import PlayerHistory  # noqa: E402

DAY = date(2026, 11, 6)


def fresh_state():
    return PlayerHistory()


def warmed_state():
    fixture = json.loads((ROOT / 'cloud/forecast-worker/test/fixtures/python-model-a-history.json').read_text())
    history = PlayerHistory()
    for event in fixture['events']:
        if event['type'] != 'commit':
            continue
        updates = []
        for update in event['updates']:
            flags = update['flags']
            updates.append((update['player'], update['course'], update['racerClass'],
                            update['exhibitionTime'], update['previewStartTiming'],
                            [int(update['win']), int(update['top2']), int(update['top3'])],
                            (flags['fastExhibition'], flags['goodPreviewStart'], flags['courseChanged'])))
        history.commit_day(event['day'], updates)
    history.state['lastDay'] = DAY.toordinal() - 1
    return history


def race_input(seed):
    racers = []
    for lane in range(1, 7):
        preview_course = (lane + seed - 1) % 6 + 1
        racers.append({
            'lane': lane, 'registrationNumber': 1000 + (lane + seed) % 15,
            'rank': ('A1', 'A2', 'B1', 'B2', '?', 'A1')[lane - 1],
            'classNumber': None if lane % 2 else lane % 5,
            'nationalWinRate': round(5.1 + lane * .31 + seed * .03, 3),
            'localWinRate': None if lane == 3 else round(4.1 + lane * .2, 2),
            'nationalTop2': 28.0 + lane * 2.1, 'localTop2': None if lane == 5 else 31.4,
            'nationalTop3': 41.1 + lane * 2, 'localTop3': 52.8,
            'motorTop2': 32.0 + lane * 1.8, 'motorTop3': 45.3,
            'boatTop2': 29.7, 'boatTop3': None if lane == 2 else 49.2,
            'averageStart': .17 + lane * .005, 'flyingCount': (lane + seed) % 2,
            'lateCount': 0, 'age': 22 + lane * 4, 'weight': 51.0 + lane * .4,
            'preview': {
                'course': preview_course, 'exhibitionTime': round(6.57 + lane * .031 + seed * .007, 3),
                'startTiming': round(-.03 + lane * .029 - seed * .002, 3),
                'tilt': None if lane == 4 else -.5, 'weightAdjustment': 0,
            },
        })
    if seed == 1:
        racers.reverse()  # Android sorts lane numbers before creating feature matrices.
    return {
        'date': DAY.isoformat(), 'stadiumNumber': 5 + seed, 'raceNumber': 6 + seed,
        'racers': racers,
        'preview': {'windSpeed': seed + 2, 'waveHeight': 3 + seed,
                    'airTemperature': 22.1, 'waterTemperature': None if seed == 2 else 18.5,
                    'windDirection': '風向 12' if seed == 1 else None,
                    'windDirectionNumber': None if seed == 1 else (seed + 3 if seed != 2 else None)},
    }


def numeric(value):
    return float(np.float32(value)) if value is not None and math.isfinite(value) else math.nan


def current_row(racer):
    p = racer['preview']
    cls = racer['classNumber']
    if cls is None:
        cls = {'A1': 1, 'A2': 2, 'B1': 3, 'B2': 4}.get(racer['rank'], 0)
    # Independent Python r2 source-field ordering; no JS feature code invoked.
    fields = ['nationalWinRate', 'localWinRate', 'nationalTop2', 'localTop2',
              'nationalTop3', 'localTop3', 'motorTop2', 'motorTop3', 'boatTop2',
              'boatTop3', 'averageStart', 'flyingCount', 'lateCount', 'age', 'weight']
    row = [numeric(racer[name]) for name in fields]
    row.extend(numeric(p[name]) for name in ['exhibitionTime', 'startTiming', 'course', 'tilt', 'weightAdjustment'])
    row.extend(math.nan if cls == 0 else float(cls == num) for num in range(1, 5))
    row.append(float(p['course'] != racer['lane']))
    assert len(row) == 25
    return np.asarray(row, np.float32), cls


def make_expected(race, history):
    racers = sorted(race['racers'], key=lambda r: r['lane'])
    base = np.stack([current_row(racer)[0] for racer in racers])
    classes = [current_row(racer)[1] for racer in racers]
    exs, sts = base[:, 15], base[:, 16]
    rel = np.stack([
        1 + (exs[:, None] > exs[None, :]).sum(axis=1),
        1 + (sts[:, None] > sts[None, :]).sum(axis=1),
        exs - exs.min(), exs - exs.max(), exs - exs[0],
    ], axis=1).astype(np.float32)
    rows, reactions, flags = [], [], []
    for lane, racer in enumerate(racers):
        h, reaction, flag = history.snapshot(racer['registrationNumber'], int(base[lane, 17]),
                                             classes[lane], float(base[lane, 15]), float(base[lane, 16]),
                                             bool(base[lane, 24]), DAY.toordinal())
        rows.append(np.concatenate((base[lane], rel[lane], h, reaction)).astype(np.float32))
        reactions.append(reaction)
        flags.append({'fastExhibition': flag[0], 'goodPreviewStart': flag[1], 'courseChanged': flag[2]})
    reactions = np.asarray(reactions, np.float32)
    preview = race['preview']
    direction = preview['windDirectionNumber']
    if direction is None and preview['windDirection']:
        direction = int(preview['windDirection'].split()[-1])
    glob = [numeric(preview[key]) for key in ['windSpeed', 'waveHeight', 'airTemperature', 'waterTemperature']]
    glob.extend(math.nan if direction is None else float(direction == n) for n in range(1, 17))
    weak = max(float(reactions[0, 1]), 0) + max(float(reactions[0, 3]), 0)
    strong = sum(reactions[other, 1] <= -.5 or reactions[other, 3] <= -.5 for other in range(1, 6))
    glob.extend([weak, int(strong), race['stadiumNumber'], race['raceNumber']])
    assert len(glob) == 24 and all(len(row) == 82 for row in rows)

    def clean(values):
        return [float(value) if math.isfinite(float(value)) else None for value in values]

    return {'boat': [clean(row) for row in rows], 'global': clean(np.asarray(glob, np.float32)),
            'flags': flags, 'predictionDayOrdinal': DAY.toordinal(),
            'historyThroughDayOrdinal': history.state['lastDay'],
            'historyFreshForDay': history.state['lastDay'] == DAY.toordinal() - 1}


def main():
    cases = []
    for seed, warm in [(0, False), (1, True), (2, True)]:
        history = warmed_state() if warm else fresh_state()
        race = race_input(seed)
        cases.append({'race': race, 'state': history.state, 'expected': make_expected(race, history)})
    data = {'schema_version': 1, 'source': 'Frozen Python v016 r2 + r4 synthetic, no holdout access', 'cases': cases}
    destination = ROOT / 'cloud/forecast-worker/test/fixtures/python-model-a-features.json'
    destination.write_text(json.dumps(data, separators=(',', ':'), allow_nan=False) + '\n', encoding='utf8')
    print(f'Wrote {len(cases)} complete synthetic races to {destination.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
