#!/usr/bin/env python3
"""Tests for the WR model: leakage, weights, matching, missing data,
and determinism. Run with:  python3 -m unittest discover -s tests -v
"""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import backtest_wr_weights
import build_wr_board
import find_wr_sleepers
import merge_act_pred_stats
import wr_model
from wr_model import (
    LEAKAGE_COLUMNS, average_ranks, check_weights, clean_share,
    dedupe_players, evaluate_ranking, match_report, norm_name, number,
    percentile, score_players, spearman, weighted,
)


class TestLeakage(unittest.TestCase):
    """No script may consume 2025 outcomes as 2024-era features."""

    def test_backtest_feature_columns_exclude_outcomes(self):
        overlap = LEAKAGE_COLUMNS.intersection(backtest_wr_weights.FEATURE_COLUMNS)
        self.assertEqual(overlap, frozenset())

    def test_no_metric_references_a_leakage_column(self):
        metric_groups = [backtest_wr_weights.BACKTEST_METRICS,
                         backtest_wr_weights.OPTIMIZE_METRICS,
                         build_wr_board.METRICS]
        for group in metric_groups:
            for items in group.values():
                for name, _ in items:
                    self.assertNotIn(name, LEAKAGE_COLUMNS)
                    self.assertNotIn("PPR_Points", name)

    def test_sleeper_signal_columns_exclude_outcomes(self):
        for cols in (find_wr_sleepers.COLS_2024, find_wr_sleepers.COLS_2025):
            for column in cols.values():
                self.assertNotIn(column, LEAKAGE_COLUMNS)

    def test_perturbing_outcome_column_does_not_change_scores(self):
        row = {"Player": "test player", "G": 12, "FPTS/G": 10.0, "XFP": 11.0,
               "YPRR": 1.5, "TGT/G": 6.0, "Target_Share": 20.0,
               "air_pct": 25.0, "WOPR": 0.5, "RZ_TGT_PCT": 15.0,
               "normalized_line": 700.0, "PPR_Points_2025": 100.0}
        other = dict(row, Player="other player", PPR_Points_2025=999.0,
                     **{"FPTS/G": 8.0})
        weights = {"market": 0.4, "production": 0.3, "opportunity": 0.3}
        metrics = {k: v for k, v in backtest_wr_weights.BACKTEST_METRICS.items()
                   if k != "trend"}

        first = score_players([dict(row), dict(other)], metrics, weights, "G")
        row["PPR_Points_2025"] = 0.0
        second = score_players([dict(row), dict(other)], metrics, weights, "G")
        self.assertEqual([r["model_score"] for r in first],
                         [r["model_score"] for r in second])


class TestWeights(unittest.TestCase):
    def test_default_board_weights_are_valid(self):
        check_weights(build_wr_board.CATEGORY_WEIGHTS, build_wr_board.METRICS)

    def test_current_backtest_weights_are_valid(self):
        check_weights(backtest_wr_weights.CURRENT_WEIGHTS,
                      backtest_wr_weights.BACKTEST_METRICS)

    def test_sleeper_weights_sum_to_one_and_nonnegative(self):
        weights = find_wr_sleepers.SIGNAL_WEIGHTS
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertTrue(all(w >= 0 for w in weights.values()))

    def test_negative_weight_rejected(self):
        with self.assertRaises(ValueError):
            check_weights({"a": -0.5, "b": 1.5}, {"a": [("x", 1.0)],
                                                  "b": [("y", 1.0)]})

    def test_unnormalized_weights_rejected(self):
        with self.assertRaises(ValueError):
            check_weights({"a": 0.5, "b": 0.4}, {"a": [("x", 1.0)],
                                                 "b": [("y", 1.0)]})

    def test_weighted_renormalizes_over_present_values(self):
        self.assertEqual(weighted([(80.0, 0.5), (None, 0.5)]), 80.0)
        self.assertAlmostEqual(weighted([(60.0, 0.25), (90.0, 0.75)]), 82.5)
        self.assertIsNone(weighted([(None, 0.5), (None, 0.5)]))

    def test_board_cli_weight_parsing(self):
        weights = build_wr_board.parse_weights(
            "market=0.35,production=0.25,opportunity=0.25,youth=0,trend=0.15")
        check_weights(weights, build_wr_board.METRICS)
        self.assertEqual(weights["trend"], 0.15)
        with self.assertRaises(SystemExit):
            build_wr_board.parse_weights("bogus=0.5")


