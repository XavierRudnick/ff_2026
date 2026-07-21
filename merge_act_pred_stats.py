#!/usr/bin/env python3
"""Merge 2025 actuals with 2024 player stat CSVs by position.

Each output keeps the 2025 actuals and 2024 stats side by side, adds
``*_diff_2025_minus_2024`` columns for useful numeric stat comparisons, and
keeps ``normalized_line`` labeled as the predicted value.
"""

import csv
import re
import unicodedata
from collections import OrderedDict
from pathlib import Path


ROOT = Path(__file__).resolve().parent

POSITION_FILES = {
    "rb": {
        "actual": "rb_stats_2025.csv",
        "old": "rb_stats.csv",
        "output": "rb_stats_act_pred_2025.csv",
    },
    "wr": {
        "actual": "wr_stats_act_2025.csv",
        "old": "wr_stats_pred_2025.csv",
        "output": "wr_stats_act_pred_2025.csv",
    },
}

ACTUAL_SUFFIX = "2025"
OLD_SUFFIX = "2024"
PREDICTED_COLUMNS = {"normalized_line"}
SKIP_COLUMNS = {"", "_index", "Unnamed: 0", "PPR_Points_2025", "rank"}
NO_DIFF_COLUMNS = {"Age"}


def normalize_name(name):
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"\([^)]*\)", "", name.lower())
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", name)
    return re.sub(r"[^a-z0-9]", "", name)


def unique_headers(header):
    seen = {}
    result = []
    for column in header:
        column = column.strip() or "_index"
        seen[column] = seen.get(column, 0) + 1
        if seen[column] == 1:
            result.append(column)
        else:
            result.append(f"{column}_{seen[column]}")
    return result


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as input_file:
        reader = csv.reader(input_file)
        header = unique_headers(next(reader))
        rows = []
        for values in reader:
            values = values + [""] * (len(header) - len(values))
            rows.append(dict(zip(header, values[: len(header)])))
    return header, rows


def keep_column(column):
    return column not in SKIP_COLUMNS and column != "Player" and not column.startswith("Player_")


def ordered_stat_columns(actual_header, old_header):
    columns = []
    for column in actual_header + old_header:
        if keep_column(column) and column not in columns:
            columns.append(column)
    return columns


def parse_number(value):
    value = str(value).strip()
    if not value:
        return None
    if value.endswith("%"):
        value = value[:-1]
    value = value.replace(",", "")
    try:
        return float(value)
    except ValueError:
        return None


def format_number(value):
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def is_numeric_column(column, keys, actual_rows, old_rows):
    observed = False
    for key in keys:
        for rows in (actual_rows, old_rows):
            row = rows.get(key)
            if row is None:
                continue
            value = row.get(column, "")
            if not str(value).strip():
                continue
            observed = True
            if parse_number(value) is None:
                return False
    return observed


def is_multi_team_total(row):
    return bool(re.fullmatch(r"\d+TM", row.get("Team", "").strip().upper()))


def index_by_player(rows):
    grouped = OrderedDict()
    for row in rows:
        player = row.get("Player", "").strip()
        if not player:
            continue
        key = normalize_name(player)
        grouped.setdefault(key, []).append(row)

    indexed = OrderedDict()
    duplicate_notes = []
    for key, player_rows in grouped.items():
        totals = [row for row in player_rows if is_multi_team_total(row)]
        selected = totals[0] if totals else player_rows[0]
        indexed[key] = selected
        if len(player_rows) > 1:
            duplicate_notes.append(
                {
                    "player": selected.get("Player", ""),
                    "kept_team": selected.get("Team", ""),
                    "ignored_rows": len(player_rows) - 1,
                }
            )
    return indexed, duplicate_notes


