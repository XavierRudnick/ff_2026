#!/usr/bin/env python3
"""Find underrated 2026 WR sleepers and backtest the sleeper profile.

A sleeper here is not just a low-ranked player: it is a receiver the
consensus (last season's finish plus the 2026 betting market) prices outside
the top 24 whose underlying profile says the price is too low.

The upside profile is fixed a priori and validated on 2024 -> 2025 before it
is applied to 2026. Signals, all computable the day after the season ends:

* youth        -- breakouts cluster on ages 22-25
* efficiency   -- yards per route run (production per chance, not volume)
* role gap     -- air-yard share minus target share: a downfield role bigger
                  than the target volume it has received so far
* regression   -- scored under expected fantasy points (XFP), so scoring
                  should catch up to usage
* route volume -- routes per game: already on the field, waiting for targets

Breakout labels for the backtest (2025 outcomes):
* rank gain     -- finished 24+ WR ranks better than the 2024 finish
* top-36 arrival-- outside the top 36 in 2024, inside it in 2025
* PPR/G growth  -- +3.0 PPR per game on 8+ games

The Michael Wilson check is reported, never optimized for: the signal
weights above are set from breakout research priors, and an equal-weight
variant is reported alongside to show the ordering is not weight-sensitive.
"""

import argparse
import csv
import statistics

from wr_model import (
    MAX_AIR_SHARE, MAX_TARGET_SHARE, WR_DIR, clean_share, dedupe_players,
    match_report, norm_name, number, percentile, read_rows, weighted,
)
from build_wr_board import load_props

FEATURES_2024 = WR_DIR / "wr_stats_2024.csv"
OUTCOMES_2025 = WR_DIR / "wr_stats_act_2025.csv"
STATS_2025 = WR_DIR / "wr_stats_act_pred_2025.csv"
OUT_CSV = WR_DIR / "wr_sleepers_2026.csv"

SIGNAL_WEIGHTS = {
    "youth": 0.25,
    "efficiency": 0.25,
    "role_gap": 0.20,
    "regression": 0.15,
    "route_volume": 0.15,
}

MIN_GAMES = 4
MIN_TGT_PER_GAME = 1.5
CONSENSUS_TOP = 24        # priced inside this = not a sleeper
SLEEPER_LIST_SIZE = 15


def extract_signals(row, cols):
    """Raw signal values from a season stat row; missing stays None."""
    age = number(row.get(cols["age"]))
    yprr = number(row.get(cols["yprr"]))
    tgt_share = clean_share(number(row.get(cols["tgt_share"])), MAX_TARGET_SHARE)
    air_share = clean_share(number(row.get(cols["air_share"])), MAX_AIR_SHARE)
    fpts_diff = number(row.get(cols["fpts_diff"]))
    routes = number(row.get(cols["routes"]))
    games = number(row.get(cols["games"]))
    return {
        "youth": -age if age is not None else None,
        "efficiency": yprr,
        "role_gap": (air_share - tgt_share)
                    if air_share is not None and tgt_share is not None else None,
        "regression": -fpts_diff if fpts_diff is not None else None,
        "route_volume": routes / games if routes is not None and games else None,
    }


def score_pool(pool, weights):
    """Attach sig_pct_* percentiles and an upside score to each row."""
    for signal in SIGNAL_WEIGHTS:
        vals = [row["signals"][signal] for row in pool]
        for row in pool:
            row[f"sig_pct_{signal}"] = percentile(vals, row["signals"][signal])
    for row in pool:
        row["upside_score"] = weighted([
            (row.get(f"sig_pct_{signal}"), weight)
            for signal, weight in weights.items()
        ])
    pool.sort(key=lambda r: (-(r["upside_score"] or -1), norm_name(r["Player"])))


def fpts_ranks(rows, fpts_field):
    """Map normalized name -> 1-based rank by total fantasy points."""
    ordered = sorted(rows, key=lambda r: (-(number(r.get(fpts_field)) or 0),
                                          norm_name(r["Player"])))
    return {norm_name(r["Player"]): rank for rank, r in enumerate(ordered, 1)}


COLS_2024 = {
    "age": "Age", "yprr": "YPRR", "tgt_share": "Target_Share",
    "air_share": "air_pct", "fpts_diff": "fpts_diff",
    "routes": "Routes Run", "games": "G",
}
COLS_2025 = {
    "age": "Age_2025", "yprr": "YPRR_2025", "tgt_share": "Target_Share_2025",
    "air_share": "air_pct_2025", "fpts_diff": "fpts_diff_2025",
    "routes": "Routes Run_2025", "games": "G_2025",
}