class TestNameMatching(unittest.TestCase):
    def test_suffixes_periods_case_and_accents(self):
        self.assertEqual(norm_name("Marvin Harrison Jr."), "marvinharrison")
        self.assertEqual(norm_name("A.J. Brown"), norm_name("AJ Brown"))
        self.assertEqual(norm_name("Calvin Austin III"), "calvinaustin")
        self.assertEqual(norm_name("Amon-Ra St. Brown"), "amonrastbrown")
        self.assertEqual(norm_name("José Ramírez"), "joseramirez")
        self.assertEqual(norm_name("KaVontae Turpin (KR)"), "kavontaeturpin")

    def test_props_name_aliases(self):
        self.assertEqual(norm_name("Cameron Skattebo"), norm_name("Cam Skattebo"))
        self.assertEqual(norm_name("Cameron Ward"), norm_name("Cam Ward"))
        self.assertEqual(
            norm_name("Jake Ferguson 2026/2027 Markets"),
            norm_name("Jake Ferguson"),
        )

    def test_dedupe_prefers_aggregate_multi_team_row(self):
        rows = [
            {"Player": "Traded Guy", "Team": "CAR", "G": "7"},
            {"Player": "Traded Guy", "Team": "3TM", "G": "12"},
            {"Player": "Traded Guy", "Team": "BAL", "G": "5"},
            {"Player": "Solo Guy", "Team": "SEA", "G": "17"},
        ]
        deduped, report = dedupe_players(rows)
        by_name = {r["Player"]: r for r in deduped}
        self.assertEqual(len(deduped), 2)
        self.assertEqual(by_name["Traded Guy"]["Team"], "3TM")
        self.assertIn("tradedguy", report)
        self.assertNotIn("sologuy", report)

    def test_match_report_finds_one_sided_names(self):
        left = [{"Player": "Both Sides"}, {"Player": "Left Only"}]
        right = [{"Player": "both sides"}, {"Player": "Right Only"}]
        left_only, right_only = match_report(left, right)
        self.assertEqual(left_only, ["leftonly"])
        self.assertEqual(right_only, ["rightonly"])

    def test_real_files_keep_prior_players_and_include_2025_newcomers(self):
        rows_2024, _ = dedupe_players(
            wr_model.read_rows(wr_model.WR_DIR / "wr_stats_2024.csv"))
        rows_2025 = wr_model.read_rows(
            wr_model.WR_DIR / "wr_stats_act_2025.csv")
        left_only, right_only = match_report(rows_2024, rows_2025)
        self.assertEqual(left_only, [])
        self.assertTrue(
            {"lutherburden", "tetairoamcmillan", "emekaegbuka"}.issubset(
                set(right_only)
            )
        )

    def test_requested_newcomers_are_in_actual_prediction_merges(self):
        rb_rows = wr_model.read_rows(
            wr_model.REPO_ROOT / "rbs" / "rb_stats_act_pred_2025.csv")
        wr_rows = wr_model.read_rows(
            wr_model.WR_DIR / "wr_stats_act_pred_2025.csv")
        rb = {norm_name(row["Player"]): row for row in rb_rows}
        wr = {norm_name(row["Player"]): row for row in wr_rows}
        self.assertEqual(rb["omarionhampton"]["merge_status"], "actual_only")
        self.assertEqual(wr["lutherburden"]["merge_status"], "actual_only")
        self.assertGreater(number(rb["omarionhampton"]["FPTS_2025"]), 0)
        self.assertGreater(number(wr["lutherburden"]["FPTS_2025"]), 0)

    def test_2026_rb_wr_props_only_players_are_in_merges(self):
        paths = {
            "rb": wr_model.REPO_ROOT / "rbs" / "rb_stats_act_pred_2025.csv",
            "wr": wr_model.WR_DIR / "wr_stats_act_pred_2025.csv",
        }
        for position, path in paths.items():
            rows = {
                norm_name(row["Player"]): row
                for row in wr_model.read_rows(path)
            }
            config = merge_act_pred_stats.POSITION_FILES[position]
            line_fields = [
                merge_act_pred_stats.prop_column(market)
                for market in config["prop_markets"]
            ]
            for player in config["prop_only_players"]:
                row = rows[norm_name(player)]
                self.assertEqual(row["merge_status"], "prop_only")
                self.assertTrue(any(number(row.get(field)) for field in line_fields))


