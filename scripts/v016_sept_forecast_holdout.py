#!/usr/bin/env python3
"""Preregistered, market-free September forecast holdout. No Q4 access path."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import subprocess
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from v016_core_research import canonical, digest, dump
from v016_r4_features import COMBOS, COMBO_TEXT, extract_pre
from v016_r4_player_history import PlayerHistory, enrich
from v016_r4_model import code_hashes, inputs, calibrated
from v016_r2_model import predict
from v01516_forecast_audit import COURSE_PRIOR, SCORE_TEMPERATURE, form_score

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'data/v016_sept_forecast_protocol.json'
CANDIDATE = ROOT / 'data/v016_forecast_candidate.json'
PRECOMMIT = '2fbf3239f8ac68e4d45775b353aa03217d9a517f'
START, END = date(2025, 9, 1), date(2025, 9, 30)
SOURCE = {'programs': ('BoatraceOpenAPI/programs', 'd3e37a2b5bce2bc10ac9d8154713cfe250aa5fa1'),
          'previews': ('BoatraceOpenAPI/previews', '5089ce91e150538a8adc8da86ca403f578343318'),
          'results': ('BoatraceOpenAPI/results', '04dfd55682c1f083963ca80b5bfce93ed43cb755')}
KEYS = ('day_ordinal', 'venue', 'race_number')


def preregistration():
    original = subprocess.check_output(['git', '-C', str(ROOT), 'show', PRECOMMIT + ':data/v016_sept_forecast_protocol.json'])
    if hashlib.sha256(original).hexdigest() != digest(PROTOCOL):
        raise ValueError('Preregistered protocol changed after commit')
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', PRECOMMIT, 'HEAD'], check=True)
    p = json.loads(original)
    assert p['period']['q4Prohibited'] and p['scope']['marketInputs'] is False
    assert p['scope']['payoutInputs'] is False and p['scope']['roiMetrics'] is False
    assert p['period']['holdoutStart'] == START.isoformat() and p['period']['holdoutEnd'] == END.isoformat()
    return p


def day_guard(day):
    if not START <= day <= END:
        raise ValueError('Only 2025 September is authorized in this holdout')


def source_url(day, kind):
    day_guard(day)  # Date fence BEFORE constructing any URL or network access.
    if kind not in SOURCE:
        raise ValueError('Only pinned programs, previews and results may be fetched')
    repo, sha = SOURCE[kind]
    return f'https://raw.githubusercontent.com/{repo}/{sha}/docs/v3/2025/{day:%Y%m%d}.json'


def read_day(day):
    out, hashes = {}, {}
    for kind in SOURCE:
        url = source_url(day, kind)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'BOAT-AI-v016-sept-forecast'}), timeout=45) as response:
                    raw = response.read()
                records = json.loads(raw)[kind]
                keyed = {}
                for row in records:
                    if row.get('date') != day.isoformat():
                        raise ValueError('Source row outside approved month')
                    key = int(row['stadium_number']), int(row['number'])
                    if key in keyed:
                        raise ValueError('Duplicate source race')
                    # Do not carry any settlement, odds, or payout field into the cache.
                    if kind == 'results':
                        keyed[key] = {'date': row['date'], 'stadium_number': row['stadium_number'],
                                      'number': row['number'], 'boats': [{k: b.get(k) for k in
                                       ('racer_boat_number', 'racer_number', 'racer_place_number')}
                                       for b in row.get('boats', [])]}
                    else:
                        keyed[key] = row
                out[kind] = keyed
                hashes[kind] = hashlib.sha256(raw).hexdigest()
                break
            except ValueError:
                raise
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
    return out, hashes


def finish_index(program, result):
    if not result:
        return None
    pb = {b['racer_boat_number']: b for b in program.get('boats', [])}
    rb = {b['racer_boat_number']: b for b in result.get('boats', [])}
    if len(program.get('boats', [])) != 6 or len(result.get('boats', [])) != 6 or set(pb) != set(range(1, 7)) or set(rb) != set(pb):
        return None
    places = [rb[i].get('racer_place_number') for i in range(1, 7)]
    if set(places) != set(range(1, 7)):
        return None
    if any(rb[i].get('racer_number') != pb[i].get('racer_number') for i in range(1, 7)):
        raise ValueError('Settled racer ID mismatch')
    order = tuple(places.index(i) for i in (1, 2, 3))
    index = np.flatnonzero(np.all(COMBOS == order, axis=1))
    if len(index) != 1:
        raise ValueError('Nonunique finish order')
    return int(index[0])


def keys(c):
    arr = np.stack([c[k].astype(np.int64) for k in KEYS], axis=1)
    if len(np.unique(arr, axis=0)) != len(arr):
        raise ValueError('Duplicate race key')
    return arr


def load_features(path):
    with np.load(path, allow_pickle=False) as z:
        for name in ('day_ordinal', 'month', 'venue', 'race_number', 'actual_index', 'usable', 'current',
                     'global_features', 'history', 'reaction', 'history_through', 'boat_names',
                     'history_names', 'reaction_names', 'combos', 'year'):
            if name not in z.files:
                raise ValueError('Missing forecast feature ' + name)
        # Explicit allowlist: outcome used solely by evaluation, never model or baseline inputs.
        c = {k: z[k] for k in ('day_ordinal', 'month', 'venue', 'race_number', 'actual_index', 'usable',
                              'current', 'global_features', 'history', 'reaction', 'history_through',
                              'boat_names', 'history_names', 'reaction_names', 'combos', 'year')}
    days = c['day_ordinal'].astype(int)
    if not len(days) or min(days) < START.toordinal() or max(days) > END.toordinal() or set(c['month'].astype(int)) != {9}:
        raise ValueError('September feature cache date fence violation')
    if np.any(c['history_through'] >= days):
        raise ValueError('Same-day/future result leakage')
    if not np.array_equal(c['combos'], COMBO_TEXT) or set(c['year'].astype(int)) != {2025}:
        raise ValueError('Feature schema/year mismatch')
    keys(c)
    return c


def build(args):
    p = preregistration()
    if digest(args.state) != p['candidate']['historyStateSha256']:
        raise ValueError('Frozen August history state SHA mismatch')
    state = json.loads(args.state.read_text())
    if state['lastDay'] != date(2025, 8, 31).toordinal():
        raise ValueError('History checkpoint is not through August 31')
    rows, source_hashes, counts = [], {}, Counter()
    days = [START + timedelta(days=i) for i in range(30)]
    with ThreadPoolExecutor(max_workers=10) as pool:
        tasks = {pool.submit(read_day, day): day for day in days}
        for task in as_completed(tasks):
            day = tasks[task]
            src, hashes = task.result()
            source_hashes[day.isoformat()] = hashes
            counts['sourceRaces'] += len(src['programs'])
            counts['resultWithoutProgram'] += len(set(src['results']) - set(src['programs']))
            for venue, race in sorted(src['programs']):
                program = src['programs'][venue, race]
                label = finish_index(program, src['results'].get((venue, race)))
                if label is None:
                    counts['notSixBoatUniqueFinish'] += 1
                    continue
                counts['eligibleSettled'] += 1
                b, glob, ids, classes, usable = extract_pre(program, src['previews'].get((venue, race)), day, venue, race)
                if not usable:
                    counts['modelMissingRequiredInput'] += 1
                rows.append((day.toordinal(), 9, venue, race, label, b, glob, ids, classes, usable))
    if len(source_hashes) != 30 or sorted(source_hashes) != [d.isoformat() for d in days]:
        raise ValueError('Incomplete September source dates')
    if counts['sourceRaces'] != counts['eligibleSettled'] + counts['notSixBoatUniqueFinish']:
        raise ValueError('Source population partition mismatch')
    rows.sort(key=lambda r: (r[0], r[2], r[3]))
    names = ('day_ordinal', 'month', 'venue', 'race_number', 'actual_index', 'current', 'global_features', 'racer_id', 'racer_class', 'usable')
    c = {name: np.asarray([r[i] for r in rows]) for i, name in enumerate(names)}
    c['year'] = np.asarray([2025]); c['combos'] = COMBO_TEXT
    keys(c)
    history = PlayerHistory(state)
    enriched = enrich(c, history)
    if enriched['history_through'][0] != date(2025, 8, 31).toordinal():
        raise ValueError('First September snapshot has wrong history start')
    # Exact allowlist: neither archived odds nor settlement amount exists in saved features.
    export = {k: enriched[k] for k in ('day_ordinal', 'month', 'venue', 'race_number', 'actual_index', 'usable',
                                      'current', 'global_features', 'history', 'reaction', 'history_through',
                                      'boat_names', 'history_names', 'reaction_names', 'combos', 'year')}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, **export)
    coverage = counts['eligibleSettled'] - counts['modelMissingRequiredInput']
    audit = {'protocolCommitSha': PRECOMMIT, 'protocolSha256': digest(PROTOCOL), 'sourceHashes': source_hashes,
             'sourceCommits': {k: v[1] for k, v in SOURCE.items()}, 'population': dict(counts),
             'comparisonRaces': coverage, 'modelCoverageOfEligible': coverage/counts['eligibleSettled'],
             'missingInputRate': counts['modelMissingRequiredInput']/counts['eligibleSettled'],
             'firstDay': START.isoformat(), 'lastDay': END.isoformat(), 'sourceDays': len(source_hashes),
             'q4Rows': 0, 'duplicateRaceKeys': 0,
             'sameDayHistoryLeakRows': int((enriched['history_through'] >= enriched['day_ordinal']).sum()),
             'historyStateStartSha256': digest(args.state), 'historyStateStartThrough': '2025-08-31',
             'historyStateEndThrough': date.fromordinal(history.state['lastDay']).isoformat(),
             'historyUpdateRacesEnd': history.state['updateRaces'],
             'featureCacheSha256': digest(args.output), 'oddsRead': False, 'payoutFieldRead': False,
             'septemberOpened': True, 'q4Opened': False, 'productionPromotion': False}
    dump(args.output.with_suffix('.json'), audit)
    print(json.dumps({'sourceDays': 30, 'eligible': counts['eligibleSettled'], 'usable': coverage}, ensure_ascii=False))


def baseline_prob(c):
    b = c['current'].astype(np.float64)
    if b.ndim != 3 or b.shape[1] != 6 or b.shape[2] < 18:
        raise ValueError('Invalid baseline boat feature shape')
    score = form_score(b)
    course = b[:, :, 17]
    fallback = np.broadcast_to(np.arange(1, 7, dtype=np.float64), course.shape)
    effective = np.where(np.isfinite(course), course, fallback).astype(int)
    prior = np.where((effective >= 1) & (effective <= 6), COURSE_PRIOR[np.clip(effective-1, 0, 5)], 0.0)
    raw = score + prior
    weight = np.exp((raw - raw.max(axis=1, keepdims=True))/SCORE_TEMPERATURE)
    total = weight.sum(axis=1)
    a, d, e = COMBOS.T
    wa, wd, we = weight[:, a], weight[:, d], weight[:, e]
    q = (wa/total[:, None])*(wd/(total[:, None]-wa))*(we/(total[:, None]-wa-wd))
    if not np.isfinite(q).all() or np.any(q < 0) or not np.allclose(q.sum(axis=1), 1, atol=1e-8):
        raise ValueError('Baseline probability invalid')
    return q


def parity(args):
    p = preregistration()
    if digest(ROOT/p['baseline']['sourcePath']) != p['baseline']['sourceSha256'] or digest(ROOT/p['baseline']['replayReferencePath']) != p['baseline']['replayReferenceSha256']:
        raise ValueError('Baseline source or reference implementation changed')
    with np.load(args.development, allow_pickle=False) as z:
        if set(z['month'].astype(int)) != {7, 8} or z['actual_index'].shape != z['usable'].shape:
            raise ValueError('Invalid development parity cache')
        take = z['usable'].astype(bool)
        c = {'current': z['current'][take], 'actual_index': z['actual_index'][take]}
    from v01516_forecast_audit import metrics
    measured = metrics(baseline_prob(c), c['actual_index'].astype(int))
    expected = json.loads((ROOT/'data/v01516_forecast_audit.json').read_text())['overall']
    if measured != expected:
        raise ValueError('Existing July-August Android v0.15.16 parity failed: ' + str({k: (measured.get(k),v) for k,v in expected.items() if measured.get(k)!=v}))
    dump(args.output, {'sourceSha256': p['baseline']['sourceSha256'], 'replayReferenceSha256': p['baseline']['replayReferenceSha256'],
                       'developmentRaces': measured['races'], 'metrics': measured, 'allReportedMetricsMatch': True,
                       'protocolCommitSha': PRECOMMIT})
    print('v0.15.16 development baseline parity passed', measured['races'])


def prediction_keys(c):
    take = c['usable'].astype(bool)
    return {name: c[name][take] for name in KEYS}, take


def infer_baseline(args):
    preregistration()
    c = load_features(args.features)
    k, take = prediction_keys(c)
    q = baseline_prob({'current': c['current'][take]})
    np.savez_compressed(args.output, p=q, **k)
    print('baseline races', len(q))


def infer_model(args):
    proto = preregistration()
    candidate = json.loads(CANDIDATE.read_text())
    if candidate['modelArtifactDigest'] != proto['candidate']['modelArtifactDigest'] or candidate['temperature'] != 1.0:
        raise ValueError('Forecast candidate changed')
    if digest(args.model/'manifest.json') != candidate['modelManifestSha256']:
        raise ValueError('Frozen model manifest mismatch')
    manifest = json.loads((args.model/'manifest.json').read_text())
    if manifest['variant'] != 'reaction' or manifest['temperature'] != 1.0 or manifest['marketInOutcomeModel'] or manifest['racerIdInModel']:
        raise ValueError('Non-frozen or market-dependent model')
    if manifest['codeSha256'] != code_hashes() or manifest['protocolSha256'] != candidate['protocolSha256']:
        raise ValueError('Original model code/protocol drift')
    c = load_features(args.features)
    schema = canonical([c[k].tolist() for k in ('boat_names', 'history_names', 'reaction_names')])
    if schema != candidate['featureSchemaSha256'] or schema != manifest['schemaSha256']:
        raise ValueError('Feature schema drift')
    k, take = prediction_keys(c)
    model_input = {name: c[name][take] if name not in ('combos', 'year', 'boat_names', 'history_names', 'reaction_names') else c[name]
                   for name in ('current', 'history', 'reaction', 'global_features', 'venue', 'race_number',
                                'month', 'day_ordinal', 'combos', 'year')}
    import lightgbm as lgb
    models = {}
    for stage in range(3):
        path = args.model / f'stage{stage}.txt'
        if digest(path) != candidate['assets'][path.name]['sha256'] or digest(path) != manifest['stages'][str(stage)]['sha256']:
            raise ValueError('Tree SHA drift')
        models[stage] = lgb.Booster(model_file=str(path))
    q = calibrated(predict(inputs(model_input, 'reaction'), 'fundamental', models), 1.0)
    if q.shape != (int(take.sum()), 120) or not np.isfinite(q).all() or np.any(q < 0) or not np.allclose(q.sum(axis=1), 1, atol=1e-5):
        raise ValueError('Invalid 120-way Model A predictions')
    first = np.column_stack([q[:, COMBOS[:, 0] == i].sum(axis=1) for i in range(6)])
    if not np.allclose(first.sum(axis=1), 1, atol=1e-5):
        raise ValueError('First-place marginal invalid')
    np.savez_compressed(args.output, p=q, **k)
    print('frozen Model A races', len(q))


def score(p, labels):
    n = len(labels)
    if n == 0: return {'races': 0}
    selected = p[np.arange(n), labels]
    ordering = np.argsort(-p, axis=1, kind='stable')
    marginal = np.column_stack([p[:, COMBOS[:, 0] == i].sum(axis=1) for i in range(6)])
    first_order = np.argsort(-marginal, axis=1, kind='stable')
    first_actual = COMBOS[labels, 0]
    confidence = p.max(axis=1); correct = (ordering[:, 0] == labels)
    ece = 0.0
    for i in range(10):
        m = (confidence >= i/10) & (confidence < (i+1)/10 if i<9 else confidence <= 1)
        if m.any(): ece += m.mean() * abs(correct[m].mean()-confidence[m].mean())
    out = {'races': n, 'trifectaLogloss': float(-np.log(np.maximum(selected, 1e-15)).mean()),
           'trifectaBrier': float((np.square(p).sum(axis=1)-2*selected+1).mean()),
           'topChoiceEce': float(ece), 'firstTop1': float((first_order[:, 0] == first_actual).mean()),
           'firstTop2': float(np.any(first_order[:, :2] == first_actual[:, None], axis=1).mean())}
    for k in (1, 2, 4, 8):
        out[f'trifectaTop{k}'] = float(np.any(ordering[:, :k] == labels[:, None], axis=1).mean())
    return out


def paired_bootstrap(days, model_p, base_p, labels, settings):
    idx = np.arange(len(labels))
    ml = -np.log(np.maximum(model_p[idx, labels], 1e-15))
    bl = -np.log(np.maximum(base_p[idx, labels], 1e-15))
    mb = (np.square(model_p).sum(axis=1)-2*model_p[idx, labels]+1)
    bb = (np.square(base_p).sum(axis=1)-2*base_p[idx, labels]+1)
    unique = np.unique(days)
    if len(unique) != 30: raise ValueError('Expected 30 calendar-day blocks')
    nday = np.asarray([(days == d).sum() for d in unique])
    totals = np.asarray([[v[days == d].sum() for d in unique] for v in (ml-bl, mb-bb)])
    rng = np.random.default_rng(settings['seed'])
    draw = rng.integers(0, len(unique), size=(settings['replicates'], len(unique)))
    den = nday[draw].sum(axis=1)
    return {name: {'point': float(v.mean()), 'ci95': np.percentile(totals[i][draw].sum(axis=1)/den,[2.5,97.5]).tolist()}
            for i,(name,v) in enumerate((('trifectaLogloss',ml-bl),('trifectaBrier',mb-bb)))}


def evaluate(args):
    p = preregistration()
    c = load_features(args.features)
    audit = json.loads(args.audit.read_text())
    parity_result = json.loads(args.parity.read_text())
    if audit['protocolCommitSha'] != PRECOMMIT or audit['featureCacheSha256'] != digest(args.features) or not parity_result['allReportedMetricsMatch']:
        raise ValueError('Source/parity provenance mismatch')
    k, take = prediction_keys(c)
    with np.load(args.model, allow_pickle=False) as a, np.load(args.baseline, allow_pickle=False) as b:
        for name in KEYS:
            if not np.array_equal(a[name], k[name]) or not np.array_equal(b[name], k[name]):
                raise ValueError('Model A/baseline population keys mismatch')
        ma, ba = a['p'], b['p']
    labels = c['actual_index'][take].astype(int)
    if ma.shape != ba.shape or ma.shape != (len(labels), 120):
        raise ValueError('Unpaired forecast probability shape')
    bootstrap = paired_bootstrap(k['day_ordinal'],ma,ba,labels,p['evaluation']['bootstrap'])
    mm, bm = score(ma,labels), score(ba,labels)
    coverage = audit['modelCoverageOfEligible']
    issues=[]
    if audit['sourceDays']!=30 or audit['q4Rows'] or audit['duplicateRaceKeys'] or audit['sameDayHistoryLeakRows'] or coverage < p['population']['coverageMinimumOfEligible']:
        issues.append('coverage/source/history guard failed')
    if len(labels)!=audit['comparisonRaces'] or min(k['day_ordinal']) < START.toordinal() or max(k['day_ordinal']) > END.toordinal():
        issues.append('paired population/date mismatch')
    primary = mm['trifectaLogloss'] < bm['trifectaLogloss'] and bootstrap['trifectaLogloss']['ci95'][1] < 0 and mm['trifectaBrier'] < bm['trifectaBrier']
    safety = mm['firstTop1'] >= bm['firstTop1'] and mm['trifectaTop4'] >= bm['trifectaTop4']
    decision = 'INCONCLUSIVE_FORECAST_HOLDOUT' if issues else ('PASS_FORECAST_HOLDOUT' if primary and safety else 'FAIL_FORECAST_HOLDOUT')
    days = {date.fromordinal(int(d)).isoformat(): {'races': int((k['day_ordinal']==d).sum()),
             'model': score(ma[k['day_ordinal']==d],labels[k['day_ordinal']==d]),
             'baseline': score(ba[k['day_ordinal']==d],labels[k['day_ordinal']==d])} for d in np.unique(k['day_ordinal'])}
    venues = {str(int(v)): {'races': int((k['venue']==v).sum()),
              'model': score(ma[k['venue']==v],labels[k['venue']==v]),
              'baseline': score(ba[k['venue']==v],labels[k['venue']==v])} for v in np.unique(k['venue'])}
    out={'decision': decision, 'protocolCommitSha': PRECOMMIT, 'protocolSha256': digest(PROTOCOL),
         'modelRunId': p['candidate']['modelRunId'], 'modelArtifactId': p['candidate']['modelArtifactId'],
         'modelArtifactDigest': p['candidate']['modelArtifactDigest'], 'modelManifestSha256':p['candidate']['modelManifestSha256'],
         'baselineSourceSha256': p['baseline']['sourceSha256'], 'population':audit['population'],
         'comparisonRaces':len(labels),'coverage':coverage,'missingInputRate':audit['missingInputRate'],
         'modelMetrics':mm,'baselineMetrics':bm,'pairedDayBlockBootstrap95':bootstrap,
         'primaryPass':bool(primary),'secondarySafetyPass':bool(safety),'validityIssues':issues,
         'septemberOpened':True,'q4Opened':False,'productionPromotion':False}
    result=dict(out, daily=days, venue=venues, dataAudit=audit, baselineParity=parity_result,
                modelPredictionsSha256=digest(args.model),baselinePredictionsSha256=digest(args.baseline))
    args.output.mkdir(parents=True, exist_ok=True)
    dump(args.output/'v016_sept_forecast_result.json',result)
    dump(args.output/'v016_sept_forecast_decision.json',out)
    dump(args.output/'v016_sept_forecast_data_audit.json',audit)
    def pct(x):return f'{x*100:.3f}%'
    lines=['# 2025年9月 Model A forecast-only 独立holdout','',f'- 事前登録commit: `{PRECOMMIT}`。評価日付: 2025-09-01〜2025-09-30。Q4未開封。',
           f"- 最終判定: **{decision}**。本番昇格なし。",
           f"- 9月出走表 {audit['population']['sourceRaces']:,}、結果が一意な6艇 {audit['population']['eligibleSettled']:,}、必要入力欠損 {audit['population']['modelMissingRequiredInput']:,}、同一レース比較 {len(labels):,}（coverage {pct(coverage)}）。",
           '- オッズ・払戻・期待値・購入判定は取得・評価せず、モデル再学習/特徴量/温度変更・後付け調整は行わない。',
           '', '| 指標 | Model A | Android v0.15.16純AI | 差 (A−baseline) |', '|---|---:|---:|---:|']
    for name in ('trifectaLogloss','trifectaBrier','firstTop1','firstTop2','trifectaTop1','trifectaTop2','trifectaTop4','trifectaTop8','topChoiceEce'):
        a,b=mm[name],bm[name]; unit='%' if name not in ('trifectaLogloss','trifectaBrier','topChoiceEce') else ''
        if unit: a,b=a*100,b*100
        lines.append(f'| {name} | {a:.6f}{unit} | {b:.6f}{unit} | {a-b:+.6f}{unit} |')
    lines += ['', f"- 対応する同一暦日を2,000回再標本化した95% CI（A−baseline）: logloss {bootstrap['trifectaLogloss']['ci95']}; Brier {bootstrap['trifectaBrier']['ci95']}。値が負ならAが改善。",
              f'- Primary通過: {primary}。Secondary safety通過: {safety}。妥当性上の重大問題: {issues or "なし"}。',
              '- 日別・場別の全診断値はresult.json。事後的な場選別・閾値変更には使わない。',
              '- baselineは同一ソースの固定式を再現し、既存7〜8月9,583レースの全報告指標一致を確認。',
              '- PASSでもAndroid互換LightGBM推論・日次履歴更新prototypeとPython parity/端末性能の検証が次段階。app/とReleaseは未変更。', '']
    (args.output/'v016_sept_forecast_report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'decision':decision,'population':len(labels),'modelLogloss':mm['trifectaLogloss'],'baselineLogloss':bm['trifectaLogloss'],'loglossCI':bootstrap['trifectaLogloss']['ci95']}))


def main():
    ap=argparse.ArgumentParser(); s=ap.add_subparsers(dest='cmd',required=True)
    b=s.add_parser('build'); b.add_argument('--state',type=Path,required=True); b.add_argument('--output',type=Path,required=True)
    pa=s.add_parser('parity'); pa.add_argument('--development',type=Path,required=True); pa.add_argument('--output',type=Path,required=True)
    ba=s.add_parser('baseline'); ba.add_argument('--features',type=Path,required=True); ba.add_argument('--output',type=Path,required=True)
    m=s.add_parser('model'); m.add_argument('--features',type=Path,required=True); m.add_argument('--model',type=Path,required=True); m.add_argument('--output',type=Path,required=True)
    e=s.add_parser('evaluate')
    for name in ('features','audit','model','baseline','parity','output'):e.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args(); {'build':build,'parity':parity,'baseline':infer_baseline,'model':infer_model,'evaluate':evaluate}[a.cmd](a)


if __name__=='__main__':main()
