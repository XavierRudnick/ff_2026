#!/usr/bin/env python3
"""Build the top-36 receiving-yards market board with reception projections."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "wr" / "wr_stats_act_pred_2025.csv"
OUTPUT = ROOT / "wr" / "wr_top36_by_rec_yds_2026.csv"
TOP_N = 36
SEASON_GAMES = 17


# Manual estimates are only used when the source has no 2026 reception line.
# They combine the receiving-yards line, recent catch/YPR history, availability,
# and material 2026 team or role changes.
MANUAL_PROJECTIONS: dict[str, tuple[int, str]] = {
    "aj brown": (
        80,
        "Manual: 78 catches in 15 games in 2025 and 67 in 13 in 2024; his "
        "trade to New England makes him a lead target for Drake Maye. The "
        "1,108.5-yard line and 13.9 weighted two-year YPR imply about 80 catches.",
    ),
    "drake london": (
        84,
        "Manual: 68 catches in 12 games in 2025 and 100 in 17 in 2024. A "
        "1,106.5-yard line at his 13.3 weighted two-year YPR implies 84 catches; "
        "the new Kevin Stefanski/Tommy Rees offense keeps some scheme uncertainty.",
    ),
    "nico collins": (
        70,
        "Manual: 71 catches in 15 games in 2025 and 68 in 12 in 2024. He remains "
        "C.J. Stroud's primary outside receiver, while the 1,073.5-yard line at "
        "his high 15.4 weighted two-year YPR implies about 70 catches.",
    ),
    "devonta smith": (
        82,
        "Manual: 77 catches in 17 games in 2025 and 68 in 13 in 2024. A.J. "
        "Brown's departure opens targets, so the 1,025.5-yard line's 80-catch "
        "YPR baseline is raised slightly in Sean Mannion's new offense.",
    ),
    "chris olave": (
        86,
        "Manual: 100 catches in 16 games in 2025 after 32 in eight injury-shortened "
        "2024 games. The 1,021-yard line and 11.9 weighted two-year YPR imply "
        "86 catches; rookie Jordyn Tyson adds target competition.",
    ),
    "george pickens": (
        68,
        "Manual: 93 catches in 17 games in 2025 versus 59 in 14 in 2024. He "
        "returns to Dallas on the franchise tag beside CeeDee Lamb; his 15.3 "
        "weighted YPR turns the 1,012.5-yard line into a high-60s catch estimate.",
    ),
    "garrett wilson": (
        90,
        "Manual: 36 catches in seven games before a 2025 knee injury and 101 in "
        "17 games in 2024. A healthy return with Geno Smith and Frank Reich plus "
        "the 996-yard line at 11.0 weighted YPR supports about 90 catches.",
    ),
    "Trey McBride": (
        100,
        "Manual: 126 catches in 17 games in 2025 after 111 in 16 in 2024. He "
        "remains Arizona's short-area centerpiece, but the 985.5-yard line and "
        "new offensive staff pull the estimate back to 100.",
    ),
    "zay flowers": (
        74,
        "Manual: catches rose from 74 in 2024 to 86 in 2025, both over 17 games. "
        "The 979.5-yard line implies 69 at his recent YPR, while a more aggressive "
        "first-down passing plan under the new Ravens staff supports 74.",
    ),
    "Tetairoa McMillan": (
        67,
        "Manual: 70 catches for 1,014 yards in his 17-game rookie season. The "
        "939.5-yard line implies 65 at that YPR; continuity with Bryce Young but "
        "a new play-caller leads to a near-baseline 67.",
    ),
    "terry mclaurin": (
        64,
        "Manual: 38 catches in 10 injury-affected games in 2025 after 82 in 17 "
        "in 2024. The 929.5-yard line at 14.7 weighted YPR implies 63-64, and "
        "Washington has a new coordinator with greater run emphasis.",
    ),
    "Emeka Egbuka": (
        66,
        "Manual: 63 catches for 938 yards across 17 games as a rookie. Mike "
        "Evans' move to San Francisco opens targets, but Tampa Bay still has a "
        "deep receiver room; 66 balances that role gain with the 903-yard line.",
    ),
    "jameson williams": (
        54,
        "Manual: 65 catches in 17 games in 2025 and 58 in 15 in 2024, with an "
        "explosive 17.2 weighted YPR. The 898.5-yard line therefore implies only "
        "52 catches; 54 allows a modest role gain under Detroit's new coordinator.",
    ),
    "Brock Bowers": (
        85,
        "Manual: 64 catches in 12 games in 2025 after 112 in 17 as a rookie in "
        "2024. The 897.5-yard line at roughly 10.6 recent YPR supports 85 catches, "
        "with extra uncertainty from Las Vegas' coaching and quarterback reset.",
    ),
    "jaylen waddle": (
        67,
        "Manual: 64 catches in 16 games in 2025 and 58 in 15 in 2024. His trade "
        "to Denver improves the quarterback setting but adds a target split with "
        "Courtland Sutton; the 885.5-yard line supports a high-60s estimate.",
    ),
    "tee higgins": (
        64,
        "Manual: 59 catches in 15 games in 2025 after 73 in 12 in 2024. "
        "Cincinnati's Burrow-Chase-Higgins core is stable, and the 875.5-yard "
        "line at 13.7 weighted YPR implies 64 catches.",
    ),
    "ladd mcconkey": (
        72,
        "Manual: 66 catches in 16 games in 2025 after 82 in 16 in 2024. The "
        "869-yard line implies 69 at his recent YPR, while Mike McDaniel's new "
        "quick-game offense provides a modest reception-volume boost.",
    ),
    "Luther Burden III": (
        63,
        "Manual: 47 catches for 652 yards in 15 games as a rookie. D.J. Moore's "
        "trade opens second-year targets, though Rome Odunze and Colston Loveland "
        "remain; the 835.5-yard line supports a low-60s estimate.",
    ),
    "dk metcalf": (
        57,
        "Manual: 59 catches in 15 games in 2025 and 66 in 15 in 2024. His 14.6 "
        "weighted YPR makes the 825-yard line worth about 57 catches, while "
        "Michael Pittman Jr.'s arrival prevents a large target-share increase.",
    ),
    "marvin harrison": (
        57,
        "Manual: 41 catches in 12 games in 2025 after 62 in 17 in 2024. The "
        "823-yard line at 14.7 weighted YPR implies 56; a new Arizona scheme is "
        "offset by target competition from Trey McBride and Michael Wilson.",
    ),
    "rome odunze": (
        58,
        "Manual: 44 catches in 12 games in 2025 and 54 in 17 in 2024. D.J. "
        "Moore's departure expands his role, lifting the 55-catch YPR baseline "
        "from the 796-yard line to 58 despite Chicago's other young pass catchers.",
    ),
    "davante adams": (
        61,
        "Manual: 60 catches in 14 games in 2025 after 85 in 14 in 2024. He "
        "returns to Matthew Stafford and Sean McVay but remains behind Puka Nacua; "
        "the 790.5-yard line at 12.9 weighted YPR directly implies 61.",
    ),
    "Colston Loveland": (
        65,
        "Manual: 58 catches for 713 yards in 16 games as a rookie. D.J. Moore's "
        "departure opens underneath targets, and the 789.5-yard line at his "
        "12.3 YPR implies 64; a small second-year bump gives 65.",
    ),
    "josh downs": (
        75,
        "Manual: 58 catches in 16 games in 2025 after 72 in 14 in 2024. Michael "
        "Pittman Jr.'s departure opens targets; the 787-yard line implies 77 at "
        "recent YPR, trimmed to 75 for Indianapolis' quarterback uncertainty.",
    ),
    "Carnell Tate": (
        54,
        "Manual: roughly 48 catches for 838 yards in his final Ohio State season. "
        "Tennessee drafted him fourth overall for an immediate lead role; the "
        "785-yard line at a conservative rookie outside-WR YPR implies about 54.",
    ),
    "courtland sutton": (
        58,
        "Manual: 74 catches in 17 games in 2025 and 81 in 17 in 2024. Jaylen "
        "Waddle's arrival reduces Sutton's target share, and the 778-yard line at "
        "13.6 weighted YPR implies about 57-58 catches.",
    ),
    "christian watson": (
        44,
        "Manual: 35 catches in 10 games in 2025 after 29 in 15 in 2024. His "
        "18.8 weighted YPR makes the 770.5-yard line worth only 41 catches; a "
        "healthier season and expanded route tree raise the estimate to 44.",
    ),
    "Jordyn Tyson": (
        58,
        "Manual: 61 catches for 711 yards in nine games in his final Arizona "
        "State season. New Orleans drafted him eighth overall to play beside "
        "Chris Olave; the 761.5-yard line at a projected NFL YPR supports 58.",
    ),
}


def number(value: str) -> float | None:
    value = (value or "").strip()
    if not value:
        return None
    return float(value)


def format_number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def expected_ppr(row: dict[str, str]) -> float:
    """Calculate PPR using the market reception line, then our projection."""
    receptions = number(row.get("Bet_Line_Rec", ""))
    if receptions is None:
        receptions = number(row.get("Predicted_Recs", ""))

    receiving_yards = number(row.get("Bet_Line_Rec_Yds", ""))
    receiving_tds = number(row.get("Bet_Line_Rec_TD", ""))
    if receiving_tds is None:
        prior_tds = number(row.get("RTD_2025", ""))
        prior_games = number(row.get("G_2025", ""))
        if prior_tds is not None and prior_games is not None and prior_games > 0:
            receiving_tds = prior_tds / prior_games * SEASON_GAMES

    if receptions is None or receiving_yards is None or receiving_tds is None:
        raise ValueError(
            f"Insufficient expected-PPR inputs for {row.get('Player')!r}"
        )
    return receptions + receiving_yards / 10 + receiving_tds * 6


def build() -> list[dict[str, str]]:
    with INPUT.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    rows.sort(
        key=lambda row: number(row.get("Bet_Line_Rec_Yds", "")) or float("-inf"),
        reverse=True,
    )
    rows = rows[:TOP_N]

    for row in rows:
        reception_line = number(row.get("Bet_Line_Rec", ""))
        if reception_line is not None:
            row["Predicted_Recs"] = row["Bet_Line_Rec"]
            row["Reasoning_Why"] = (
                f"Market-based: the existing 2026 reception line of "
                f"{row['Bet_Line_Rec']} is used directly; no manual substitute "
                f"is needed."
            )
            continue

        try:
            projection, reason = MANUAL_PROJECTIONS[row["Player"]]
        except KeyError as exc:
            raise ValueError(
                f"Missing manual reception projection for {row['Player']!r}"
            ) from exc
        row["Predicted_Recs"] = str(projection)
        row["Reasoning_Why"] = reason

    for row in rows:
        row["Expected_Fantasy_Points_PPR"] = format_number(expected_ppr(row))

    missing = [
        row["Player"]
        for row in rows
        if not row.get("Predicted_Recs") or not row.get("Reasoning_Why")
    ]
    if missing:
        raise ValueError(f"Incomplete projections: {missing}")

    output_fields = fieldnames + ["Predicted_Recs", "Reasoning_Why"]
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    result = build()
    manual_count = sum(not row.get("Bet_Line_Rec") for row in result)
    print(f"Wrote {len(result)} rows to {OUTPUT}")
    print(f"Used {len(result) - manual_count} reception lines and {manual_count} manual projections")
