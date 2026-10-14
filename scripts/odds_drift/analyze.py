"""Winner-selected odds drift diagnostic. No prediction or BUY/SKIP evaluation."""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path.cwd() / "odds_drift_work"
COMBOS = ['-'.join(map(str, p)) for p in itertools.permutations(range(1, 7), 3)]
RANKS = ['1', '2-3', '4-6', '7-12', '13-30', '31+']
TIMES = ['<=4', '4-6', '6-8', '8-10', '>10']
SIZES = [1, 2, 3, 6, 18, 90]
PRIOR = dict(zip(RANKS, [0.92, 0.86, 0.87, 0.88, 0.96, 0.96]))

def rank_bucket(rank):
    return next(label for label, bound in zip(RANKS, [1, 3, 6, 12, 30, 120]) if rank <= bound)

def time_bucket(minutes):
    return next(label for label, bound in zip(TIMES, [4, 6, 8, 10, math.inf]) if minutes <= bound)

def read_csv(path):
    return list(csv.DictReader(path.read_text(encoding='utf-8-sig').splitlines()))

def parse_snapshot(row):
    code = row['レースコード'].strip()
    if len(code) != 12 or not code.isdigit():
        raise ValueError('invalid_race_code')
    odds = {combo: float(row['3連単_' + combo]) for combo in COMBOS}
    if not all(math.isfinite(v) and v > 0 for v in odds.values()):
        raise ValueError('nonpositive_or_nonfinite_snapshot')
    fetched = datetime.fromisoformat(row['取得日時'])
    if fetched.tzinfo is None:
        raise ValueError('naive_timestamp')
    close = datetime.fromisoformat(row['レース日'] + 'T' + row['締切時刻'] + ':00+09:00')
    minutes = (close - fetched).total_seconds() / 60
    if close.date().strftime('%Y%m%d') != code[:8]:
        raise ValueError('date_mismatch')
    ordered = sorted(odds, key=lambda c: (odds[c], c))
    ranks = {c: i + 1 for i, c in enumerate(ordered)}
    return code, odds, ranks, minutes

def stats(frame, bootstrap=False):
    if len(frame) == 0:
        return {'n': 0, 'days': 0, 'venues': 0}
    r = frame.ratio.to_numpy()
    d = frame.difference.to_numpy()
    out = {'n': len(r), 'days': int(frame.date.nunique()), 'venues': int(frame.venue.nunique()),
           'medianRatio': float(np.median(r)), 'meanRatio': float(np.mean(r)),
           'medianOddsDifference': float(np.median(d)), 'medianAbsoluteOddsDifference': float(np.median(np.abs(d))),
           'p10': float(np.quantile(r, .10)), 'p25': float(np.quantile(r, .25)),
           'p75': float(np.quantile(r, .75)), 'p90': float(np.quantile(r, .90)),
           'fallPct': float(100 * np.mean(d < -1e-8)), 'risePct': float(100 * np.mean(d > 1e-8)),
           'unchangedPct': float(100 * np.mean(np.abs(d) <= 1e-8)),
           'medianMinutes': float(frame.minutes.median()),
           'androidMedianFinalOverEstimate': float(np.median(frame.final_odds / frame.android_estimate)),
           'androidOverestimatePct': float(100 * np.mean(frame.android_estimate - frame.final_odds > 1e-8)),
           'meanNormalizedPreImpliedProb': float(frame.pre_implied_prob.mean()),
           'tieWinnerPct': float(100 * frame.tied_odds.mean()),
           'medianFinalMinusPreRank': float(frame.final_rank_delta.dropna().median()) if frame.final_rank_delta.notna().any() else None}
    if bootstrap and out['days'] >= 2:
        rng = np.random.default_rng(20261014)
        groups = [g.ratio.to_numpy() for _, g in frame.groupby('date', sort=True)]
        medians = [np.median(np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])) for _ in range(800)]
        out['dayBootstrapMedian95'] = [float(v) for v in np.quantile(medians, [.025, .975])]
    return out

