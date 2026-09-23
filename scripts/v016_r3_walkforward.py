#!/usr/bin/env python3
"""Preregistered CORE r3 quarterly walk-forward evaluation on 2024 only.

This script never reads 2025. It re-fits only residual-small/place-small using
records strictly earlier than each evaluation quarter and keeps the r2 betting
policy fixed. Q1 remains explicitly incomplete until pre-2024 feature sidecars
exist; it is never treated as zero purchases.
"""
import argparse
import json
from datetime import date
from pathlib import Path
import numpy as np

from v016_core_research import canonical, digest, dump, normalize, summarize, tickets
from v016_r2_features import FEATURES, GLOBALS, PROTOCOL as R2_PROTOCOL, load
from v016_r2_model import COMBOS, context, metric, objective, predict, rows, subset, validate_combos

ROOT = Path(__file__).resolve().parents[1]
R3_PROTOCOL = ROOT / "data" / "v016_r3_protocol.json"
QUARTERS = {
    "q2": {"train_months": (1, 2), "valid_month": 3, "eval_months": (4, 5, 6), "eval_start": "2024-04-01"},
    "q3": {"train_months": (1, 2, 3, 4, 5), "valid_month": 6, "eval_months": (7, 8, 9), "eval_start": "2024-07-01"},
    "q4": {"train_months": (1, 2, 3, 4, 5, 6, 7, 8), "valid_month": 9, "eval_months": (10, 11, 12), "eval_start": "2024-10-01"},
}
FAMILIES = ("residual", "place")


def iso_from_ordinal(value):
    return date.fromordinal(int(value)).isoformat()


def fixed_policy():
    r3 = json.loads(R3_PROTOCOL.read_text())["inherits"]["betting_policy"]
    p = {
        "budget": int(r3["budget_yen"]),
        "maxPoints": int(r3["max_points"]),
        "minEv": float(r3["min_ev"]),
        "minProbability": float(r3["min_probability"]),
        "maxOdds": float(r3["max_odds"]),
    }
    r2 = json.loads(R2_PROTOCOL.read_text())["fixedPolicy"]
    if p != r2:
        raise ValueError("r3 betting policy drifted from frozen r2 policy")
    return p


def sorted_cache(path):
    c = load(path, 2024)
    validate_combos(c)
    order = np.lexsort((c["race_number"], c["venue"], c["day_ordinal"]))
    return subset(c, order)


def baseline_file(directory: Path):
    files = sorted(directory.rglob("*.npz"))
    if len(files) != 1:
        raise ValueError(f"expected one baseline prediction npz, found {len(files)}")
    return files[0]


def load_baseline(directory: Path, c):
    path = baseline_file(directory)
    with np.load(path, allow_pickle=False) as z:
        for key in ("day_ordinal", "venue", "race_number"):
            if not np.array_equal(z[key], c[key]):
                raise ValueError("r2 baseline/cache race alignment mismatch")
        p = z["p"].astype(np.float64)
    if p.shape != c["market_p"].shape:
        raise ValueError("r2 baseline probability shape mismatch")
    return p, path