def backtest():
    """Validate the sleeper profile on 2024 -> 2025 and report the
    Michael Wilson case. Returns printed-lines for reuse in docs."""
    rows, dupes = dedupe_players(read_rows(FEATURES_2024))
    outcomes = read_rows(OUTCOMES_2025)
    left_only, right_only = match_report(rows, outcomes)
    print(f"backtest join: {len(dupes)} multi-team players collapsed, "
          f"{len(left_only)} unmatched 2024, {len(right_only)} unmatched 2025")
    out_by_key = {norm_name(r["Player"]): r for r in outcomes}

    rank24 = fpts_ranks(rows, "FPTS")
    rank25 = fpts_ranks(outcomes, "FPTS")

    # Preseason 2025 market rank from the normalized line (where posted).
    lined = [(norm_name(r["Player"]), number(r.get("normalized_line")))
             for r in rows if number(r.get("normalized_line")) is not None]
    lined.sort(key=lambda item: (-item[1], item[0]))
    market_rank = {key: rank for rank, (key, _) in enumerate(lined, 1)}

    pool = []
    for row in rows:
        key = norm_name(row["Player"])
        out = out_by_key.get(key)
        games = number(row.get("G"))
        tgt_pg = number(row.get("TGT/G"))
        if out is None or (games or 0) < MIN_GAMES or (tgt_pg or 0) < MIN_TGT_PER_GAME:
            continue
        # Consensus already believes: not sleeper material.
        if rank24[key] <= CONSENSUS_TOP:
            continue
        if market_rank.get(key, 999) <= CONSENSUS_TOP:
            continue
        row["signals"] = extract_signals(row, COLS_2024)
        gain = rank24[key] - rank25[key]
        arrived = rank24[key] > 36 and rank25[key] <= 36
        pg24, pg25 = number(row.get("FPTS/G")), number(out.get("FPTS/G"))
        g25 = number(out.get("G"))
        grew = (pg24 is not None and pg25 is not None and (g25 or 0) >= 8
                and pg25 - pg24 >= 3.0)
        row["label_rank_gain"] = gain >= 24
        row["label_top36"] = arrived
        row["label_ppg_growth"] = grew
        row["label_breakout"] = arrived or (row["label_rank_gain"] and grew)
        row["rank24"], row["rank25"] = rank24[key], rank25[key]
        pool.append(row)

    print(f"sleeper-eligible pool (2024): {len(pool)} WRs outside the "
          f"consensus top {CONSENSUS_TOP}")
    for label in ("rank_gain", "top36", "ppg_growth", "breakout"):
        base = sum(r[f"label_{label}"] for r in pool)
        print(f"  base rate {label}: {base}/{len(pool)} "
              f"({100 * base / len(pool):.0f}%)")

    for name, weights in (("profile weights", SIGNAL_WEIGHTS),
                          ("equal weights", {s: 0.2 for s in SIGNAL_WEIGHTS})):
        score_pool(pool, weights)
        top = pool[:SLEEPER_LIST_SIZE]
        print(f"\ntop {SLEEPER_LIST_SIZE} by {name}:")
        for label in ("rank_gain", "top36", "ppg_growth", "breakout"):
            hits = sum(r[f"label_{label}"] for r in top)
            base = sum(r[f"label_{label}"] for r in pool) / len(pool)
            print(f"  {label}: {hits}/{len(top)} hit "
                  f"(pool base rate {100 * base:.0f}%)")
        for i, row in enumerate(top, 1):
            marks = "".join(
                flag for flag, ok in (
                    ("R", row["label_rank_gain"]), ("T", row["label_top36"]),
                    ("G", row["label_ppg_growth"]))
                if ok)
            print(f"  {i:2d}. {row['Player']:<24} upside {row['upside_score']:5.1f} "
                  f"WR{row['rank24']} -> WR{row['rank25']} {marks}")

    # Michael Wilson case study under the profile weights (rescore so the
    # reported ordering matches the profile, not the equal-weight variant).
    score_pool(pool, SIGNAL_WEIGHTS)
    for i, row in enumerate(pool, 1):
        if norm_name(row["Player"]) == "michaelwilson":
            print(f"\nMichael Wilson check: sleeper rank {i}/{len(pool)}, "
                  f"upside {row['upside_score']:.1f}")
            for signal in SIGNAL_WEIGHTS:
                print(f"  {signal}: value {row['signals'][signal]}, "
                      f"pct {row[f'sig_pct_{signal}']:.0f}")
            print(f"  outcome: WR{row['rank24']} in 2024 -> WR{row['rank25']} "
                  f"in 2025, breakout={row['label_breakout']}")
            break
    return pool