def build_output_header(columns, actual_columns, old_columns, diff_columns):
    header = ["Player", "merge_status"]
    for column in columns:
        if column in PREDICTED_COLUMNS:
            if column in old_columns:
                header.append(f"{column}_pred")
            continue
        if column in actual_columns:
            header.append(f"{column}_{ACTUAL_SUFFIX}")
        if column in old_columns:
            header.append(f"{column}_{OLD_SUFFIX}")
        if column in diff_columns:
            header.append(f"{column}_diff_{ACTUAL_SUFFIX}_minus_{OLD_SUFFIX}")
    return header


def build_output_rows(keys, columns, actual_rows, old_rows, actual_columns, old_columns, diff_columns):
    output_rows = []
    for key in keys:
        actual_row = actual_rows.get(key)
        old_row = old_rows.get(key)
        player = (
            (actual_row or {}).get("Player")
            or (old_row or {}).get("Player")
            or key
        )
        if actual_row and old_row:
            status = "both"
        elif actual_row:
            status = "actual_only"
        else:
            status = "old_only"

        output_row = {"Player": player, "merge_status": status}
        for column in columns:
            if column in PREDICTED_COLUMNS:
                if column in old_columns:
                    output_row[f"{column}_pred"] = (old_row or {}).get(column, "")
                continue
            if column in actual_columns:
                output_row[f"{column}_{ACTUAL_SUFFIX}"] = (actual_row or {}).get(column, "")
            if column in old_columns:
                output_row[f"{column}_{OLD_SUFFIX}"] = (old_row or {}).get(column, "")
            if column in diff_columns:
                actual_value = parse_number((actual_row or {}).get(column, ""))
                old_value = parse_number((old_row or {}).get(column, ""))
                output_row[f"{column}_diff_{ACTUAL_SUFFIX}_minus_{OLD_SUFFIX}"] = (
                    format_number(actual_value - old_value)
                    if actual_value is not None and old_value is not None
                    else ""
                )
        output_rows.append(output_row)
    return output_rows


def merge_position(position, config):
    actual_header, actual_raw_rows = read_csv(ROOT / config["actual"])
    old_header, old_raw_rows = read_csv(ROOT / config["old"])
    actual_rows, actual_duplicates = index_by_player(actual_raw_rows)
    old_rows, old_duplicates = index_by_player(old_raw_rows)

    actual_columns = [column for column in actual_header if keep_column(column)]
    old_columns = [column for column in old_header if keep_column(column)]
    columns = ordered_stat_columns(actual_header, old_header)

    keys = list(actual_rows)
    keys.extend(key for key in old_rows if key not in actual_rows)
    diff_columns = [
        column
        for column in columns
        if column not in NO_DIFF_COLUMNS
        and column not in PREDICTED_COLUMNS
        if column in actual_columns
        and column in old_columns
        and is_numeric_column(column, keys, actual_rows, old_rows)
    ]

    output_header = build_output_header(columns, actual_columns, old_columns, diff_columns)
    output_rows = build_output_rows(
        keys,
        columns,
        actual_rows,
        old_rows,
        actual_columns,
        old_columns,
        diff_columns,
    )

    output_path = ROOT / config["output"]
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=output_header)
        writer.writeheader()
        writer.writerows(output_rows)

    both = sum(row["merge_status"] == "both" for row in output_rows)
    actual_only = sum(row["merge_status"] == "actual_only" for row in output_rows)
    old_only = sum(row["merge_status"] == "old_only" for row in output_rows)
    ignored_split_rows = sum(note["ignored_rows"] for note in actual_duplicates + old_duplicates)
    return {
        "position": position.upper(),
        "output": config["output"],
        "rows": len(output_rows),
        "both": both,
        "actual_only": actual_only,
        "old_only": old_only,
        "diff_columns": len(diff_columns),
        "ignored_split_rows": ignored_split_rows,
    }


def main():
    summaries = [merge_position(position, config) for position, config in POSITION_FILES.items()]
    for summary in summaries:
        print(
            "{position}: wrote {output} with {rows} rows "
            "({both} matched, {actual_only} actual-only, {old_only} 2024-only), "
            "{diff_columns} diff columns; ignored {ignored_split_rows} split-team rows".format(
                **summary
            )
        )


if __name__ == "__main__":
    main()
