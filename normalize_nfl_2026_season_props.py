#!/usr/bin/env python3
"""Normalize NFL season props to -110/-110 and build a unified consensus.

The input contains standard two-way over/under markets and a small number of
one-sided DraftKings alternate ladders. Standard markets are proportionally
de-vigged and translated to their logistic 50th-percentile line. Ladder-only
markets are fitted directly from their available alternate points after
removing the sportsbook's typical market hold.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
import unicodedata
from collections import defaultdict
from pathlib import Path


DEFAULT_INPUT = "nfl_2026_season_props_2026-07-19.csv"
DEFAULT_NORMALIZED = "nfl_2026_season_props_normalized_-110_2026-07-19.csv"
DEFAULT_UNIFIED = "nfl_2026_season_props_unified_2026-07-19.csv"

# These scale/line ratios are calibrated from the same-book alternate ladders
# in the source file. See the methodology document for the derivation.
VOLUME_SCALE_RATIO = 0.30594991142364136
COUNT_SCALE_RATIO = 0.44063243801941165

VOLUME_MARKETS = {
    "passing_yards",
    "rushing_yards",
    "receiving_yards",
    "receptions",
}
COUNT_MARKETS = {
    "passing_tds",
    "rushing_tds",
    "receiving_tds",
    "sacks",
}

SPORTSBOOK_ORDER = [
    "BetMGM",
    "BetRivers",
    "Caesars",
    "DraftKings",
    "FanDuel",
    "bet365",
]

NORMALIZED_FIELDS = [
    "sportsbook",
    "jurisdiction",
    "season",
    "player",
    "source_player",
    "market",
    "line",
    "side",
    "american_odds",
    "decimal_odds",
    "retrieved_at_ct",
    "market_id",
    "selection_id",
    "source_url",
    "source_line",
    "source_american_odds",
    "source_decimal_odds",
    "source_market_id",
    "source_selection_id",
    "source_lines_used",
    "source_odds_used",
    "no_vig_probability_at_source_line",
    "source_overround",
    "logit_probability_at_source_line",
    "logistic_scale",
    "scale_ratio",
    "line_adjustment",
    "normalization_method",
]

UNIFIED_FIELDS = [
    "season",
    "player",
    "market",
    "bettable_line_nearest_half",
    "sportsbook_count",
    "sportsbooks",
    "betmgm_line",
    "betrivers_line",
    "caesars_line",
    "draftkings_line",
    "fanduel_line",
    "bet365_line",
    "minimum_sportsbook_line",
    "maximum_sportsbook_line",
    "sportsbook_line_range",
    "population_standard_deviation",
    "paired_two_way_book_count",
    "ladder_fit_book_count",
]


def american_to_probability(odds: str | int) -> float:
    value = int(odds)
    if value == 0:
        raise ValueError("American odds cannot be zero")
    if value < 0:
        return abs(value) / (abs(value) + 100.0)
    return 100.0 / (value + 100.0)


def american_to_decimal(odds: str | int) -> float:
    value = int(odds)
    if value < 0:
        return 1.0 + 100.0 / abs(value)
    return 1.0 + value / 100.0


def logit(probability: float) -> float:
    if not 0.0 < probability < 1.0:
        raise ValueError(f"Probability must be strictly between 0 and 1: {probability}")
    return math.log(probability / (1.0 - probability))


def fmt(value: float | None, places: int = 6) -> str:
    if value is None:
        return ""
    rendered = f"{value:.{places}f}"
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def nearest_half(value: float) -> float:
    # Values exactly on a quarter are rounded upward, avoiding banker's rounding.
    scaled = value * 2.0
    return math.floor(scaled + 0.5 + 1e-12) / 2.0


def nearest_whole(value: float) -> float:
    # Values exactly on a half are rounded upward, avoiding banker's rounding.
    return float(math.floor(value + 0.5 + 1e-12))


def scale_ratio_for_market(market: str) -> float:
    if market in VOLUME_MARKETS:
        return VOLUME_SCALE_RATIO
    if market in COUNT_MARKETS:
        return COUNT_SCALE_RATIO
    raise ValueError(f"No scale family configured for market: {market}")


def player_match_key(player: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", player)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    key = re.sub(r"[^a-z0-9]", "", ascii_name)
    # One source spells McMillan with a single "l"; the player, market, and
    # overlapping sportsbook lines make this deterministic rather than fuzzy.
    aliases = {"tetairoamcmilan": "tetairoamcmillan"}
    return aliases.get(key, key)


def canonical_player_names(source_rows: list[dict[str, str]]) -> dict[str, str]:
    appearances: dict[str, dict[str, set[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(set)
    )
    row_counts: dict[tuple[str, str], int] = defaultdict(int)
    for row in source_rows:
        key = player_match_key(row["player"])
        display = row["player"]
        appearances[key][display].add((row["sportsbook"], row["market"]))
        row_counts[(key, display)] += 1

    canonical: dict[str, str] = {}
    for key, displays in appearances.items():
        canonical[key] = max(
            displays,
            key=lambda display: (
                len(displays[display]),
                row_counts[(key, display)],
                display,
            ),
        )
    return canonical


def linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    if len(xs) != len(ys) or len(xs) < 2:
        raise ValueError("Linear fit requires at least two paired values")
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0.0:
        raise ValueError("Linear fit requires distinct x values")
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    intercept = y_mean - slope * x_mean
    return intercept, slope


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No data rows found in {path}")
    required = {
        "sportsbook",
        "jurisdiction",
        "season",
        "player",
        "market",
        "line",
        "side",
        "american_odds",
        "decimal_odds",
        "retrieved_at_ct",
        "market_id",
        "selection_id",
        "source_url",
    }
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"Missing required input fields: {sorted(missing)}")
    return rows


def exact_market_groups(
    rows: list[dict[str, str]],
) -> dict[tuple[str, str, str, str, str, str], dict[str, dict[str, str]]]:
    groups: dict[
        tuple[str, str, str, str, str, str], dict[str, dict[str, str]]
    ] = defaultdict(dict)
    for row in rows:
        key = (
            row["sportsbook"],
            row["jurisdiction"],
            row["season"],
            row["player"],
            row["market"],
            row["line"],
        )
        side = row["side"]
        if side in groups[key]:
            raise ValueError(f"Duplicate {side} selection for {key}")
        groups[key][side] = row
    return dict(groups)


def median_holds_by_book_market(
    exact_groups: dict[
        tuple[str, str, str, str, str, str], dict[str, dict[str, str]]
    ],
) -> dict[tuple[str, str], float]:
    holds: dict[tuple[str, str], list[float]] = defaultdict(list)
    for key, sides in exact_groups.items():
        sportsbook, _, _, _, market, _ = key
        if set(sides) != {"Over", "Under"}:
            continue
        over_probability = american_to_probability(sides["Over"]["american_odds"])
        under_probability = american_to_probability(sides["Under"]["american_odds"])
        holds[(sportsbook, market)].append(over_probability + under_probability)
    return {key: statistics.median(values) for key, values in holds.items()}


def paired_prediction(
    sides: dict[str, dict[str, str]],
) -> tuple[float, dict[str, float | str]]:
    over_row = sides["Over"]
    under_row = sides["Under"]
    source_line = float(over_row["line"])
    if float(under_row["line"]) != source_line:
        raise ValueError("Over and Under source lines do not match")

    over_implied = american_to_probability(over_row["american_odds"])
    under_implied = american_to_probability(under_row["american_odds"])
    overround = over_implied + under_implied
    fair_over = over_implied / overround
    fair_under = under_implied / overround

    ratio = scale_ratio_for_market(over_row["market"])
    scale = ratio * source_line
    over_logit = logit(fair_over)
    even_line = source_line + scale * over_logit
    adjustment = even_line - source_line

    if even_line <= 0.0:
        raise ValueError(f"Non-positive normalized line for {over_row}")
    if fair_over > 0.5 and adjustment <= 0.0:
        raise AssertionError("Over-favored market must move to a higher even line")
    if fair_over < 0.5 and adjustment >= 0.0:
        raise AssertionError("Under-favored market must move to a lower even line")

    metadata: dict[str, float | str] = {
        "source_line": source_line,
        "fair_over": fair_over,
        "fair_under": fair_under,
        "overround": overround,
        "over_logit": over_logit,
        "scale": scale,
        "scale_ratio": ratio,
        "adjustment": adjustment,
        "method": "paired_two_way_proportional_devig_logistic",
    }
    return even_line, metadata


def ladder_prediction(
    rows: list[dict[str, str]], typical_hold: float
) -> tuple[float, dict[str, float | str]]:
    if len(rows) < 3 or any(row["side"] != "Over" for row in rows):
        raise ValueError("A ladder-only fit requires at least three Over selections")

    sorted_rows = sorted(rows, key=lambda row: float(row["line"]))
    xs: list[float] = []
    ys: list[float] = []
    for row in sorted_rows:
        implied = american_to_probability(row["american_odds"])
        fair_over = implied / typical_hold
        # The typical-hold estimate should keep these naturally in range. The
        # bound only protects the logit transform from floating-point endpoints.
        fair_over = min(max(fair_over, 1e-9), 1.0 - 1e-9)
        xs.append(float(row["line"]))
        ys.append(logit(fair_over))

    intercept, slope = linear_fit(xs, ys)
    if slope >= 0.0:
        raise ValueError(f"Alternate ladder probability does not decrease with line: {rows}")
    scale = -1.0 / slope
    even_line = -intercept / slope
    if even_line <= 0.0:
        raise ValueError(f"Non-positive ladder-fitted line: {rows}")

    metadata: dict[str, float | str] = {
        "source_line": "",
        "fair_over": "",
        "fair_under": "",
        "overround": typical_hold,
        "over_logit": "",
        "scale": scale,
        "scale_ratio": scale / even_line,
        "adjustment": "",
        "method": "one_sided_ladder_typical_hold_logistic_fit",
    }
    return even_line, metadata


def normalized_output_rows(
    source_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, float | str]]]:
    exact_groups = exact_market_groups(source_rows)
    typical_holds = median_holds_by_book_market(exact_groups)
    canonical_names = canonical_player_names(source_rows)

    logical_groups: dict[
        tuple[str, str, str, str, str], list[dict[str, str]]
    ] = defaultdict(list)
    for row in source_rows:
        key = (
            row["sportsbook"],
            row["jurisdiction"],
            row["season"],
            row["player"],
            row["market"],
        )
        logical_groups[key].append(row)

    normalized: list[dict[str, str]] = []
    predictions: list[dict[str, float | str]] = []
    for logical_key in sorted(
        logical_groups,
        key=lambda key: (
            key[2],
            key[4],
            canonical_names[player_match_key(key[3])],
            SPORTSBOOK_ORDER.index(key[0]),
        ),
    ):
        sportsbook, jurisdiction, season, source_player, market = logical_key
        player = canonical_names[player_match_key(source_player)]
        group_rows = logical_groups[logical_key]

        paired_candidates: list[dict[str, dict[str, str]]] = []
        for exact_key, sides in exact_groups.items():
            if exact_key[:5] == logical_key and set(sides) == {"Over", "Under"}:
                paired_candidates.append(sides)

        if len(paired_candidates) > 1:
            raise ValueError(f"Multiple two-way base lines found for {logical_key}")

        if paired_candidates:
            sides = paired_candidates[0]
            even_line, metadata = paired_prediction(sides)
            source_rows_by_side = sides
            source_lines_used = sides["Over"]["line"]
            source_odds_used = (
                f"Over {sides['Over']['american_odds']}|"
                f"Under {sides['Under']['american_odds']}"
            )
            source_urls = [sides["Over"]["source_url"], sides["Under"]["source_url"]]
            retrieved_values = [
                sides["Over"]["retrieved_at_ct"],
                sides["Under"]["retrieved_at_ct"],
            ]
        else:
            if (sportsbook, market) not in typical_holds:
                raise ValueError(f"No typical hold available for ladder {logical_key}")
            even_line, metadata = ladder_prediction(
                group_rows, typical_holds[(sportsbook, market)]
            )
            source_rows_by_side = {}
            sorted_ladder = sorted(group_rows, key=lambda row: float(row["line"]))
            source_lines_used = "|".join(row["line"] for row in sorted_ladder)
            source_odds_used = "|".join(
                f"{row['side']} {row['american_odds']}" for row in sorted_ladder
            )
            source_urls = [row["source_url"] for row in sorted_ladder]
            retrieved_values = [row["retrieved_at_ct"] for row in sorted_ladder]

        unique_urls = list(dict.fromkeys(source_urls))
        retrieved_at = max(retrieved_values)
        prediction = {
            "sportsbook": sportsbook,
            "jurisdiction": jurisdiction,
            "season": season,
            "player": player,
            "market": market,
            "line": even_line,
            "method": metadata["method"],
        }
        predictions.append(prediction)

        for side in ("Over", "Under"):
            source = source_rows_by_side.get(side)
            fair_side = (
                metadata["fair_over"] if side == "Over" else metadata["fair_under"]
            )
            side_logit = ""
            if isinstance(fair_side, float):
                side_logit = logit(fair_side)
            output = {
                "sportsbook": sportsbook,
                "jurisdiction": jurisdiction,
                "season": season,
                "player": player,
                "source_player": source_player,
                "market": market,
                "line": fmt(even_line),
                "side": side,
                "american_odds": "-110",
                "decimal_odds": fmt(american_to_decimal(-110), 14),
                "retrieved_at_ct": retrieved_at,
                # The normalized line is synthetic, so source selection IDs are
                # retained only in explicitly named provenance columns.
                "market_id": "",
                "selection_id": "",
                "source_url": "|".join(unique_urls),
                "source_line": source["line"] if source else "",
                "source_american_odds": source["american_odds"] if source else "",
                "source_decimal_odds": source["decimal_odds"] if source else "",
                "source_market_id": source["market_id"] if source else "",
                "source_selection_id": source["selection_id"] if source else "",
                "source_lines_used": source_lines_used,
                "source_odds_used": source_odds_used,
                "no_vig_probability_at_source_line": (
                    fmt(fair_side, 9) if isinstance(fair_side, float) else ""
                ),
                "source_overround": fmt(float(metadata["overround"]), 9),
                "logit_probability_at_source_line": (
                    fmt(side_logit, 9) if isinstance(side_logit, float) else ""
                ),
                "logistic_scale": fmt(float(metadata["scale"]), 9),
                "scale_ratio": fmt(float(metadata["scale_ratio"]), 12),
                "line_adjustment": (
                    fmt(float(metadata["adjustment"]), 9)
                    if isinstance(metadata["adjustment"], float)
                    else ""
                ),
                "normalization_method": str(metadata["method"]),
            }
            normalized.append(output)

    return normalized, predictions


def unified_output_rows(
    predictions: list[dict[str, float | str]],
) -> list[dict[str, str]]:
    groups: dict[
        tuple[str, str, str], list[dict[str, float | str]]
    ] = defaultdict(list)
    for prediction in predictions:
        key = (
            str(prediction["season"]),
            str(prediction["player"]),
            str(prediction["market"]),
        )
        groups[key].append(prediction)

    sportsbook_columns = {
        "BetMGM": "betmgm_line",
        "BetRivers": "betrivers_line",
        "Caesars": "caesars_line",
        "DraftKings": "draftkings_line",
        "FanDuel": "fanduel_line",
        "bet365": "bet365_line",
    }
    unified: list[dict[str, str]] = []
    for (season, player, market), values in sorted(
        groups.items(), key=lambda item: (item[0][0], item[0][2], item[0][1])
    ):
        books = [str(value["sportsbook"]) for value in values]
        if len(books) != len(set(books)):
            raise ValueError(f"Duplicate sportsbook in unified group: {(season, player, market)}")
        lines = [float(value["line"]) for value in values]
        mean_line = statistics.fmean(lines)
        minimum = min(lines)
        maximum = max(lines)
        methods = [str(value["method"]) for value in values]
        presentation_line = (
            nearest_whole(mean_line)
            if market in {"passing_tds", "rushing_tds", "receiving_tds"}
            else nearest_half(mean_line)
        )
        row = {
            "season": season,
            "player": player,
            "market": market,
            "bettable_line_nearest_half": fmt(presentation_line, 1),
            "sportsbook_count": str(len(values)),
            "sportsbooks": "|".join(
                book for book in SPORTSBOOK_ORDER if book in set(books)
            ),
            "minimum_sportsbook_line": fmt(minimum),
            "maximum_sportsbook_line": fmt(maximum),
            "sportsbook_line_range": fmt(maximum - minimum),
            "population_standard_deviation": fmt(statistics.pstdev(lines)),
            "paired_two_way_book_count": str(
                sum(method.startswith("paired_two_way") for method in methods)
            ),
            "ladder_fit_book_count": str(
                sum(method.startswith("one_sided_ladder") for method in methods)
            ),
        }
        for sportsbook, column in sportsbook_columns.items():
            matching = [
                float(value["line"])
                for value in values
                if value["sportsbook"] == sportsbook
            ]
            row[column] = fmt(matching[0]) if matching else ""
        unified.append(row)
    return unified


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def validate_outputs(
    normalized: list[dict[str, str]],
    predictions: list[dict[str, float | str]],
    unified: list[dict[str, str]],
) -> None:
    if len(normalized) != 2 * len(predictions):
        raise AssertionError("Every sportsbook prediction must have Over and Under rows")
    if any(row["american_odds"] != "-110" for row in normalized):
        raise AssertionError("All normalized odds must be -110")

    pair_check: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in normalized:
        key = (row["sportsbook"], row["season"], row["player"], row["market"])
        pair_check[key].append(row)
    for key, rows in pair_check.items():
        if {row["side"] for row in rows} != {"Over", "Under"} or len(rows) != 2:
            raise AssertionError(f"Normalized pair is incomplete: {key}")
        if len({row["line"] for row in rows}) != 1:
            raise AssertionError(f"Normalized pair has mismatched lines: {key}")

    for row in unified:
        line_columns = [
            row["betmgm_line"],
            row["betrivers_line"],
            row["caesars_line"],
            row["draftkings_line"],
            row["fanduel_line"],
            row["bet365_line"],
        ]
        available = [float(value) for value in line_columns if value]
        if len(available) != int(row["sportsbook_count"]):
            raise AssertionError(f"Unified sportsbook count mismatch: {row}")
        mean_line = statistics.fmean(available)
        expected_line = (
            nearest_whole(mean_line)
            if row["market"] in {"passing_tds", "rushing_tds", "receiving_tds"}
            else nearest_half(mean_line)
        )
        if float(row["bettable_line_nearest_half"]) != expected_line:
            raise AssertionError(f"Unified presentation-line mismatch: {row}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(DEFAULT_INPUT))
    parser.add_argument("--normalized-output", type=Path, default=Path(DEFAULT_NORMALIZED))
    parser.add_argument("--unified-output", type=Path, default=Path(DEFAULT_UNIFIED))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_rows = load_rows(args.input)
    normalized, predictions = normalized_output_rows(source_rows)
    unified = unified_output_rows(predictions)
    validate_outputs(normalized, predictions, unified)
    write_csv(args.normalized_output, NORMALIZED_FIELDS, normalized)
    write_csv(args.unified_output, UNIFIED_FIELDS, unified)

    paired_count = sum(
        prediction["method"] == "paired_two_way_proportional_devig_logistic"
        for prediction in predictions
    )
    ladder_count = len(predictions) - paired_count
    print(f"Source rows: {len(source_rows)}")
    print(f"Sportsbook-level predictions: {len(predictions)}")
    print(f"  Paired two-way: {paired_count}")
    print(f"  One-sided ladder fits: {ladder_count}")
    print(f"Normalized rows: {len(normalized)}")
    print(f"Unified props: {len(unified)}")
    print(f"Normalized output: {args.normalized_output}")
    print(f"Unified output: {args.unified_output}")


if __name__ == "__main__":
    main()
