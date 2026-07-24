#!/usr/bin/env python3
"""Shared helpers for the WR board, backtest, and sleeper scripts.

Everything here is standard library only. The design rules that every
consumer relies on:

* Missing values stay ``None``. They are never coerced to zero; weighted
  scores are renormalized over the metrics that are present.
* Player names are joined only through :func:`norm_name`.
* Multi-team seasons keep the ``2TM``/``3TM`` aggregate row, and impossible
  share values (a season target share above ``MAX_TARGET_SHARE``) become
  missing instead of poisoning percentiles.
"""

import csv
import math
import re
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WR_DIR = REPO_ROOT / "wr"
PROPS_DIR = REPO_ROOT / "props"
NAME_ALIASES = {
    "cameronskattebo": "camskattebo",
    "cameronward": "camward",
    "chigoziemokonkwo": "chigokonkwo",
    "jakeferguson20262027markets": "jakeferguson",
}

# Columns that describe 2025 outcomes inside the 2024 feature file. They are
# join/evaluation data and must never be read as model features.
LEAKAGE_COLUMNS = frozenset({"PPR_Points_2025", "rank"})

# A single receiver cannot see more than half of his team's season targets;
# larger values are merge artifacts (e.g. a 3TM row holding 100).
MAX_TARGET_SHARE = 50.0
MAX_AIR_SHARE = 60.0


def norm_name(value):
    """Lowercase ASCII letters and digits only, with suffixes dropped."""
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    value = re.sub(r"\([^)]*\)", "", value.lower())
    value = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", value)
    key = re.sub(r"[^a-z0-9]", "", value)
    return NAME_ALIASES.get(key, key)


def number(value):
    """Parse a CSV cell to float; blank or unparseable cells become None."""
    value = str(value if value is not None else "").strip().replace(",", "").rstrip("%")
    try:
        return float(value)
    except ValueError:
        return None