def build_2026_list():
    """Score the 2025 season for 2026 sleepers and write the CSV."""
    rows, dupes = dedupe_players(read_rows(STATS_2025), team_field="Team_2025")
    if dupes:
        print(f"2025 file: collapsed multi-team rows for {sorted(dupes)}")
    prop_lines = load_props()

    rank25 = fpts_ranks(rows, "FPTS_2025")
    rank24 = fpts_ranks(rows, "FPTS_2024")
    lined = sorted(
        ((key, line) for (key, market), line in prop_lines.items()
         if market == "receiving_yards"),
        key=lambda item: (-item[1], item[0]))
    market_rank = {key: rank for rank, (key, _) in enumerate(lined, 1)}

    pool, excluded_established = [], []
    for row in rows:
        key = norm_name(row["Player"])
        games = number(row.get("G_2025"))
        tgt_pg = number(row.get("TGT/G_2025"))
        if (games or 0) < MIN_GAMES or (tgt_pg or 0) < MIN_TGT_PER_GAME:
            continue
        row["prop_receiving_yards"] = (
            number(row.get("Bet_Line_Rec_Yds"))
            or prop_lines.get((key, "receiving_yards")))
        row["prop_receptions"] = (
            number(row.get("Bet_Line_Rec")) or prop_lines.get((key, "receptions")))
        row["prop_receiving_tds"] = (
            number(row.get("Bet_Line_Rec_TD"))
            or prop_lines.get((key, "receiving_tds")))
        if rank25[key] <= CONSENSUS_TOP or market_rank.get(key, 999) <= CONSENSUS_TOP:
            excluded_established.append(row["Player"])
            continue
        # No posted line is unknown, not cheap: an unpriced player who
        # finished top-24 in either of the last two seasons is a known
        # quantity (usually an injury return), not a sleeper.
        if (row["prop_receiving_yards"] is None
                and min(rank25[key], rank24[key]) <= CONSENSUS_TOP):
            excluded_established.append(row["Player"] + " (unpriced, recent top-24)")
            continue
        row["signals"] = extract_signals(row, COLS_2025)
        pool.append(row)

    print(f"\n2026 sleeper pool: {len(pool)} WRs outside the consensus top "
          f"{CONSENSUS_TOP} (excluded {len(excluded_established)} established)")
    unpriced = [name for name in excluded_established if "unpriced" in name]
    if unpriced:
        print("  unpriced recent top-24 (unknown market, not sleepers): "
              + ", ".join(unpriced))
    score_pool(pool, SIGNAL_WEIGHTS)

    out_rows = []
    for row in pool[:SLEEPER_LIST_SIZE]:
        games = number(row.get("G_2025")) or 0
        games_factor = min(games / 12, 1)
        has_line = row["prop_receiving_yards"] is not None
        age = number(row.get("Age_2025"))
        present = sum(1 for s in SIGNAL_WEIGHTS if row["signals"][s] is not None)
        completeness = present / len(SIGNAL_WEIGHTS)

        risk_points = (50 * (1 - games_factor)
                       + (25 if not has_line else 0)
                       + (25 if age is not None and age >= 27 else 0))
        risk = ("LOW" if risk_points < 25 else
                "MEDIUM" if risk_points < 50 else "HIGH")
        confidence = round(100 * (0.5 * games_factor + 0.3 * completeness
                                  + 0.2 * has_line))

        reasons = []
        if row["sig_pct_youth"] is not None and age is not None and age <= 25:
            reasons.append(f"age {age:.0f}")
        if (row["sig_pct_efficiency"] or 0) >= 65:
            reasons.append(f"{row['signals']['efficiency']:.2f} YPRR "
                           f"(pct {row['sig_pct_efficiency']:.0f})")
        if (row["sig_pct_role_gap"] or 0) >= 65:
            reasons.append(f"air share {row['signals']['role_gap']:+.1f} pts "
                           f"above target share")
        if (row["sig_pct_regression"] or 0) >= 65:
            reasons.append(f"{-row['signals']['regression']:.1f} PPG under "
                           f"expected (positive regression)")
        if (row["sig_pct_route_volume"] or 0) >= 65:
            reasons.append(f"{row['signals']['route_volume']:.0f} routes/game")
        if not has_line:
            reasons.append("no 2026 market line yet (market unknown)")

        out_rows.append({
            "rank": len(out_rows) + 1,
            "Player": row["Player"],
            "Team": row.get("Team_2025", ""),
            "Age": age,
            "G_2025": games,
            "upside_score": round(row["upside_score"], 1),
            "risk": risk,
            "confidence": confidence,
            "prop_receiving_yards": row["prop_receiving_yards"],
            "prop_receptions": row["prop_receptions"],
            "prop_receiving_tds": row["prop_receiving_tds"],
            "FPTS_G_2025": number(row.get("FPTS/G_2025")),
            "YPRR_2025": row["signals"]["efficiency"],
            "air_minus_target_share": (
                round(row["signals"]["role_gap"], 1)
                if row["signals"]["role_gap"] is not None else None),
            "routes_per_game": (
                round(row["signals"]["route_volume"], 1)
                if row["signals"]["route_volume"] is not None else None),
            "reasons": "; ".join(reasons) if reasons else "balanced profile",
        })

    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"wrote {OUT_CSV}")
    for row in out_rows:
        line = (f"{row['prop_receiving_yards']:.1f} yds line"
                if row["prop_receiving_yards"] is not None else "no line")
        print(f"  {row['rank']:2d}. {row['Player']:<24} upside "
              f"{row['upside_score']:5.1f} risk {row['risk']:<6} "
              f"conf {row['confidence']:3d} {line} | {row['reasons']}")
    return out_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-backtest", action="store_true",
                        help="only rebuild the 2026 sleeper CSV")
    args = parser.parse_args()
    if not args.skip_backtest:
        print("=== Sleeper profile backtest (2024 -> 2025) ===")
        backtest()
    print("\n=== 2026 sleeper list ===")
    build_2026_list()


if __name__ == "__main__":
    main()
