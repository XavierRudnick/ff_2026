# 2025 player-stat sources and definitions

`scrape_2025_player_stats.py` creates `rb_stats_2025.csv` and
`wr_stats_2025.csv`. It keeps the first occurrence of every player in the
existing `rb_stats.csv` and `wr_stats.csv`, preserving their order. This removes
the old PFR `2TM`/team-split duplicate rows while retaining the same player set.

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
python scrape_2025_player_stats.py
```
