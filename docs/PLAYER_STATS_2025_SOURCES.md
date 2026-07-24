# 2025 player-stat sources and definitions

`scripts/scrape_2025_player_stats.py` creates `rbs/rb_stats_2025.csv` and
`wr/wr_stats_act_2025.csv`. It keeps the first occurrence of every player in
the existing 2024 files, preserving their order, and then appends active 2025
players who were absent from the prior-year universe in descending PPR order.
This includes rookies and other newcomers while removing old PFR
`2TM`/team-split duplicate rows.

The merged `*_act_pred_2025.csv` files also retain upcoming 2026 RB/WR
rookies who have a market in the unified props file but no 2025 NFL season.
Those rows use `merge_status=prop_only`; their 2025 and 2024 fields remain
blank rather than fabricating statistics.

All results cover the 2025 NFL regular season only. `normalized_line` is blank
by design.

## Sources

- Basic rushing, receiving, fantasy, target-share, air-share, and WOPR fields:
  nflverse `stats_player_reg_2025`, which is built from NFL play-by-play.
- Age and player identifiers: nflverse 2025 rosters.
- YBC, YAC, and drops/catchable targets: nflverse's weekly Pro Football
  Reference advanced-stat release. `CATCHABLE = receptions + drops`.
- Red-zone counts, team RB opportunity denominators, and team air yards:
  nflverse 2025 play-by-play. Red zone means `yardline_100 <= 20`; nullified
  plays and two-point tries are excluded.
- Routes run: the 2025 SumerSports WR and TE season tables. For the rare player
  omitted because of a later position reclassification, the script falls back
  to that player's public PFF season page. `YPRR` is receiving yards divided by
  routes run.
- XFP and XTD: ffopportunity's public 2025 expected-opportunity model. Both are
  reported per game. `fpts_diff` and `td_diff`/`tds_diff` are actual per-game
  values minus expected per-game values.

## Calculated fields

- RB `Att_Share` is player carries divided by team RB/FB carries.
- RB `TGT_share` is player targets divided by team RB/FB targets.
- WR `Target_Share`, `air_pct`, and `WOPR` use nflverse's standard team passing
  denominators.
- Red-zone opportunity percentages use the player's position group: RB/FB for
  RBs, WR for WRs, and TE for TEs.
- `FPTS` is full-PPR scoring from nflverse. `FPTS/G`, `TD/G`, and `TGT/G` use
  games played.
- `VOR` retains the baselines implied by the prior files: 11.5 PPR points/game
  for RB, 13.0 for WR, and 8.5 for TE.
- `ALY` uses the public line-yards weighting (losses 120%, yards 0-4 at 100%,
  yards 5-10 at 50%, and no credit beyond 10), normalized so league-average ALY
  equals league-average RB yards per carry. Proprietary opponent adjustments
  are not guessed.

For a reproducible rerun:

```bash
uv run --with pandas --with requests python scripts/scrape_2025_player_stats.py
python scripts/merge_act_pred_stats.py
```