class TestMissingData(unittest.TestCase):
    def test_number_parsing(self):
        self.assertIsNone(number(""))
        self.assertIsNone(number(None))
        self.assertIsNone(number("N/A"))
        self.assertEqual(number("44.0%"), 44.0)
        self.assertEqual(number("1,234"), 1234.0)

    def test_percentile_of_missing_is_missing_not_zero(self):
        self.assertIsNone(percentile([1.0, 2.0, 3.0], None))
        self.assertIsNone(percentile([None, None], 1.0))
        self.assertEqual(percentile([1.0, 2.0, 3.0], 2.0), 50.0)

    def test_impossible_shares_become_missing(self):
        self.assertIsNone(clean_share(100.0, wr_model.MAX_TARGET_SHARE))
        self.assertIsNone(clean_share(-1.0, wr_model.MAX_TARGET_SHARE))
        self.assertEqual(clean_share(30.0, wr_model.MAX_TARGET_SHARE), 30.0)
        self.assertIsNone(clean_share(None, wr_model.MAX_TARGET_SHARE))

    def test_missing_market_scores_neutral_not_zero(self):
        metrics = {"market": [("line", 1.0)], "production": [("ppg", 1.0)]}
        weights = {"market": 0.5, "production": 0.5}
        rows = [
            {"Player": "has line", "G": 17, "line": 900.0, "ppg": 15.0},
            {"Player": "no line", "G": 17, "line": None, "ppg": 15.0},
        ]
        score_players(rows, metrics, weights, "G",
                      neutral_categories=("market",))
        no_line = next(r for r in rows if r["Player"] == "no line")
        self.assertEqual(no_line["market_score"], 50.0)
        self.assertIsNotNone(no_line["model_score"])

    def test_category_with_all_metrics_missing_is_dropped_not_zeroed(self):
        metrics = {"production": [("ppg", 1.0)],
                   "trend": [("nonexistent", 1.0)]}
        weights = {"production": 0.5, "trend": 0.5}
        rows = [{"Player": "a", "G": 17, "ppg": 15.0},
                {"Player": "b", "G": 17, "ppg": 5.0}]
        score_players(rows, metrics, weights, "G")
        self.assertIsNone(rows[0]["trend_score"])
        # Model score equals the production score alone (weight renormalized),
        # not production averaged with an imputed zero.
        self.assertEqual(rows[0]["model_score"], rows[0]["production_score"])

    def test_sleeper_signals_keep_missing_as_none(self):
        signals = find_wr_sleepers.extract_signals(
            {"Age": "24", "YPRR": "", "Target_Share": "10",
             "air_pct": "", "fpts_diff": "-1.5", "Routes Run": "300",
             "G": "10"},
            find_wr_sleepers.COLS_2024)
        self.assertEqual(signals["youth"], -24.0)
        self.assertIsNone(signals["efficiency"])
        self.assertIsNone(signals["role_gap"])
        self.assertEqual(signals["regression"], 1.5)
        self.assertEqual(signals["route_volume"], 30.0)


class TestRankingMath(unittest.TestCase):
    def test_average_ranks_with_ties(self):
        self.assertEqual(average_ranks([10, 20, 20, 30]), [1, 2.5, 2.5, 4])

    def test_spearman_perfect_and_inverse(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [40, 30, 20, 10]), -1.0)

    def test_evaluate_ranking_metrics(self):
        # Prediction reverses the two middle players of four.
        pairs = [(4.0, 400.0), (3.0, 100.0), (2.0, 300.0), (1.0, 50.0)]
        result = evaluate_ranking(pairs)
        self.assertEqual(result["n"], 4)
        self.assertEqual(result["rank_mae"], 0.5)
        self.assertEqual(result["top12_hits"], 4)
        self.assertEqual(result["top12_accuracy"], 1.0)


class TestDeterminism(unittest.TestCase):
    def _fixture_rows(self):
        return [
            {"Player": f"player {i}", "G": 10 + (i % 8),
             "line": 400.0 + 37 * i if i % 3 else None,
             "ppg": 5.0 + 0.7 * (i * 13 % 11),
             "tpg": 2.0 + 0.5 * (i * 7 % 9)}
            for i in range(30)
        ]

    def test_score_players_is_deterministic(self):
        metrics = {"market": [("line", 1.0)],
                   "production": [("ppg", 0.6), ("tpg", 0.4)]}
        weights = {"market": 0.4, "production": 0.6}
        a = score_players(copy.deepcopy(self._fixture_rows()), metrics,
                          weights, "G", shrink_categories=("production",),
                          neutral_categories=("market",))
        b = score_players(copy.deepcopy(self._fixture_rows()), metrics,
                          weights, "G", shrink_categories=("production",),
                          neutral_categories=("market",))
        self.assertEqual([r["model_score"] for r in a],
                         [r["model_score"] for r in b])

    def test_equal_scores_order_by_name(self):
        rows = [{"Player": name, "signals": {s: 1.0 for s in
                                             find_wr_sleepers.SIGNAL_WEIGHTS}}
                for name in ("zeta", "alpha", "mike")]
        find_wr_sleepers.score_pool(rows, find_wr_sleepers.SIGNAL_WEIGHTS)
        self.assertEqual([r["Player"] for r in rows],
                         ["alpha", "mike", "zeta"])

    def test_bootstrap_is_seed_stable(self):
        rows = self._fixture_rows()
        metrics = {"market": [("line", 1.0)],
                   "production": [("ppg", 0.6), ("tpg", 0.4)]}
        weights = {"market": 0.4, "production": 0.6}
        score_players(rows, metrics, weights, "G",
                      neutral_categories=("market",))
        for row in rows:
            row["actual_ppr_2025"] = row["ppg"] * row["G"]
        first = backtest_wr_weights.bootstrap_spearman(
            rows, weights, resamples=50, seed=7)
        second = backtest_wr_weights.bootstrap_spearman(
            rows, weights, resamples=50, seed=7)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
