#!/usr/bin/env python3
"""Build the 2026 RB projection board for players with a rushing-yards line.

For each requested category, an existing prop line is used as the projection.
When that category has no prop, the fallback below uses 2024-25 production,
2026 team/depth-chart context, role, age, and injury information.
"""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "rbs" / "rb_stats_act_pred_2025.csv"
BOARD_OUTPUT = ROOT / "rbs" / "rb_2026_rush_line_projections.csv"


# rec, rec_yds, rec_td, and rush_td are fallbacks used only when the matching
# Bet_Line_* field is blank in the source CSV.
PROJECTIONS = {
    "jonathan taylor": {
        "team": "IND",
        "rec": 49,
        "rec_yds": 330,
        "rec_td": 1.5,
        "rush_td": 11,
        "reason": (
            "Receiving jumped to 46-378 in 2025 from 18-136 in 2024; project "
            "partial regression, not a full reversal, with Daniel Jones expected "
            "back for Week 1."
        ),
    },
    "derrick henry": {
        "team": "BAL",
        "rec": 18,
        "rec_yds": 172,
        "rec_td": 0.5,
        "rush_td": 12,
        "reason": (
            "Receiving remained tiny at 15-150 after 19-193; Baltimore still "
            "uses him as a featured rusher and goal-line back, not a pass-game option."
        ),
    },
    "james cook": {
        "team": "BUF",
        "rec": 33,
        "rec_yds": 282,
        "rec_td": 1.5,
        "rush_td": 10,
        "reason": (
            "Receiving held near 32-33 catches in consecutive seasons; the same "
            "Joe Brady/Josh Allen structure supports rushing efficiency but caps targets."
        ),
    },
    "jahmyr gibbs": {
        "team": "DET",
        "rec": 61,
        "rec_yds": 570,
        "rec_td": 3,
        "rush_td": 12,
        "reason": (
            "Receptions rose from 52 to 77; David Montgomery's exit expands the "
            "touch ceiling, though new backup Isiah Pacheco should absorb some early-down work."
        ),
    },
    "bijan robinson": {
        "team": "ATL",
        "rec": 68,
        "rec_yds": 568,
        "rec_td": 3,
        "rush_td": 9,
        "reason": (
            "He followed 61-431 with 79-820 and remains an elite three-down back; "
            "Kevin Stefanski is the new coach, while the receiving-yard market tempers "
            "a straight-line repeat of 2025."
        ),
    },
    "saquon barkley": {
        "team": "PHI",
        "rec": 35,
        "rec_yds": 260,
        "rec_td": 2,
        "rush_td": 7,
        "reason": (
            "His last two receiving lines were stable at 33-278 and 37-273; a "
            "healthier line and new playcaller Sean Mannion help the offense without "
            "materially changing Barkley's target role."
        ),
    },
    "devon achane": {
        "team": "MIA",
        "rec": 58,
        "rec_yds": 400.5,
        "rec_td": 3.5,
        "rush_td": 5,
        "reason": (
            "He posted 67-488 after 78-592; new QB Malik Willis adds passing-volume "
            "uncertainty, but minimal backfield competition keeps Achane central to the offense."
        ),
    },
    "kyren williams": {
        "team": "LAR",
        "rec": 35,
        "rec_yds": 235,
        "rec_td": 1.5,
        "rush_td": 10,
        "reason": (
            "He has stayed in the 34-36 catch range, and Blake Corum remains the "
            "backup; the stable role and elite Rams offense support similar receiving usage."
        ),
    },
    "ashton jeanty": {
        "team": "LVR",
        "rec": 50,
        "rec_yds": 350.5,
        "rec_td": 3,
        "rush_td": 7,
        "reason": (
            "The rookie line was 55-346; new coach Klint Kubiak, a healthier line, "
            "and new QB Fernando Mendoza improve the environment while Jeanty retains "
            "a clean path to heavy volume."
        ),
    },
    "kenneth walker": {
        "team": "KAN",
        "rec": 42,
        "rec_yds": 255,
        "rec_td": 1.5,
        "rush_td": 7,
        "reason": (
            "He moves from Seattle to an Andy Reid-led Kansas City offense after "
            "31-282 in 2025 and 46-299 in 2024; the reception market limits the catch "
            "projection despite an improved scoring setting."
        ),
    },
    "christian mccaffrey": {
        "team": "SFO",
        "rec": 68,
        "rec_yds": 564.5,
        "rec_td": 4,
        "rush_td": 8,
        "reason": (
            "He rebounded to 102-924 after an injury-shortened 15-146 season; age "
            "30 and 450 touches including playoffs call for regression, but Kyle "
            "Shanahan's usage preserves a high receiving floor."
        ),
    },
    "javonte williams": {
        "team": "DAL",
        "rec": 36,
        "rec_yds": 220,
        "rec_td": 1.5,
        "rush_td": 9,
        "reason": (
            "He re-signed with Dallas and has little touch competition, but 35-137 "
            "in 2025 and a league-low 2.7 yards per target argue for only modest "
            "receiving efficiency."
        ),
    },
    "omarion hampton": {
        "team": "LAC",
        "rec": 52,
        "rec_yds": 375,
        "rec_td": 2,
        "rush_td": 8,
        "reason": (
            "He managed 32-192 in only nine rookie games; Mike McDaniel replacing "
            "Greg Roman should raise targets, and both starting tackles return healthy."
        ),
    },
    "breece hall": {
        "team": "NYJ",
        "rec": 44,
        "rec_yds": 325.5,
        "rec_td": 2,
        "rush_td": 5,
        "reason": (
            "Receiving fell to 36-350 from 57-483; the franchise-tagged back can "
            "rebound with pocket passer Geno Smith, though the Jets offense still caps upside."
        ),
    },
    "jeremiyah love": {
        "team": "ARI",
        "rec": 41,
        "rec_yds": 317,
        "rec_td": 2,
        "rush_td": 6,
        "reason": (
            "The No. 3 overall rookie has a clear path to lead work in Arizona, but "
            "Tyler Allgeier can take early-down and goal-line touches; use a strong "
            "but not full-workhorse first-year receiving projection."
        ),
    },
    "quinshon judkins": {
        "team": "CLE",
        "rec": 35,
        "rec_yds": 250,
        "rec_td": 1,
        "rush_td": 6,
        "reason": (
            "He had 26-171 in 14 games and only 2.6 targets per game; a large carry "
            "role remains, but leg rehab, new coach Todd Monken, and QB uncertainty "
            "limit the receiving ceiling."
        ),
    },
    "chase brown": {
        "team": "CIN",
        "rec": 64,
        "rec_yds": 475,
        "rec_td": 4,
        "rush_td": 6,
        "reason": (
            "He improved from 54-360 to 69-437; a healthy Joe Burrow and minimal "
            "backfield competition sustain the catch floor, with mild regression from five rec TDs."
        ),
    },
    "david montgomery": {
        "team": "HOU",
        "rec": 26,
        "rec_yds": 205,
        "rec_td": 1,
        "rush_td": 7,
        "reason": (
            "Receiving declined from 36-341 to 24-192; after the trade to Houston, "
            "Woody Marks should retain passing-down work, keeping Montgomery touchdown-dependent."
        ),
    },
    "cam skattebo": {
        "team": "NYG",
        "rec": 38,
        "rec_yds": 275.5,
        "rec_td": 2,
        "rush_td": 6,
        "reason": (
            "He produced 24-207 in eight rookie games; a full-season role is viable "
            "with the same backfield competition, but ankle recovery and new coaches "
            "John Harbaugh and Matt Nagy add uncertainty."
        ),
    },
    "chuba hubbard": {
        "team": "CAR",
        "rec": 40,
        "rec_yds": 275,
        "rec_td": 2,
        "rush_td": 4,
        "reason": (
            "He followed 43-171 with 30-223 in an injury-hit season; Rico Dowdle's "
            "departure restores opportunity, though Jonathon Brooks and Trevor Etienne "
            "will still take touches."
        ),
    },
    "bucky irving": {
        "team": "TAM",
        "rec": 43,
        "rec_yds": 385,
        "rec_td": 2.5,
        "rush_td": 5,
        "reason": (
            "He posted 30-277 in 10 games after 47-392 as a rookie; Kenneth "
            "Gainwell's arrival can siphon passing downs, and 2025 durability and "
            "efficiency issues lower the ceiling."
        ),
    },
    "travis etienne": {
        "team": "NOR",
        "rec": 40,
        "rec_yds": 285,
        "rec_td": 2,
        "rush_td": 5,
        "reason": (
            "After 39-254 and 36-292, he moves to New Orleans with a feature-back "
            "path if Alvin Kamara departs; four straight 35-catch seasons support the market line."
        ),
    },
    "tony pollard": {
        "team": "TEN",
        "rec": 34,
        "rec_yds": 215,
        "rec_td": 0.8,
        "rush_td": 5,
        "reason": (
            "Receiving slipped from 41-238 to 33-206 as Tyjae Spears took passing "
            "work; modest Cam Ward growth helps the offense, but the role remains capped."
        ),
    },
    "dandre swift": {
        "team": "CHI",
        "rec": 40,
        "rec_yds": 315,
        "rec_td": 1.5,
        "rush_td": 6,
        "reason": (
            "He followed 42-386 with 34-299; Kyle Monangai should command more "
            "committee work in Year 2, while Swift retains the primary receiving role."
        ),
    },
    "jadarian price": {
        "team": "SEA",
        "rec": 27,
        "rec_yds": 182,
        "rec_td": 1.5,
        "rush_td": 6,
        "reason": (
            "The first-round rookie has a path after Kenneth Walker left and Zach "
            "Charbonnet tore his ACL, but Seattle may ease him in with George Holani "
            "and Emanuel Wilson; his college role was not a workhorse role."
        ),
    },
    "rico dowdle": {
        "team": "PIT",
        "rec": 32,
        "rec_yds": 230,
        "rec_td": 1,
        "rush_td": 4,
        "reason": (
            "He caught 39 passes in each of the past two seasons, but the move to "
            "Pittsburgh creates a split with Jaylen Warren and Kaleb Johnson in a "
            "Mike McCarthy offense that rarely targets backs."
        ),
    },
    "bhayshul tuten": {
        "team": "JAX",
        "rec": 30,
        "rec_yds": 210,
        "rec_td": 1.2,
        "rush_td": 5,
        "reason": (
            "He had 10-79 in a limited rookie role; Travis Etienne's exit opens lead "
            "work, but LeQuint Allen profiles as the receiving specialist and Chris "
            "Rodriguez joins the committee."
        ),
    },
    "treveyon henderson": {
        "team": "NWE",
        "rec": 42,
        "rec_yds": 325,
        "rec_td": 2,
        "rush_td": 5,
        "reason": (
            "He posted 35-221 as a rookie and should earn more work after an "
            "efficient debut, but Rhamondre Stevenson remains a meaningful committee partner."
        ),
    },
    "jk dobbins": {
        "team": "DEN",
        "rec": 21,
        "rec_yds": 145,
        "rec_td": 0.5,
        "rush_td": 5,
        "reason": (
            "He managed 11-37 in 10 games and re-signed with Denver; RJ Harvey "
            "already drew more targets and can take the lead role, while Dobbins' "
            "durability remains a major discount."
        ),
    },
    "blake corum": {
        "team": "LAR",
        "rec": 13,
        "rec_yds": 95,
        "rec_td": 0.3,
        "rush_td": 6,
        "reason": (
            "Receiving stayed negligible at 7-58 and 8-36; he remains Kyren "
            "Williams' backup after a 29% snap share, making him an insurance back "
            "rather than a weekly pass-game option."
        ),
    },
    "jordan mason": {
        "team": "MIN",
        "rec": 16,
        "rec_yds": 115,
        "rec_td": 0.5,
        "rush_td": 5,
        "reason": (
            "He followed 11-91 with 14-51; Aaron Jones remains the starter and "
            "Mason's role is still tilted toward early-down rushing."
        ),
    },
    "kyle monangai": {
        "team": "CHI",
        "rec": 26,
        "rec_yds": 180,
        "rec_td": 1,
        "rush_td": 5,
        "reason": (
            "The rookie line was 18-164 and his usage should grow, but D'Andre "
            "Swift remains healthy and controls most passing-down work."
        ),
    },
    "jaylen warren": {
        "team": "PIT",
        "rec": 39,
        "rec_yds": 290,
        "rec_td": 1.5,
        "rush_td": 6,
        "reason": (
            "He followed 38-310 with 40-333, but Rico Dowdle joins the committee "
            "and Mike McCarthy rarely features RB targets; the rush-TD estimate holds "
            "near 2025 rather than extrapolating the breakout."
        ),
    },
    "rhamondre stevenson": {
        "team": "NWE",
        "rec": 31,
        "rec_yds": 250,
        "rec_td": 1,
        "rush_td": 6,
        "reason": (
            "He posted 32-345 after 33-168, but the yards-per-target spike should "
            "regress and TreVeyon Henderson is likely to take a larger Year 2 role."
        ),
    },
    "aaron jones": {
        "team": "MIN",
        "rec": 35,
        "rec_yds": 275,
        "rec_td": 1.5,
        "rush_td": 5,
        "reason": (
            "An injury-hit age-31 season produced 28-199 after 51-408; declining "
            "elusiveness and Jordan Mason's committee presence warrant a reduced "
            "full-season projection."
        ),
    },
    "jacory croskey-merritt": {
        "team": "WAS",
        "rec": 19,
        "rec_yds": 130,
        "rec_td": 0.5,
        "rush_td": 4,
        "reason": (
            "He had only 9-68 as a rookie; additions Rachaad White and Jerome Ford "
            "reduce passing-down access, so both receiving and TD projections remain modest."
        ),
    },
    "isiah pacheco": {
        "team": "DET",
        "rec": 18,
        "rec_yds": 140,
        "rec_td": 0.8,
        "rush_td": 4,
        "reason": (
            "After injury-limited lines of 12-79 and 19-101, he moves to Detroit as "
            "Jahmyr Gibbs' change-of-pace back; replacing Montgomery offers some TD "
            "chances but little standalone passing work."
        ),
    },
}