def fit_models(c, family, quarter, output_dir: Path):
    import lightgbm as lgb

    if family not in FAMILIES or quarter not in QUARTERS:
        raise ValueError("unregistered r3 family/quarter")
    spec = QUARTERS[quarter]
    months = c["month"]
    train_mask = np.isin(months, spec["train_months"]) & c["usable"]
    valid_mask = (months == spec["valid_month"]) & c["usable"]
    train = subset(c, train_mask)
    valid = subset(c, valid_mask)
    if len(train["month"]) < 1000 or len(valid["month"]) < 500:
        raise ValueError("insufficient chronological training/validation races")
    last_fit_date = max(iso_from_ordinal(x) for x in np.concatenate([train["day_ordinal"], valid["day_ordinal"]]))
    if last_fit_date >= spec["eval_start"]:
        raise ValueError("chronology violation: fit/validation reaches evaluation quarter")

    r2proto = json.loads(R2_PROTOCOL.read_text())
    capacity = r2proto["capacities"]["small"]
    output_dir.mkdir(parents=True, exist_ok=True)
    models = {}
    stage_meta = {}
    contexts = [context(train), context(valid)]
    for stage in range(3):
        if family == "place" and stage == 0:
            continue
        k = 6 - stage
        datasets = []
        arrays = []
        for part, ctx in zip((train, valid), contexts):
            actual = COMBOS[part["actual_index"]]
            x, base, candidate = rows(ctx, np.arange(len(actual)), actual[:, :stage], family)
            y = (candidate == actual[:, stage, None]).astype(np.float32).ravel()
            if not np.all(y.reshape(-1, k).sum(axis=1) == 1):
                raise ValueError("invalid conditional label")
            ds = lgb.Dataset(x, label=y, init_score=base, free_raw_data=False,
                             reference=datasets[0] if datasets else None)
            datasets.append(ds)
            arrays.append((x, base))
        params = dict(capacity, objective=objective(k), metric="None", learning_rate=.03,
                      lambda_l2=20, num_threads=2, seed=1602, deterministic=True,
                      force_col_wise=True, verbosity=-1, feature_pre_filter=False)
        model = lgb.train(params, datasets[0], num_boost_round=400, valid_sets=[datasets[1]],
                          feval=metric(k), callbacks=[lgb.early_stopping(30, verbose=False)])
        x, base = arrays[1]
        logits = model.predict(x, raw_score=True, num_threads=2) + base
        loss = metric(k)(logits, datasets[1])[1]
        file = output_dir / f"stage{stage}.txt"
        model.save_model(str(file))
        models[stage] = model
        stage_meta[str(stage)] = {
            "iterations": int(model.best_iteration),
            "validationLogloss": float(loss),
            "sha256": digest(file),
            "features": int(x.shape[1]),
        }

    manifest = {
        "protocol": "v016-core-r3-walk-forward-v1",
        "family": family,
        "capacity": "small",
        "quarter": quarter,
        "trainRaces": int(len(train["month"])),
        "validationRaces": int(len(valid["month"])),
        "trainStart": min(iso_from_ordinal(x) for x in train["day_ordinal"]),
        "trainEnd": max(iso_from_ordinal(x) for x in train["day_ordinal"]),
        "validationStart": min(iso_from_ordinal(x) for x in valid["day_ordinal"]),
        "validationEnd": max(iso_from_ordinal(x) for x in valid["day_ordinal"]),
        "evalStart": spec["eval_start"],
        "r3ProtocolSha256": digest(R3_PROTOCOL),
        "r2ProtocolSha256": digest(R2_PROTOCOL),
        "featureSchemaSha256": canonical([FEATURES, GLOBALS]),
        "codeSha256": digest(__file__),
        "lightgbmVersion": lgb.__version__,
        "stages": stage_meta,
        "holdoutOpened": False,
    }
    dump(output_dir / "manifest.json", manifest)
    return models, manifest


