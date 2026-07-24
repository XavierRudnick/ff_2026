#!/usr/bin/env python3
"""Build a transparent 2026 top-40 fantasy WR board and HTML dashboard.

Uses only the Python standard library. Scores are percentile composites, so
the board is easy to audit and the weights are easy to change (edit
CATEGORY_WEIGHTS or pass ``--weights``).

Default weights are the ones supported by the 2024 -> 2025 backtest
(``backtest_wr_weights.py``): production and opportunity carry the most
weight, youth is a meaningful complement, the market is a moderate anchor,
and trend is displayed but unweighted because it cannot be backtested
without 2023 data. See docs/WR_RANKING_METHOD.md.
"""

import argparse
import csv
import html
import statistics

from wr_model import (
    MAX_AIR_SHARE, MAX_TARGET_SHARE, PROPS_DIR, WR_DIR, check_weights,
    clean_share, dedupe_players, norm_name, number, read_rows, score_players,
)

STATS = WR_DIR / "wr_stats_act_pred_2025.csv"
OUT_CSV = WR_DIR / "wr_top40_2026.csv"
OUT_HTML = WR_DIR / "wr_dashboard_2026.html"

# Backtest-supported defaults (see docs/WR_RANKING_METHOD.md for the full
# table). Trend defaults to zero weight: it is shown on the board but there
# is no 2023 data to validate it against. Override with e.g.
#   --weights market=0.35,production=0.25,opportunity=0.25,youth=0,trend=0.15
CATEGORY_WEIGHTS = {
    "market": 0.15,
    "production": 0.40,
    "opportunity": 0.25,
    "youth": 0.20,
    "trend": 0.00,
}
METRICS = {
    # PPR scoring makes catches valuable; touchdowns remain the least stable,
    # so yards and receptions carry more weight than TDs. Players missing
    # some markets are reweighted over the lines they do have.
    "market": [
        ("prop_receiving_yards", 0.45),
        ("prop_receptions", 0.35),
        ("prop_receiving_tds", 0.20),
    ],
    "production": [("FPTS/G_2025", 0.40), ("XFP_2025", 0.30), ("YPRR_2025", 0.30)],
    "opportunity": [
        ("TGT/G_2025", 0.28),
        ("Target_Share_2025", 0.25),
        ("air_pct_2025", 0.18),
        ("WOPR_2025", 0.20),
        ("RZ_TGT_PCT_2025", 0.09),
    ],
    "youth": [("neg_age", 1.0)],
    "trend": [
        ("TGT/G_diff_2025_minus_2024", 0.30),
        ("Target_Share_diff_2025_minus_2024", 0.25),
        ("air_pct_diff_2025_minus_2024", 0.15),
        ("WOPR_diff_2025_minus_2024", 0.15),
        ("YPRR_diff_2025_minus_2024", 0.15),
    ],
}

RECEIVING_MARKETS = ("receiving_yards", "receptions", "receiving_tds")
BOOK_LINE_FIELDS = (
    "betmgm_line", "betrivers_line", "caesars_line",
    "draftkings_line", "fanduel_line", "bet365_line",
)


def latest_props_file():
    matches = sorted(PROPS_DIR.glob("nfl_2026_season_props_unified_*.csv"))
    if not matches:
        raise FileNotFoundError(f"no unified props file in {PROPS_DIR}")
    return matches[-1]


def parse_weights(text):
    weights = dict(CATEGORY_WEIGHTS)
    for part in text.split(","):
        name, _, value = part.partition("=")
        name = name.strip()
        if name not in weights:
            raise SystemExit(f"unknown category '{name}' "
                             f"(choose from {', '.join(weights)})")
        parsed = number(value)
        if parsed is None:
            raise SystemExit(f"bad weight for '{name}': {value!r}")
        weights[name] = parsed
    return weights