def read_rows(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def dedupe_players(rows, name_field="Player", team_field="Team"):
    """Collapse multi-team split rows into one row per player.

    Traded players appear once per team plus an aggregate ``2TM``/``3TM``
    row; the aggregate row wins because it holds full-season totals. Returns
    ``(deduped_rows, report)`` where the report maps each duplicated
    normalized name to the list of team labels that were seen.
    """
    by_key = {}
    report = {}
    for row in rows:
        key = norm_name(row.get(name_field, ""))
        if not key:
            continue
        if key in by_key:
            report.setdefault(key, [by_key[key].get(team_field, "")]).append(
                row.get(team_field, "")
            )
            if "TM" in str(row.get(team_field, "")):
                by_key[key] = row
        else:
            by_key[key] = row
    return list(by_key.values()), report


def clean_share(value, cap):
    """Return the share value, or None when it is missing or impossible."""
    return value if value is not None and 0 <= value <= cap else None


def percentile(values, value):
    """Midrank empirical percentile from 0 to 100; None stays None."""
    clean = sorted(v for v in values if v is not None and math.isfinite(v))
    if value is None or not clean:
        return None
    below = sum(v < value for v in clean)
    equal = sum(v == value for v in clean)
    return 100 * (below + 0.5 * equal) / len(clean)


def weighted(values):
    """Weighted mean over (value, weight) pairs, renormalized over the
    weights whose values are present. All values missing -> None."""
    present = [(value, weight) for value, weight in values if value is not None]
    total = sum(weight for _, weight in present)
    if not present or total <= 0:
        return None
    return sum(value * weight for value, weight in present) / total


def check_weights(category_weights, metrics):
    """Raise ValueError unless every weight is non-negative and each level
    sums to 1 within tolerance."""
    def _check(pairs, label):
        weights = [w for _, w in pairs]
        if any(w < 0 for w in weights):
            raise ValueError(f"negative weight in {label}")
        if abs(sum(weights) - 1) > 1e-6:
            raise ValueError(f"{label} weights sum to {sum(weights)}, expected 1")

    _check(list(category_weights.items()), "category")
    for category, items in metrics.items():
        _check(items, f"metric group '{category}'")


def score_players(candidates, metrics, category_weights, games_field,
                  shrink_categories=(), full_season_games=12,
                  neutral_categories=()):
    """Score rows in place with the percentile-composite model.

    * Each metric becomes a percentile among ``candidates`` (``pct_<metric>``).
    * Each category score is the weighted mean of its present percentiles.
    * Categories in ``shrink_categories`` are pulled toward 50 for small
      samples (games / full_season_games), because season-share denominators
      punish players who missed time.
    * Categories in ``neutral_categories`` score 50 when absent: no market
      line means unknown, not bad.
    """
    check_weights(category_weights, metrics)
    for category, items in metrics.items():
        for metric, _ in items:
            vals = [row.get(metric) for row in candidates]
            for row in candidates:
                row[f"pct_{metric}"] = percentile(vals, row.get(metric))

    for row in candidates:
        for category, items in metrics.items():
            row[f"{category}_score"] = weighted(
                [(row.get(f"pct_{metric}"), weight) for metric, weight in items]
            )
        games_factor = min((row.get(games_field) or 0) / full_season_games, 1)
        for category in shrink_categories:
            score = row.get(f"{category}_score")
            if score is not None:
                row[f"{category}_score"] = 50 + games_factor * (score - 50)
        for category in neutral_categories:
            if row.get(f"{category}_score") is None:
                row[f"{category}_score"] = 50.0
        row["model_score"] = weighted([
            (row.get(f"{category}_score"), weight)
            for category, weight in category_weights.items()
        ])
    return candidates


def average_ranks(values):
    """1-based ranks with ties sharing their average rank (ascending)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(xs, ys):
    """Spearman rank correlation with average-tie handling."""
    if len(xs) != len(ys) or len(xs) < 2:
        raise ValueError("need two equal-length sequences of length >= 2")
    rx, ry = average_ranks(xs), average_ranks(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    vy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if vx == 0 or vy == 0:
        return 0.0
    return cov / (vx * vy)


def rank_by(rows, key_fn):
    """Map row id -> 1-based rank, best (largest key) first, ties broken by
    normalized name so ordering is deterministic."""
    ordered = sorted(rows, key=lambda r: (-key_fn(r), norm_name(r.get("Player", ""))))
    return {id(row): rank for rank, row in enumerate(ordered, 1)}


def evaluate_ranking(pairs):
    """Backtest metrics for (predicted_score, actual_outcome) pairs.

    Returns spearman, mean absolute rank error, and top-12/24/36 hit rates
    (share of the actual top-K that the predicted top-K captured).
    """
    if len(pairs) < 2:
        raise ValueError("need at least two players to evaluate")
    scores = [p for p, _ in pairs]
    actual = [a for _, a in pairs]
    n = len(pairs)
    pred_rank = [n + 1 - r for r in average_ranks(scores)]
    act_rank = [n + 1 - r for r in average_ranks(actual)]
    result = {
        "n": n,
        "spearman": spearman(scores, actual),
        "rank_mae": sum(abs(p - a) for p, a in zip(pred_rank, act_rank)) / n,
    }
    for k in (12, 24, 36):
        pred_top = {i for i in range(n) if pred_rank[i] <= k}
        act_top = {i for i in range(n) if act_rank[i] <= k}
        result[f"top{k}_hits"] = len(pred_top & act_top)
        result[f"top{k}_accuracy"] = len(pred_top & act_top) / min(k, n)
    return result


def match_report(left_rows, right_rows, name_field="Player"):
    """Names present on only one side of a join, after normalization."""
    left = {norm_name(r.get(name_field, "")) for r in left_rows}
    right = {norm_name(r.get(name_field, "")) for r in right_rows}
    return sorted(left - right), sorted(right - left)
