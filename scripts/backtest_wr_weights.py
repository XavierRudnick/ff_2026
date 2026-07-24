#!/usr/bin/env python3
"""Backtest WR board weights: 2024 features -> actual 2025 PPR results.

Features come from ``wr/wr_stats_2024.csv`` restricted to information that
existed after the 2024 season (2024 stats plus the normalized 2025 preseason
market line). ``PPR_Points_2025`` and the preseason rank column are outcome
data and are excluded by :data:`wr_model.LEAKAGE_COLUMNS`. Outcomes come from
``wr/wr_stats_act_2025.csv``.

The current board weights are evaluated first, through the same scoring code
the board uses. The board's trend category needs 2023 stats that do not
exist, so its metrics are all missing and the scorer renormalizes the
remaining categories -- exactly what the board itself does with missing data.
Then a grid search over the non-negative simplex (step 0.05) optimizes the
market / production / opportunity / youth split, with a player-bootstrap
stability check so we prefer a stable plateau over a one-season spike.
"""

import argparse
import itertools
import random

from wr_model import (
    LEAKAGE_COLUMNS, MAX_AIR_SHARE, MAX_TARGET_SHARE, WR_DIR,
    clean_share, dedupe_players, evaluate_ranking, match_report, norm_name,
    number, percentile, read_rows, score_players, spearman, weighted,
)

FEATURES_CSV = WR_DIR / "wr_stats_2024.csv"
OUTCOMES_CSV = WR_DIR / "wr_stats_act_2025.csv"

# The board's category weights as of the last commit (see build_wr_board.py
# history): market .35, production .25, opportunity .25, trend .15.
CURRENT_WEIGHTS = {
    "market": 0.35,
    "production": 0.25,
    "opportunity": 0.25,
    "trend": 0.15,
}

# 2024-season analogs of the board's metric groups. "trend" names columns
# that do not exist in the 2024 file (they would need 2023 data), so the
# category goes missing and is renormalized away, mirroring board behavior.
BACKTEST_METRICS = {
    "market": [("normalized_line", 1.0)],
    "production": [("FPTS/G", 0.40), ("XFP", 0.30), ("YPRR", 0.30)],
    "opportunity": [
        ("TGT/G", 0.28),
        ("Target_Share", 0.25),
        ("air_pct", 0.18),
        ("WOPR", 0.20),
        ("RZ_TGT_PCT", 0.09),
    ],
    "trend": [
        ("TGT/G_diff_2024_minus_2023", 0.30),
        ("Target_Share_diff_2024_minus_2023", 0.25),
        ("air_pct_diff_2024_minus_2023", 0.15),
        ("WOPR_diff_2024_minus_2023", 0.15),
        ("YPRR_diff_2024_minus_2023", 0.15),
    ],
}

OPTIMIZE_METRICS = {
    "market": BACKTEST_METRICS["market"],
    "production": BACKTEST_METRICS["production"],
    "opportunity": BACKTEST_METRICS["opportunity"],
    "youth": [("neg_age", 1.0)],
}

FEATURE_COLUMNS = [
    "G", "Age", "FPTS/G", "XFP", "YPRR", "TGT/G", "Target_Share",
    "air_pct", "WOPR", "RZ_TGT_PCT", "normalized_line",
]

MIN_GAMES_2024 = 3
MIN_TGT_PER_GAME = 2.5
MIN_GAMES_PER_GAME_EVAL = 4