NEW_FIELDS = [
    "Team_2026",
    "Predicted_RECs_2026",
    "Predicted_Rec_Yards_2026",
    "Predicted_Rec_TDs_2026",
    "Predicted_Rush_TDs_2026",
    "Calculated_Expected_Points_PPR_2026",
    "Prediction_Reasoning_2026",
]


def compact_number(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def line_or_fallback(row: dict[str, str], column: str, fallback: object) -> str:
    line = row[column].strip()
    return line if line else compact_number(fallback)


def market_anchor_text(row: dict[str, str]) -> str:
    labels = (
        ("Bet_Line_Rec", "receptions"),
        ("Bet_Line_Rec_Yds", "receiving yards"),
        ("Bet_Line_Rec_TD", "receiving TDs"),
        ("Bet_Line_Rush_TD", "rushing TDs"),
    )
    anchors = [
        f"{label}={row[column].strip()}"
        for column, label in labels
        if row[column].strip()
    ]
    if not anchors:
        return "No category-specific market anchors; all four fields are modeled."
    return "Market anchors used: " + ", ".join(anchors) + "."


def calculated_ppr_points(row: dict[str, str]) -> str:
    """Score the line-first, prediction-second 2026 stat combination."""
    rushing_yards = float(row["Bet_Line_Rush_Yds"])
    rushing_tds = float(row["Predicted_Rush_TDs_2026"])
    receptions = float(row["Predicted_RECs_2026"])
    receiving_yards = float(row["Predicted_Rec_Yards_2026"])
    receiving_tds = float(row["Predicted_Rec_TDs_2026"])
    points = (
        rushing_yards * 0.1
        + rushing_tds * 6
        + receptions
        + receiving_yards * 0.1
        + receiving_tds * 6
    )
    return f"{points:.2f}"


def main() -> None:
    with INPUT.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        original_fields = [
            field for field in (reader.fieldnames or []) if field not in NEW_FIELDS
        ]
        all_rows = list(reader)

    rows = [
        row for row in all_rows if row.get("Bet_Line_Rush_Yds", "").strip()
    ]
    rows_without_rush_line = [
        row for row in all_rows if not row.get("Bet_Line_Rush_Yds", "").strip()
    ]
    rows.sort(key=lambda row: float(row["Bet_Line_Rush_Yds"]), reverse=True)

    source_players = {row["Player"].strip().casefold() for row in rows}
    configured_players = set(PROJECTIONS)
    missing = source_players - configured_players
    extra = configured_players - source_players
    if missing or extra:
        raise ValueError(
            f"Projection map mismatch. Missing={sorted(missing)} Extra={sorted(extra)}"
        )

    for row in rows:
        key = row["Player"].strip().casefold()
        projection = PROJECTIONS[key]
        row["Team_2026"] = str(projection["team"])
        row["Predicted_RECs_2026"] = line_or_fallback(
            row, "Bet_Line_Rec", projection["rec"]
        )
        row["Predicted_Rec_Yards_2026"] = line_or_fallback(
            row, "Bet_Line_Rec_Yds", projection["rec_yds"]
        )
        row["Predicted_Rec_TDs_2026"] = line_or_fallback(
            row, "Bet_Line_Rec_TD", projection["rec_td"]
        )
        row["Predicted_Rush_TDs_2026"] = line_or_fallback(
            row, "Bet_Line_Rush_TD", projection["rush_td"]
        )
        row["Calculated_Expected_Points_PPR_2026"] = calculated_ppr_points(row)
        row["Prediction_Reasoning_2026"] = (
            f"{market_anchor_text(row)} {projection['reason']}"
        )

    for row in rows_without_rush_line:
        for field in NEW_FIELDS:
            row[field] = ""

    fieldnames = original_fields + NEW_FIELDS
    source_temp = INPUT.with_suffix(".csv.tmp")
    with source_temp.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows + rows_without_rush_line)
    source_temp.replace(INPUT)

    with BOARD_OUTPUT.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Updated {INPUT} with {len(rows)} projected rows and "
        f"{len(rows_without_rush_line)} retained rows"
    )
    print(f"Wrote {len(rows)} sorted rows to {BOARD_OUTPUT}")


if __name__ == "__main__":
    main()
