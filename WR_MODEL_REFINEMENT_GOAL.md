# /goal: Optimize the WR board and find sleepers
Use `wr/wr_stats_2024.csv` to predict actual 2025 WR success.
Use `wr/wr_stats_act_2025.csv` as the outcome source.
Never use `PPR_Points_2025` or other future data as features.
Normalize player names and report unmatched or duplicate players.
Backtest the current weights before changing them.
Optimize non-negative weights that sum to one.
Use only information available after the 2024 season.
Consider usage, efficiency, age, routes, shares, WOPR, XFP, and YPRR.
Avoid double-counting strongly correlated statistics.
Handle missing values explicitly and never replace them with zero.
Evaluate 2025 total PPR and PPR per game.
Report Spearman correlation and mean absolute rank error.
Also report top-12, top-24, and top-36 accuracy.
Prefer stable, simple weights over a one-season overfit.
Update `scripts/build_wr_board.py` with the supported weights.
Fix repository-relative paths and keep weights configurable.
Use receiving-yard, reception, and receiving-TD sportsbook lines.
Use all available markets, even when only some players have them.
Reweight available lines; a missing line means unknown, not bad.
Weight yards and receptions above volatile touchdowns.
Create `scripts/find_wr_sleepers.py` and `wr/wr_sleepers_2026.csv`.
Find underrated upside, not merely low-ranked main-board players.
Backtest breakouts by rank gain, top-36 arrival, and PPR/G growth.
Show if Michael Wilson's 2024 profile identified his 2025 breakout.
Do not tune the model only to make Michael Wilson rank highly.
Output upside, risk, confidence, market lines, and short reasons.
Add tests for leakage, weights, matching, missing data, and determinism.
Update `docs/WR_RANKING_METHOD.md` and run every script and test.
Stop only when outputs exist, tests pass, docs are updated, and results are reported.