def load_props():
    """Median line per (player, market) across the books that post one."""
    lines = {}
    for row in read_rows(latest_props_file()):
        market = row.get("market")
        if market not in RECEIVING_MARKETS:
            continue
        book_lines = [number(row.get(field)) for field in BOOK_LINE_FIELDS]
        book_lines = [v for v in book_lines if v is not None]
        if book_lines:
            key = (norm_name(row.get("player", "")), market)
            lines[key] = statistics.median(book_lines)
    return lines


def fmt(value, digits=1):
    return "" if value is None else f"{value:.{digits}f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", default=None,
                        help="comma list of category=weight overrides; "
                             "weights must be >= 0 and sum to 1")
    parser.add_argument("--top", type=int, default=40, help="board size")
    args = parser.parse_args()
    weights = parse_weights(args.weights) if args.weights else CATEGORY_WEIGHTS
    check_weights(weights, METRICS)

    raw = read_rows(STATS)
    rows, dupes = dedupe_players(raw, team_field="Team_2025")
    if dupes:
        print(f"duplicate players collapsed ({len(dupes)}): "
              + ", ".join(sorted(dupes)))
    for row in rows:
        for key in {name for items in METRICS.values() for name, _ in items}:
            row[key] = number(row.get(key))
        for key in ("G_2025", "Age_2025", "AIR_2025"):
            row[key] = number(row.get(key))
        row["Target_Share_2025"] = clean_share(row["Target_Share_2025"],
                                               MAX_TARGET_SHARE)
        row["air_pct_2025"] = clean_share(row["air_pct_2025"], MAX_AIR_SHARE)
        row["neg_age"] = -row["Age_2025"] if row["Age_2025"] is not None else None
        row["air_yards_per_game"] = (
            row["AIR_2025"] / row["G_2025"]
            if row["AIR_2025"] is not None and row["G_2025"]
            else None
        )
        row["_key"] = norm_name(row["Player"])

    prop_lines = load_props()
    stat_keys = {row["_key"] for row in rows}
    missing_from_stats = sorted({
        key for (key, market), line in prop_lines.items()
        if key not in stat_keys and market == "receiving_yards" and line >= 500
    })
    if missing_from_stats:
        print(f"receiving-yard lines >= 500 with no 2025 WR stats row "
              f"(rookies or other positions, review manually): "
              + ", ".join(missing_from_stats))

    for row in rows:
        for market in RECEIVING_MARKETS:
            row[f"prop_{market}"] = prop_lines.get((row["_key"], market))
        # Lines merged directly into the WR file win because they may be
        # newer than the standalone props snapshot.
        direct_lines = {
            "prop_receiving_yards": number(row.get("Bet_Line_Rec_Yds")),
            "prop_receptions": number(row.get("Bet_Line_Rec")),
            "prop_receiving_tds": number(row.get("Bet_Line_Rec_TD")),
        }
        for field, direct_value in direct_lines.items():
            if direct_value is not None:
                row[field] = direct_value

    # Rank plausible fantasy candidates. A player needs either meaningful 2025
    # volume or a 2026 market line.
    candidates = [
        r for r in rows
        if (r["G_2025"] or 0) >= 3
        and ((r["TGT/G_2025"] or 0) >= 2.5 or r["prop_receiving_yards"] is not None)
    ]
    score_players(
        candidates, METRICS, weights, games_field="G_2025",
        shrink_categories=("production", "opportunity", "trend"),
        neutral_categories=("market",),
    )
    for row in candidates:
        games_factor = min((row["G_2025"] or 0) / 12, 1)
        market_factor = 1 if row["prop_receiving_yards"] is not None else 0
        row["confidence"] = 100 * (0.65 * games_factor + 0.35 * market_factor)

    candidates.sort(key=lambda r: (-(r["model_score"] or -1), r["_key"]))
    top = candidates[:args.top]
    for rank, row in enumerate(top, 1):
        row["rank"] = rank
        trend = row["trend_score"]
        row["trend_label"] = (
            "Unknown" if trend is None else
            "Strong riser" if trend >= 75 else
            "Rising" if trend >= 60 else
            "Stable" if trend >= 40 else
            "Falling"
        )

    fields = [
        "rank", "Player", "Age_2025", "Team_2025", "G_2025", "model_score",
        "market_score", "production_score", "opportunity_score", "youth_score",
        "trend_score", "trend_label", "confidence", "prop_receiving_yards",
        "prop_receptions", "prop_receiving_tds", "FPTS/G_2025", "XFP_2025",
        "TGT/G_2025", "Target_Share_2025", "AIR_2025", "air_yards_per_game",
        "air_pct_2025", "WOPR_2025", "YPRR_2025",
        "TGT/G_diff_2025_minus_2024",
        "Target_Share_diff_2025_minus_2024",
        "air_pct_diff_2025_minus_2024", "WOPR_diff_2025_minus_2024",
        "YPRR_diff_2025_minus_2024",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in top:
            writer.writerow({
                k: (round(v, 2) if isinstance(v, float) else v)
                for k, v in row.items()
            })

    build_html(top, weights)
    print(f"Wrote {OUT_CSV} and {OUT_HTML}")


def build_html(top, weights):
    dots = []
    for row in top:
        trend = row["trend_score"] if row["trend_score"] is not None else 50
        x = 55 + 8.1 * trend
        y = 535 - 4.75 * row["model_score"]
        color = "#22c55e" if trend >= 60 else "#f59e0b" if trend >= 40 else "#ef4444"
        dots.append(
            f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{color}">'
            f'<title>#{row["rank"]} {html.escape(row["Player"].title())}: '
            f'score {row["model_score"]:.1f}, trend {trend:.1f}</title>'
            f'</circle><text x="{x+8:.1f}" y="{y+4:.1f}">{row["rank"]}</text></g>'
        )
    table_rows = []
    for r in top:
        table_rows.append(
            "<tr>"
            f'<td>{r["rank"]}</td><td class="player">{html.escape(r["Player"].title())}</td>'
            f'<td>{html.escape(r.get("Team_2025", ""))}</td>'
            f'<td>{fmt(r["Age_2025"], 0)}</td>'
            f'<td>{fmt(r["G_2025"], 0)}</td>'
            f'<td>{fmt(r["model_score"])}</td><td>{fmt(r["market_score"])}</td>'
            f'<td>{fmt(r["production_score"])}</td><td>{fmt(r["opportunity_score"])}</td>'
            f'<td>{fmt(r["youth_score"])}</td>'
            f'<td>{fmt(r["trend_score"])}</td><td>{html.escape(r["trend_label"])}</td>'
            f'<td>{fmt(r["confidence"], 0)}%</td><td>{fmt(r["prop_receiving_yards"], 1)}</td>'
            f'<td>{fmt(r["prop_receptions"], 1)}</td><td>{fmt(r["prop_receiving_tds"], 1)}</td>'
            f'<td>{fmt(r["FPTS/G_2025"])}</td>'
            f'<td>{fmt(r["TGT/G_2025"])}</td><td>{fmt(r["Target_Share_2025"])}</td>'
            f'<td>{fmt(r["air_yards_per_game"])}</td><td>{fmt(r["air_pct_2025"])}</td>'
            f'<td>{fmt(r["WOPR_2025"], 2)}</td><td>{fmt(r["YPRR_2025"], 2)}</td>'
            "</tr>"
        )
    pct = {k: round(100 * v) for k, v in weights.items()}
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>2026 Fantasy WR Board</title>
<style>
:root{{--bg:#07111f;--card:#0e1b2c;--ink:#e7eef8;--muted:#91a4bc;--line:#21344c;--blue:#60a5fa}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:14px system-ui,sans-serif}}
main{{max-width:1440px;margin:auto;padding:28px}} h1{{font-size:32px;margin:0 0 6px}} p{{color:var(--muted);max-width:900px}}
.cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:22px 0}}
.card,.chart,.table-wrap{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}}
.card b{{display:block;font-size:22px;color:var(--blue)}} .chart{{overflow:auto}} svg{{min-width:900px;width:100%;height:auto}}
svg text{{fill:var(--muted);font-size:11px}} .axis{{stroke:#38506d;stroke-width:1}}
.table-wrap{{margin-top:14px;overflow:auto;padding:0}} table{{border-collapse:collapse;width:100%;min-width:1250px}}
th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}
th{{position:sticky;top:0;background:#132238;color:#bed0e5;cursor:pointer}} th:nth-child(2),td:nth-child(2){{text-align:left}}
tr:hover{{background:#132238}} .player{{font-weight:650;color:white}}
@media(max-width:800px){{.cards{{grid-template-columns:1fr 1fr}} main{{padding:14px}}}}
</style></head><body><main>
<h1>2026 Fantasy WR Top 40</h1>
<p>A decision board, not a black box. Overall score blends 2025 production
({pct['production']}%), underlying opportunity ({pct['opportunity']}%), youth
({pct['youth']}%), 2026 sportsbook expectations ({pct['market']}%), and
year-over-year trend ({pct['trend']}%). Weights are backtested against actual
2025 results; see docs/WR_RANKING_METHOD.md. All components are percentile
scores among relevant receivers. Click any column to sort.</p>
<div class="cards">
<div class="card"><b>{pct['production']}%</b>current production</div>
<div class="card"><b>{pct['opportunity']}%</b>underlying opportunity</div>
<div class="card"><b>{pct['youth']}%</b>youth</div>
<div class="card"><b>{pct['market']}%</b>2026 market baseline</div>
<div class="card"><b>{pct['trend']}%</b>direction of travel</div>
</div>
<div class="chart"><h2>Trend vs. total outlook</h2>
<p>Green = rising, amber = stable, red = falling. Labels are board ranks; hover for names.</p>
<svg viewBox="0 0 900 570" role="img" aria-label="Trend versus model score scatter plot">
<line class="axis" x1="55" y1="535" x2="865" y2="535"/><line class="axis" x1="55" y1="60" x2="55" y2="535"/>
<text x="410" y="562">YEAR-OVER-YEAR TREND →</text><text transform="translate(15 350) rotate(-90)">TOTAL OUTLOOK →</text>
{''.join(dots)}</svg></div>
<div class="table-wrap"><table id="board"><thead><tr>
<th>Rank</th><th>Player</th><th>Team</th><th>Age</th><th>2025 GP</th><th>Score</th><th>Market</th><th>Production</th>
<th>Opportunity</th><th>Youth</th><th>Trend</th><th>Direction</th><th>Confidence</th><th>2026 Yds Line</th>
<th>2026 Rec Line</th><th>2026 TD Line</th><th>2025 PPR/G</th><th>Tgt/G</th><th>Tgt Share</th>
<th>Air Yds/G</th><th>Air Share</th><th>WOPR</th><th>YPRR</th>
</tr></thead><tbody>{''.join(table_rows)}</tbody></table></div>
<p>Confidence reflects sample size and whether a 2026 receiving-yards line is available.
It is not injury probability. Update the source CSVs and rerun <code>python3 scripts/build_wr_board.py</code>.</p>
</main><script>
document.querySelectorAll('th').forEach((th,i)=>th.onclick=()=>{{
 const body=document.querySelector('tbody'), rows=[...body.rows], asc=th.dataset.asc!=='1';
 rows.sort((a,b)=>{{let x=a.cells[i].innerText,y=b.cells[i].innerText,nx=parseFloat(x),ny=parseFloat(y);
 return (isNaN(nx)||isNaN(ny)?x.localeCompare(y):nx-ny)*(asc?1:-1)}});
 rows.forEach(r=>body.appendChild(r)); th.dataset.asc=asc?'1':'0';
}});</script></body></html>"""
    OUT_HTML.write_text(document, encoding="utf-8")


if __name__ == "__main__":
    main()