def load_candidates():
    """Load, dedupe, clean, and filter the 2024 feature rows; attach 2025
    outcomes. Returns (candidates, audit_lines)."""
    audit = []
    raw = read_rows(FEATURES_CSV)
    forbidden = LEAKAGE_COLUMNS.intersection(FEATURE_COLUMNS)
    if forbidden:
        raise RuntimeError(f"leakage: outcome columns used as features: {forbidden}")

    rows, dupes = dedupe_players(raw)
    audit.append(f"2024 file: {len(raw)} rows -> {len(rows)} players after "
                 f"collapsing {len(dupes)} multi-team players")
    if dupes:
        audit.append("  multi-team (aggregate row kept): " + ", ".join(sorted(dupes)))

    for row in rows:
        for col in FEATURE_COLUMNS:
            row[col] = number(row.get(col))
        cleaned = clean_share(row["Target_Share"], MAX_TARGET_SHARE)
        if cleaned != row["Target_Share"]:
            audit.append(f"  impossible target share -> missing: {row['Player']} "
                         f"({row['Target_Share']})")
        row["Target_Share"] = cleaned
        row["air_pct"] = clean_share(row["air_pct"], MAX_AIR_SHARE)
        row["neg_age"] = -row["Age"] if row["Age"] is not None else None

    outcomes = read_rows(OUTCOMES_CSV)
    left_only, right_only = match_report(rows, outcomes)
    audit.append(f"outcome join: {len(left_only)} unmatched 2024 names, "
                 f"{len(right_only)} unmatched 2025 names")
    for name in left_only:
        audit.append(f"  2024-only: {name}")
    for name in right_only:
        audit.append(f"  2025-only: {name}")

    by_key = {norm_name(r["Player"]): r for r in outcomes}
    candidates = []
    for row in rows:
        out = by_key.get(norm_name(row["Player"]))
        if out is None:
            continue
        row["actual_ppr_2025"] = number(out.get("FPTS"))
        row["actual_ppr_pg_2025"] = number(out.get("FPTS/G"))
        row["actual_g_2025"] = number(out.get("G"))
        if row["actual_ppr_2025"] is None:
            continue
        if (row["G"] or 0) < MIN_GAMES_2024:
            continue
        if (row["TGT/G"] or 0) < MIN_TGT_PER_GAME and row["normalized_line"] is None:
            continue
        candidates.append(row)
    audit.append(f"backtest pool: {len(candidates)} WRs with >= {MIN_GAMES_2024} "
                 f"games in 2024 and (>= {MIN_TGT_PER_GAME} targets/game or a "
                 f"2025 preseason line)")
    audit.append(f"  with a 2025 preseason market line: "
                 f"{sum(1 for r in candidates if r['normalized_line'] is not None)}")
    return candidates, audit


def evaluate(candidates, score_field="model_score"):
    """Evaluate a score column against total PPR and PPR/G outcomes."""
    total = evaluate_ranking([
        (row[score_field], row["actual_ppr_2025"])
        for row in candidates if row.get(score_field) is not None
    ])
    pg_pool = [
        row for row in candidates
        if row.get(score_field) is not None
        and (row["actual_g_2025"] or 0) >= MIN_GAMES_PER_GAME_EVAL
        and row["actual_ppr_pg_2025"] is not None
    ]
    per_game = evaluate_ranking([
        (row[score_field], row["actual_ppr_pg_2025"]) for row in pg_pool
    ])
    return {"total": total, "per_game": per_game}


def fmt_eval(result):
    lines = []
    for label, r in (("2025 total PPR", result["total"]),
                     ("2025 PPR per game", result["per_game"])):
        lines.append(
            f"  vs {label} (n={r['n']}): spearman {r['spearman']:.3f}, "
            f"rank MAE {r['rank_mae']:.1f}, "
            f"top-12 {r['top12_hits']}/12, top-24 {r['top24_hits']}/24, "
            f"top-36 {r['top36_hits']}/36"
        )
    return "\n".join(lines)


def combo_model_score(row, weights):
    parts = []
    for category, weight in weights.items():
        score = row.get(f"{category}_score")
        if category == "market" and score is None:
            score = 50.0
        parts.append((score, weight))
    return weighted(parts)


def simplex(step):
    """All non-negative 4-weight combinations that sum to one."""
    n = round(1 / step)
    for a, b, c in itertools.combinations_with_replacement(range(n + 1), 3):
        # a <= b <= c partition the [0, n] range into four segments.
        yield (a / n, (b - a) / n, (c - b) / n, (n - c) / n)


def objective(candidates, weights):
    for row in candidates:
        row["_opt_score"] = combo_model_score(row, weights)
    result = evaluate(candidates, "_opt_score")
    return (result["total"]["spearman"] + result["per_game"]["spearman"]) / 2, result