def run(args):
    protocol = json.loads(R3_PROTOCOL.read_text())
    if protocol["holdout"]["state"] != "SEALED":
        raise ValueError("final holdout must remain sealed")
    if args.family not in FAMILIES or args.quarter not in QUARTERS:
        raise ValueError("unregistered r3 run")

    c = sorted_cache(args.cache)
    baseline, baseline_path = load_baseline(args.baseline_dir, c)
    spec = QUARTERS[args.quarter]
    eval_mask = np.isin(c["month"], spec["eval_months"])
    eval_c = subset(c, eval_mask)
    eval_baseline = baseline[eval_mask]
    if len(eval_c["month"]) < 5000:
        raise ValueError("incomplete evaluation quarter")
    expected_months = set(spec["eval_months"])
    if set(map(int, np.unique(eval_c["month"]))) != expected_months:
        raise ValueError("INCOMPLETE_QUARTER")

    model_dir = args.output_dir / "model"
    models, manifest = fit_models(c, args.family, args.quarter, model_dir)
    p = predict(eval_c, args.family, models).astype(np.float64)
    p[~eval_c["usable"]] = 0

    # Direct result-leak guard: changing evaluation labels must not change predictions.
    mutated = {k: (v.copy() if hasattr(v, "copy") else v) for k, v in eval_c.items()}
    mutated["actual_index"] = (mutated["actual_index"] + 37) % 120
    p_mut = predict(mutated, args.family, models).astype(np.float64)
    p_mut[~mutated["usable"]] = 0
    if not np.allclose(p, p_mut, atol=1e-12):
        raise ValueError("future-label mutation changed predictions")

    good = eval_c["usable"]
    actual = eval_c["actual_index"][good]
    market = normalize(eval_c["market_p"][good])
    wf = p[good]
    static = eval_baseline[good]
    ix = np.arange(len(actual))
    logloss = lambda q: float(-np.log(np.maximum(q[ix, actual], 1e-15)).mean())
    metrics = {
        "walkForwardLogloss": logloss(wf),
        "staticR2Logloss": logloss(static),
        "marketLogloss": logloss(market),
        "deltaVsStatic": logloss(wf) - logloss(static),
        "deltaVsMarket": logloss(wf) - logloss(market),
        "usableRaces": int(good.sum()),
        "allRaces": int(len(good)),
    }

    policy = fixed_policy()
    chosen, units, counts = tickets(p, eval_c["odds"], policy)
    wins = (units * (chosen == eval_c["actual_index"][:, None])).sum(axis=1)
    stake = np.where(counts > 0, policy["budget"], 0)
    payout = wins * eval_c["amount"]
    total = summarize(stake, payout, counts)
    months = {
        str(m): summarize(stake[eval_c["month"] == m], payout[eval_c["month"] == m], counts[eval_c["month"] == m])
        for m in sorted(expected_months)
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "protocol": protocol["protocol"],
        "family": args.family,
        "capacity": "small",
        "quarter": args.quarter,
        "manifest": manifest,
        "total": total,
        "months": months,
        "predictionMetrics": metrics,
        "fixedPolicy": policy,
        "featureCacheSha256": digest(args.cache),
        "baselinePredictionSha256": digest(baseline_path),
        "futureLabelMutationInvariant": True,
        "finalHoldoutOpened": False,
        "releaseQualified": False,
    }
    dump(args.output_dir / "result.json", result)
    np.savez_compressed(args.output_dir / "predictions.npz", p=p,
                        day_ordinal=eval_c["day_ordinal"], venue=eval_c["venue"], race_number=eval_c["race_number"])
    print(json.dumps({"family": args.family, "quarter": args.quarter, "total": total, "metrics": metrics}, ensure_ascii=False))


def combine_totals(rows):
    stake = sum(r["total"]["stake"] for r in rows)
    payout = sum(r["total"]["payout"] for r in rows)
    largest = max((r["total"].get("largestHitPayout", 0) for r in rows), default=0)
    purchases = sum(r["total"]["purchaseRaces"] for r in rows)
    hits = sum(r["total"]["hits"] for r in rows)
    return {
        "purchaseRaces": int(purchases),
        "hits": int(hits),
        "stake": int(stake),
        "payout": int(payout),
        "profit": int(payout - stake),
        "roi": float(100 * payout / stake) if stake else 0.0,
        "largestHitPayout": int(largest),
        "largestHitShare": float(100 * largest / payout) if payout else 0.0,
        "roiWithoutLargestHit": float(100 * (payout - largest) / stake) if stake else 0.0,
    }