def grouped(frame, columns, labels=None, bootstrap=False):
    results = []
    if labels is None:
        groups = frame.groupby(columns, sort=True, observed=True)
        for key, group in groups:
            key = key if isinstance(key, tuple) else (key,)
            results.append(dict(zip(columns, key)) | stats(group, bootstrap))
    else:
        for values in itertools.product(*labels):
            mask = pd.Series(True, index=frame.index)
            for column, value in zip(columns, values):
                mask &= frame[column] == value
            results.append(dict(zip(columns, values)) | stats(frame[mask], bootstrap))
    return results

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root
    manifest = json.loads((root / 'output/odds_drift_source_manifest_20261014.json').read_text())
    if any(f['status'] != 'ok' for f in manifest['files']):
        raise SystemExit('Manifest contains failed downloads')
    dates = sorted({f['date'] for f in manifest['files']})
    counters = Counter()
    exclusions = []
    records = []
    opportunities = Counter()
    expected = Counter()
    daily = []
    for day in dates:
        pre = read_csv(root / f'cache/od3_{day}.csv')
        payouts = read_csv(root / f'cache/payouts_{day}.csv')
        if len({r['レースコード'] for r in pre}) != len(pre) or len({r['レースコード'] for r in payouts}) != len(payouts):
            raise SystemExit('Duplicate race code in ' + day)
        payout_map = {r['レースコード']: r for r in payouts}
        counters['raw_od3_rows'] += len(pre)
        counters['payout_rows'] += len(payouts)
        day_matched = 0
        for row in pre:
            try:
                code, odds, ranks, minutes = parse_snapshot(row)
            except (ValueError, KeyError) as exc:
                reason = str(exc) if isinstance(exc, ValueError) else 'missing_snapshot_field'
                counters['excluded_' + reason] += 1
                exclusions.append({'race_code': row.get('レースコード'), 'reason': reason})
                continue
            counters['complete_positive_120_rows'] += 1
            if not (0 <= minutes <= 15):
                reason = 'snapshot_after_scheduled_close' if minutes < 0 else 'snapshot_more_than_15min_before_close'
                counters['excluded_' + reason] += 1
                exclusions.append({'race_code': code, 'reason': reason, 'minutes': minutes})
                continue
            counters['time_valid_rows'] += 1
            payout = payout_map.get(code)
            if payout is None:
                reason = 'missing_payout_race'
            elif payout.get('3連単_組番') not in odds:
                reason = 'missing_or_noncanonical_winner'
            else:
                try:
                    amount = int(payout['3連単_払戻金'].replace(',', ''))
                    if amount <= 0:
                        raise ValueError()
                except (ValueError, KeyError):
                    reason = 'invalid_winning_payout'
                else:
                    reason = None
            if reason:
                counters['excluded_' + reason] += 1
                exclusions.append({'race_code': code, 'reason': reason})
                continue
            winner = payout['3連単_組番']
            rank = ranks[winner]
            bucket = rank_bucket(rank)
            pre_odds = odds[winner]
            final_odds = amount / 100
            invsum = sum(1 / v for v in odds.values())
            probs = {c: (1 / v) / invsum for c, v in odds.items()}
            for c in COMBOS:
                b = rank_bucket(ranks[c])
                opportunities[b] += 1
                expected[b] += probs[c]
            try:
                final_rank = int(payout['3連単_人気'])
                if not (1 <= final_rank <= 120):
                    final_rank = None
            except (ValueError, KeyError):
                final_rank = None
            base = PRIOR[bucket]
            effective = 1 + (base - 1) * min(minutes / 8, 1)
            # Kotlin round() uses ties to even, as does Python round().
            estimate = round(max(1., pre_odds * effective) * 10) / 10
            records.append({'race_code': code, 'date': day, 'month': day[:7], 'venue': code[8:10],
                            'winner': winner, 'minutes': minutes, 'time_bucket': time_bucket(minutes),
                            'pre_rank': rank, 'rank_bucket': bucket, 'pre_odds': pre_odds,
                            'final_odds': final_odds, 'ratio': final_odds/pre_odds, 'difference': final_odds-pre_odds,
                            'pre_implied_prob': probs[winner], 'android_estimate': estimate,
                            'tied_odds': sum(v == pre_odds for v in odds.values()) > 1,
                            'min_tie_rank': 1 + sum(v < pre_odds for v in odds.values()),
                            'final_rank': final_rank, 'final_rank_delta': (final_rank-rank) if final_rank else None})
            day_matched += 1
        daily.append({'date': day, 'rawOd3': len(pre), 'payoutRows': len(payouts), 'matched': day_matched})
    frame = pd.DataFrame(records)
    frame['odds_band'] = pd.cut(frame.pre_odds, [0, 10, 30, 100, 300, math.inf], labels=['<=10', '10-30', '30-100', '100-300', '>300'], right=True)
    selected = frame.rank_bucket.value_counts()
    bias = []
    for label, size in zip(RANKS, SIZES):
        count = int(selected.get(label, 0))
        share = count / len(frame)
        bias.append({'rankBucket': label, 'combinationsPerRace': size, 'allCombinationPct': size/120*100,
                     'winnerN': count, 'winnerPct': share*100, 'selectionEnrichmentVsUniform': share/(size/120),
                     'observedFractionOfCellFinalOddsPct': count/opportunities[label]*100,
                     'normalizedPreImpliedExpectedWinnerPct': expected[label]/len(frame)*100})
    frame['minimum_tie_bucket'] = frame.min_tie_rank.map(rank_bucket)
    trimmed = frame[(frame.ratio >= .25) & (frame.ratio <= 4)]
    payload = {'schemaVersion': 1, 'generatedAt': datetime.now(timezone.utc).isoformat(),
               'sourceRef': manifest['sourceRef'], 'sourceRepo': 'BoatraceCSV/boatracecsv.github.io',
               'androidRef': 'faf0807d714aeb292899ced0331974a3cd1a9d85',
               'estimand': 'realizedWinningPayoutPer100JPY / preCloseWinningCombinationOdds; winner-selected, not a 120-way final-odds estimate',
               'period': {'from': dates[0], 'through': dates[-1], 'days': len(dates)},
               'filters': {'canonical120PositiveFinite': True, 'minutesRangeInclusive': [0,15], 'noRatioBasedPrimaryExclusions': True, 'noModelOrBuySkipFilter': True},
               'counters': dict(counters), 'overall': stats(frame, True),
               'byRank': grouped(frame, ['rank_bucket'], [RANKS], True),
               'byTime': grouped(frame, ['time_bucket'], [TIMES], True),
               'byTimeRank': grouped(frame, ['time_bucket','rank_bucket'], [TIMES,RANKS], True),
               'byMonthRank': grouped(frame, ['month','rank_bucket']),
               'byOddsBand': grouped(frame, ['odds_band']),
               'bias': bias, 'dailyCoverage': daily,
               'sensitivity': {'ratio025to4Removed': len(frame)-len(trimmed), 'ratio025to4ByRank': grouped(trimmed,['rank_bucket'],[RANKS]),
                               'minimumTieRankBuckets': grouped(frame,['minimum_tie_bucket'],[RANKS]),
                               'unresolvedRefundsAndDeadHeats': 'not identifiable from the one-combination payout CSV; retained as diagnostic contamination risk'},
               'currentAndroidPrior': {'baseFactors': PRIOR, 'effectiveFactor': '1 + (baseFactor - 1) * clamp(minutes/8,0,1)'},
               'decision': 'KEEP provisional Android priors pending full-combination final snapshots; do not fit or promote from winner-selected payouts',
               'bootstrap': {'replicates': 800, 'seed': 20261014, 'unit': 'calendar day', 'interpretation': 'sampling uncertainty of biased diagnostic only'}}
    (root / 'output/odds_drift_calibration_20261014.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    frame.to_csv(root / 'output/odds_drift_winner_matches_20261014.csv', index=False)
    (root / 'output/odds_drift_exclusions_20261014.json').write_text(json.dumps(exclusions, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'period':payload['period'], 'counters':payload['counters'], 'overall':payload['overall'], 'byRank':payload['byRank'], 'byTime':payload['byTime'], 'bias':bias}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
