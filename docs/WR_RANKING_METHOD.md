# 2026 WR ranking method

The WR pipeline is three scripts plus a shared core, all standard library:

| file | job |
| --- | --- |
| `scripts/wr_model.py` | shared loading, cleaning, scoring, and evaluation |
| `scripts/backtest_wr_weights.py` | 2024 → 2025 backtest and weight optimization |
| `scripts/build_wr_board.py` | the 2026 top-40 board (`wr/wr_top40_2026.csv` + dashboard) |
| `scripts/find_wr_sleepers.py` | sleeper backtest + `wr/wr_sleepers_2026.csv` |

Run everything from the repo root:

```
python3 scripts/backtest_wr_weights.py
python3 scripts/build_wr_board.py
python3 scripts/find_wr_sleepers.py
python3 -m unittest discover -s tests -v
```

## Data hygiene rules

These rules are enforced in `wr_model.py` and covered by `tests/test_wr_model.py`:

- **No leakage.** `wr/wr_stats_2024.csv` carries `PPR_Points_2025` (and a
  preseason rank column) for evaluation only. They are listed in
  `LEAKAGE_COLUMNS` and never read as features; a test perturbs the column
  and asserts scores do not move.
- **Names are joined only through `norm_name`** (lowercase ASCII, suffixes
  and punctuation stripped). Every script prints unmatched names on both
  sides of a join; the 2024/2025 files currently join 223-for-223.
- **Duplicates are collapsed, not summed.** Traded players appear once per
  team plus a `2TM`/`3TM` aggregate row; the aggregate row is kept and the
  duplicates are reported (8 players in the 2024 file).
- **Missing means missing.** Blank cells become `None`, never zero. Weighted
  scores renormalize over the metrics a player actually has. Impossible
  values (a 100% season target share on a `3TM` row) also become missing.
- **A missing market line is unknown, not bad.** Players without lines get a
  neutral market score of 50 and lower confidence, and available lines are
  reweighted (a player with only a TD line is scored on the TD line alone).

## Backtest: 2024 features → actual 2025 PPR

`backtest_wr_weights.py` scores every WR using only information available
after the 2024 season — 2024 usage/efficiency stats plus the normalized 2025
preseason receiving-yard line — and grades the ordering against actual 2025
results from `wr/wr_stats_act_2025.csv`. Pool: 112 WRs with 3+ games in 2024
and either 2.5+ targets/game or a preseason line; the PPR-per-game grade uses
the 104 of them with 4+ games in 2025. The board's trend category needs 2023
data that does not exist, so the backtest renormalizes it away — exactly what
the scorer does with any missing category.

| weights | Spearman (total / per-game) | rank MAE | top-12 | top-24 | top-36 |
| --- | --- | --- | --- | --- | --- |
| old defaults: market .35 / prod .25 / opp .25 / trend .15 | .522 / .676 | 24.3 / 18.8 | 6 / 8 | 14 / 16 | 24 / 24 |
| grid optimum: market .10 / prod .50 / opp .10 / youth .30 | .661 / .770 | 20.8 / 16.5 | 6 | 14 | 23 |
| **new defaults: market .15 / prod .40 / opp .25 / youth .20** | **.646 / .760** | **21.0 / 16.4** | 6 / 8 | 14 / 15 | 23 / 25 |

Top-K hit counts are the number of actual top-K finishers captured by the
predicted top K; they barely move because the very top is easy — the gains
show up in whole-list ordering (Spearman, MAE).

Single-category baselines: production alone .584/.685, opportunity alone
.565/.655, youth alone .326/.331, market alone .266/.424. The 2025 preseason
line was a mediocre predictor; last season's production and role were far
better, and youth is weak alone but a strong complement.