def aggregate(args):
    rows = [json.loads(p.read_text()) for p in sorted(args.input.rglob("result.json"))]
    expected = {(f, q) for f in FAMILIES for q in QUARTERS}
    got = {(r["family"], r["quarter"]) for r in rows}
    if len(rows) != 6 or got != expected:
        raise ValueError(f"incomplete r3 matrix: {got}")
    protocol = json.loads(R3_PROTOCOL.read_text())
    families = {}
    for family in FAMILIES:
        rr = [r for r in rows if r["family"] == family]
        weights = np.asarray([r["predictionMetrics"]["usableRaces"] for r in rr], dtype=float)
        def weighted(key):
            return float(np.average([r["predictionMetrics"][key] for r in rr], weights=weights))
        metrics = {
            "walkForwardLogloss": weighted("walkForwardLogloss"),
            "staticR2Logloss": weighted("staticR2Logloss"),
            "marketLogloss": weighted("marketLogloss"),
        }
        metrics["deltaVsStatic"] = metrics["walkForwardLogloss"] - metrics["staticR2Logloss"]
        metrics["deltaVsMarket"] = metrics["walkForwardLogloss"] - metrics["marketLogloss"]
        total = combine_totals(rr)
        calibration_ok = metrics["deltaVsStatic"] < 0 and metrics["deltaVsMarket"] < 0
        families[family] = {
            "q2ToQ4": total,
            "predictionMetrics": metrics,
            "calibrationGate": calibration_ok,
            "quarterResults": rr,
        }

    continue_families = [f for f, v in families.items() if v["calibrationGate"]]
    out = {
        "runId": args.run,
        "protocol": protocol["protocol"],
        "r3ProtocolSha256": digest(R3_PROTOCOL),
        "q1State": "BLOCKED_UNTIL_PRE2024_FEATURE_SIDECAR_EXISTS",
        "annualComplete": False,
        "annualPass": False,
        "families": families,
        "continueToQ1DataBuild": continue_families,
        "decision": "build_missing_pre2024_sidecar" if continue_families else "reject_r3_walk_forward_hypothesis",
        "finalHoldoutOpened": False,
        "releaseQualified": False,
        "notes": [
            "Q2-Q4 are development evidence only; no annual pass is possible while Q1 is incomplete.",
            "Betting thresholds/budget are frozen from r2 and were not tuned to these results.",
            "2025-10-01..2025-12-31 was never read.",
        ],
    }
    dump(args.output, out)

    lines = [
        "# v0.16 CORE r3 walk-forward partial result",
        "",
        f"Run: {args.run}",
        "",
        "Q1 is intentionally BLOCKED until a pre-2024 feature sidecar exists; it is not counted as zero purchases.",
        "",
        "| family | Q2-Q4 ROI | purchases | hits | ROI w/o largest | WF logloss | static r2 | market | calibration gate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for family in FAMILIES:
        v = families[family]; t = v["q2ToQ4"]; m = v["predictionMetrics"]
        lines.append(
            f"| {family}-small | {t['roi']:.2f}% | {t['purchaseRaces']} | {t['hits']} | {t['roiWithoutLargestHit']:.2f}% | "
            f"{m['walkForwardLogloss']:.6f} | {m['staticR2Logloss']:.6f} | {m['marketLogloss']:.6f} | "
            f"{'PASS' if v['calibrationGate'] else 'FAIL'} |"
        )
    lines += [
        "",
        f"Decision: {out['decision']}",
        "",
        "No production promotion. Final 2025 Q4 holdout remains sealed.",
    ]
    args.output.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"decision": out["decision"], "continue": continue_families}, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--family", choices=FAMILIES, required=True)
    r.add_argument("--quarter", choices=tuple(QUARTERS), required=True)
    r.add_argument("--cache", type=Path, required=True)
    r.add_argument("--baseline-dir", type=Path, required=True)
    r.add_argument("--output-dir", type=Path, required=True)
    a = sub.add_parser("aggregate")
    a.add_argument("--input", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--run", required=True)
    args = p.parse_args()
    if args.command == "run":
        run(args)
    else:
        aggregate(args)