def bootstrap_spearman(candidates, weights, resamples, seed):
    """Mean/worst Spearman vs total PPR across player resamples."""
    rng = random.Random(seed)
    pairs = [
        (combo_model_score(row, weights), row["actual_ppr_2025"])
        for row in candidates
    ]
    stats = []
    for _ in range(resamples):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        scores = [s for s, _ in sample]
        if len(set(scores)) < 2:
            continue
        stats.append(spearman(scores, [a for _, a in sample]))
    stats.sort()
    return {
        "mean": sum(stats) / len(stats),
        "p05": stats[int(0.05 * len(stats))],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", type=float, default=0.05,
                        help="grid step over the weight simplex")
    parser.add_argument("--resamples", type=int, default=300,
                        help="bootstrap resamples for the stability check")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    candidates, audit = load_candidates()
    print("=== Data audit ===")
    print("\n".join(audit))

    print("\n=== Current board weights (market .35 / production .25 / "
          "opportunity .25 / trend .15) ===")
    print("trend metrics need 2023 data that does not exist, so the scorer "
          "renormalizes to\nmarket .412 / production .294 / opportunity .294 "
          "-- the board's own missing-data rule.")
    score_players(
        candidates, BACKTEST_METRICS, CURRENT_WEIGHTS, games_field="G",
        shrink_categories=("production", "opportunity", "trend"),
        neutral_categories=("market",),
    )
    ages = [row.get("neg_age") for row in candidates]
    for row in candidates:
        row["youth_score"] = percentile(ages, row.get("neg_age"))
    current_result = evaluate(candidates)
    print(fmt_eval(current_result))

    print("\n=== Single-category baselines ===")
    for category in OPTIMIZE_METRICS:
        pool = [r for r in candidates if r.get(f"{category}_score") is not None]
        result = evaluate(pool, f"{category}_score")
        print(f"{category} alone (n={result['total']['n']}):")
        print(fmt_eval(result))

    print(f"\n=== Grid search: market/production/opportunity/youth, "
          f"step {args.step} ===")
    scored = []
    for market, production, opportunity, youth in simplex(args.step):
        weights = {"market": market, "production": production,
                   "opportunity": opportunity, "youth": youth}
        value, result = objective(candidates, weights)
        scored.append((value, weights, result))
    scored.sort(key=lambda item: -item[0])

    print("top 10 combos by mean Spearman (total, per-game):")
    for value, weights, result in scored[:10]:
        print(f"  mkt {weights['market']:.2f} prod {weights['production']:.2f} "
              f"opp {weights['opportunity']:.2f} youth {weights['youth']:.2f}"
              f" -> {value:.4f} (total {result['total']['spearman']:.3f} / "
              f"pg {result['per_game']['spearman']:.3f}, "
              f"top-24 {result['total']['top24_hits']}, "
              f"top-36 {result['total']['top36_hits']})")

    best_value = scored[0][0]
    plateau = [item for item in scored if item[0] >= best_value - 0.005]
    print(f"\nplateau within 0.005 of best: {len(plateau)} combos")

    print(f"\n=== Bootstrap stability ({args.resamples} resamples) ===")
    finalists = plateau[:8] + [
        (None, dict(zip(("market", "production", "opportunity", "youth"), w)), None)
        for w in [(0.40, 0.30, 0.30, 0.0), (0.35, 0.35, 0.30, 0.0),
                  (0.40, 0.30, 0.25, 0.05), (0.35, 0.30, 0.30, 0.05)]
    ]
    seen = set()
    for _, weights, _ in finalists:
        key = tuple(round(weights[c], 2) for c in
                    ("market", "production", "opportunity", "youth"))
        if key in seen:
            continue
        seen.add(key)
        boot = bootstrap_spearman(candidates, weights, args.resamples, args.seed)
        value, result = objective(candidates, weights)
        print(f"  mkt {key[0]:.2f} prod {key[1]:.2f} opp {key[2]:.2f} "
              f"youth {key[3]:.2f}: point {value:.4f}, boot mean "
              f"{boot['mean']:.4f}, boot 5th pct {boot['p05']:.4f}")

    print("\nPick round weights on the plateau with the strongest bootstrap "
          "floor, then set them\nas the defaults in build_wr_board.py "
          "(CATEGORY_WEIGHTS) and rerun this script to confirm.")


if __name__ == "__main__":
    main()