**Why not the grid optimum?** One season of validation. Youth at .30 likely
overfits a 2025 that was unusually kind to young receivers (a player
bootstrap cannot detect a season-specific age effect), so youth is shaded to
.20. Market is kept at .15 — above its backtest optimum of .05–.10 — because
the 2026 market component is richer than the backtest proxy (three markets
across six books instead of one normalized line) and it carries offseason
information (trades, depth charts, injuries) that trailing stats cannot see.
The chosen weights sit on the optimization plateau (bootstrap mean Spearman
.641, 5th percentile .547, vs .525/.402 for the old defaults).

## Default score

- 40% 2025 production — `FPTS/G` .40, `XFP` .30, `YPRR` .30
- 25% underlying opportunity — `TGT/G` .28, target share .25, `WOPR` .20,
  air-yard share .18, red-zone target share .09
- 20% youth — percentile of (negative) age
- 15% 2026 market — receiving yards .45, receptions .35, receiving TDs .20;
  touchdowns get the smallest share because they are the least stable, and
  receptions matter because this is PPR
- 0% trend — still computed and displayed (`trend_score`, `Direction`
  column) but unweighted by default: with no 2023 data there is nothing to
  validate it against

All components are percentiles among relevant receivers, small 2025 samples
are shrunk toward the 50th percentile (season-share denominators punish
injured players), and every weight is non-negative and sums to one
(`check_weights` refuses anything else).

Weights are configurable without editing code:

```
python3 scripts/build_wr_board.py \
  --weights market=0.35,production=0.25,opportunity=0.25,youth=0,trend=0.15   # old board
python3 scripts/build_wr_board.py --weights trend=0.15,youth=0.05             # breakout tilt
```

## Sleepers (`find_wr_sleepers.py`)

A sleeper is a receiver priced outside the consensus top 24 — by last
season's finish and by the 2026 receiving-yard market — whose underlying
profile says the price is too low. Being low-ranked on the main board is not
enough. Unpriced players who finished top-24 in 2024 or 2025 (e.g. injury
returns like Malik Nabers) are excluded: no line means the market is
unknown, not that the player is cheap.

Upside profile (fixed a priori, then validated — not fit to any player):
youth .25, YPRR efficiency .25, role gap (air-yard share minus target share)
.20, XFP regression (scored under expected points) .15, routes/game .15.

Backtested on 2024 → 2025 (109-WR sleeper pool), the top 15 by upside score
hit: top-36 arrival 5/15 vs a 12% base rate (~2.8×), +3 PPR/G growth 3/15 vs
8%, combined breakout 5/15 vs 15%. An equal-weight variant produces a
similar list, so the ordering is not weight-sensitive. Honest misses ride
along (Aiyuk, Tank Dell — injury wipeouts the profile cannot see).

**Michael Wilson check:** his 2024 profile ranked him 18th of 109 (top ~17%)
— 96th percentile role gap, 84th percentile route volume, age 24 — held back
by a 37th-percentile YPRR. The profile flagged the *shape* of his 2025
breakout (WR61 → WR10) without putting him in the top 15; equal weights rank
him 12th. Reported as-is; the weights were not tuned to move him.

Output (`wr/wr_sleepers_2026.csv`): upside score, risk (games played, age
27+, unpriced market), confidence (sample, signal completeness, line
availability), the three 2026 market lines, key metrics, and short reasons.

## How to use the board

- Target players in the upper-right of the scatter plot: strong outlook and
  improving role.
- Treat high score plus weak trend as an established player whose price
  needs scrutiny, not an automatic fade.
- Prefer opportunity over touchdown overperformance: `XFP` describes
  repeatable usage better than last year's touchdown total.
- Use the confidence column to find rankings that need manual review, and
  the build's console report for receiving-yard lines with no 2025 stats row
  — that list is the rookie class (plus TE/RB lines) the model cannot rank.
- Refresh sportsbook lines and rebuild periodically; a meaningful line move
  is new information.

This is a screening model. The final manual pass should account for
injuries, quarterback changes, trades, rookies absent from the 2025 dataset,
and league scoring settings.
