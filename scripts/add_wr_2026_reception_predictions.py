#!/usr/bin/env python3
"""Add researched 2026 reception estimates and sort the actual/predicted file."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "wr" / "wr_stats_act_pred_2025.csv"


# These are reception estimates, not sportsbook lines. The accompanying notes
# supply the 2026 role adjustment; build_reason() adds each player's recent
# catches, games, and market-implied catches at recent yards per reception.
PROJECTIONS: dict[str, tuple[int, str]] = {
    "brian thomas": (
        49,
        "Jacksonville added Jakobi Meyers, so the estimate stays near the "
        "yardage/YPR baseline rather than assuming a full target-share rebound.",
    ),
    "nico collins": (
        70,
        "He remains Houston's primary outside target, with Jayden Higgins and "
        "the returning receiver group limiting the need for a volume bump.",
    ),
    "aj brown": (
        80,
        "His trade to New England makes him a featured target for Drake Maye, "
        "although Romeo Doubs and Hunter Henry keep the projection below a "
        "true one-man passing game.",
    ),
    "drake london": (
        84,
        "Kevin Stefanski and Tommy Rees now run Atlanta's offense; London "
        "remains the lead wideout, but the new scheme adds modest uncertainty.",
    ),
    "ladd mcconkey": (
        70,
        "Mike McDaniel's arrival as Chargers offensive coordinator should add "
        "quick-game opportunities, so the estimate is modestly above the raw "
        "two-year YPR result.",
    ),
    "terry mclaurin": (
        66,
        "Washington promoted David Blough to coordinator and drafted Antonio "
        "Williams, but McLaurin remains the established lead receiver.",
    ),
    "tee higgins": (
        65,
        "Cincinnati's Burrow-Chase-Higgins core is intact, making the recent "
        "YPR baseline the best guide.",
    ),
    "davante adams": (
        62,
        "He remains Matthew Stafford's veteran secondary option behind Puka "
        "Nacua, so no large target-share change is assumed.",
    ),
    "marvin harrison": (
        57,
        "Arizona has a new offensive staff and quarterback uncertainty, while "
        "Trey McBride and Michael Wilson still command meaningful targets.",
    ),
    "dk metcalf": (
        56,
        "Pittsburgh added Michael Pittman Jr. and rookie Germie Bernard under "
        "Mike McCarthy, keeping Metcalf's catch volume close to the line/YPR "
        "baseline.",
    ),
    "garrett wilson": (
        88,
        "A healthy return with Geno Smith and Frank Reich supports strong "
        "volume, but first-rounder Omar Cooper Jr. and Adonai Mitchell add "
        "target competition.",
    ),
    "jaylen waddle": (
        62,
        "His trade to Denver improves the quarterback setting but creates a "
        "target split with Courtland Sutton in Davis Webb's offense.",
    ),
    "jerry jeudy": (
        49,
        "Todd Monken takes over Cleveland, which also added first-rounder K.C. "
        "Concepcion and second-rounder Denzel Boston.",
    ),
    "calvin ridley": (
        38,
        "Brian Daboll now coordinates Tennessee, but fourth-overall pick "
        "Carnell Tate and new slot receiver Wan'Dale Robinson make a major "
        "target rebound unlikely.",
    ),
    "zay flowers": (
        70,
        "Baltimore changed to Jesse Minter and Declan Doyle; Flowers is still "
        "the lead wideout, but the estimate does not assume a major change in "
        "his downfield usage.",
    ),
    "george pickens": (
        67,
        "He returns opposite CeeDee Lamb in Dallas, so his high recent yards "
        "per catch keeps the reception estimate in the upper 60s.",
    ),
    "xavier worthy": (
        50,
        "Eric Bieniemy's return and a crowded Kansas City target tree create "
        "uncertainty; the estimate assumes a somewhat deeper role than his "
        "two-year average.",
    ),
    "jameson williams": (
        53,
        "Drew Petzing is Detroit's new coordinator, but Amon-Ra St. Brown and "
        "Sam LaPorta keep Williams in an explosive, lower-catch role.",
    ),
    "courtland sutton": (
        58,
        "Jaylen Waddle's arrival reduces Sutton's target ceiling even though "
        "Sutton remains a starting outside receiver for Bo Nix.",
    ),
    "devonta smith": (
        81,
        "A.J. Brown's departure opens targets, but Philadelphia also added "
        "Makai Lemon, Marquise Brown, and Dontayvion Wicks to Sean Mannion's "
        "new offense.",
    ),
    "chris olave": (
        84,
        "Eighth-overall pick Jordyn Tyson adds target competition, trimming "
        "Olave slightly from the raw recent-YPR result.",
    ),
    "rome odunze": (
        59,
        "D.J. Moore's trade to Buffalo expands Odunze's role, though Luther "
        "Burden III and Colston Loveland remain prominent young targets.",
    ),
    "jakobi meyers": (
        62,
        "His move to Jacksonville puts him alongside Brian Thomas Jr. and "
        "Parker Washington, favoring a steady intermediate role over a volume "
        "spike.",
    ),
    "khalil shakir": (
        61,
        "Buffalo added D.J. Moore as Josh Allen's lead outside receiver, which "
        "slightly lowers Shakir's short-area volume.",
    ),
    "ricky pearsall": (
        46,
        "San Francisco added Mike Evans, Christian Kirk, and second-rounder "
        "De'Zhaun Stribling, creating a crowded route distribution.",
    ),
    "jordan addison": (
        47,
        "Minnesota added Jauan Jennings, so Addison remains a secondary option "
        "behind Justin Jefferson rather than receiving a large volume bump.",
    ),
    "chris godwin": (
        60,
        "Mike Evans' departure opens routes in Tampa Bay, but Emeka Egbuka is "
        "now the lead receiver and Godwin's recent injuries cap the estimate.",
    ),
    "rashid shaheed": (
        36,
        "His move to Seattle places him behind Jaxon Smith-Njigba and keeps him "
        "in a lower-catch vertical role.",
    ),
    "josh downs": (
        72,
        "Michael Pittman Jr.'s trade opens underneath targets in Indianapolis, "
        "but quarterback uncertainty keeps the estimate below the full raw "
        "YPR implication.",
    ),
    "jayden reed": (
        48,
        "Dontayvion Wicks left Green Bay, but Matthew Golden remains a major "
        "competitor; Reed's short-area and rushing role supports a modest bump.",
    ),
    "quentin johnston": (
        46,
        "Mike McDaniel's new Chargers offense should emphasize Ladd McConkey, "
        "leaving Johnston in a lower-catch outside role.",
    ),
    "wandale robinson": (
        69,
        "His move to Tennessee gives him the primary slot role, but Carnell "
        "Tate and Calvin Ridley prevent a repeat of his 2025 Giants volume.",
    ),
    "rashod bateman": (
        34,
        "Declan Doyle's new Baltimore offense and a thin outside-receiver room "
        "offer some rebound potential, but Bateman remains behind Zay Flowers "
        "and the tight ends.",
    ),
    "michael wilson": (
        57,
        "He remains Arizona's secondary wideout behind Marvin Harrison Jr., "
        "with Trey McBride still the offense's high-volume middle target.",
    ),
    "tre tucker": (
        48,
        "Klint Kubiak and rookie quarterback Fernando Mendoza reset the Raiders "
        "offense, while Brock Bowers, Jack Bech, and Jalen Nailor compete for "
        "targets.",
    ),
    "jalen coker": (
        46,
        "He remains behind Tetairoa McMillan, and third-round rookie Chris "
        "Brazzell adds competition for Carolina's secondary receiver work.",
    ),
    "parker washington": (
        53,
        "Jakobi Meyers' arrival adds competition in Jacksonville, keeping "
        "Washington near the market-adjusted volume baseline.",
    ),
    "christian watson": (
        44,
        "Dontayvion Wicks' departure opens routes, but Watson's health history "
        "and deep average target keep the catch total well below his yardage.",
    ),
    "adonai mitchell": (
        35,
        "His move to the Jets puts him behind Garrett Wilson and first-rounder "
        "Omar Cooper Jr. in Frank Reich's offense.",
    ),
    "Tetairoa McMillan": (
        67,
        "He remains Bryce Young's primary outside receiver; continuity in the "
        "core offense is balanced by added rookie depth behind him.",
    ),
    "Emeka Egbuka": (
        66,
        "Mike Evans' move to San Francisco opens Tampa Bay targets, but Chris "
        "Godwin and the rest of the receiver room prevent an aggressive jump.",
    ),
    "Jayden Higgins": (
        46,
        "He remains a secondary Houston target behind Nico Collins, with Tank "
        "Dell and the tight ends also involved.",
    ),
    "Luther Burden III": (
        63,
        "D.J. Moore's departure opens a larger second-year role, though Rome "
        "Odunze and Colston Loveland remain ahead in Chicago's target tree.",
    ),
    "Matthew Golden": (
        49,
        "Dontayvion Wicks' departure helps, but Green Bay still spreads targets "
        "among Jayden Reed, Christian Watson, and its tight ends.",
    ),
    "Brock Bowers": (
        86,
        "He had 112 catches as a 2024 rookie before an injury-shortened 2025. "
        "Klint Kubiak and rookie quarterback Fernando Mendoza add uncertainty, "
        "but Bowers remains the Raiders' central short-area target.",
    ),
    "Trey McBride": (
        99,
        "He followed 111 catches in 2024 with 126 in 2025. Arizona's new staff "
        "and quarterback uncertainty pull the estimate just below the raw "
        "yardage/YPR result.",
    ),
    "George Kittle": (
        64,
        "Mike Evans, Christian Kirk, and rookie De'Zhaun Stribling add target "
        "competition, while Kittle enters camp with an injury designation.",
    ),
    "T.J. Hockenson": (
        48,
        "Minnesota added Jauan Jennings and still funnels its passing game "
        "through Justin Jefferson; a normalized tight-end YPR lowers the catch "
        "need versus Hockenson's unusually low 2025 YPR.",
    ),
    "Sam LaPorta": (
        55,
        "His 2025 was limited to nine games. A healthier season in Drew "
        "Petzing's new Detroit offense supports a mid-50s total.",
    ),
    "Travis Kelce": (
        64,
        "Eric Bieniemy returns as coordinator, but age and Kansas City's deep "
        "receiver group keep Kelce below his 76 catches from 2025.",
    ),
    "Hunter Henry": (
        43,
        "New England added A.J. Brown and Romeo Doubs, reducing Henry's target "
        "share despite a strong Drake Maye offense.",
    ),
    "Isaiah Likely": (
        54,
        "His move to the Giants removes him from Mark Andrews' shadow; Matt "
        "Nagy's new offense should feature him, with Theo Johnson still sharing "
        "tight-end routes.",
    ),
    "Dallas Goedert": (
        56,
        "A.J. Brown's departure helps, but Philadelphia added three receivers "
        "and rookie tight end Eli Stowers to Sean Mannion's offense.",
    ),
    "Mark Andrews": (
        50,
        "Isaiah Likely's departure restores routes, but a normalized receiving "
        "average under new coordinator Declan Doyle keeps the estimate below "
        "the raw 2025-YPR result.",
    ),
    "Dalton Schultz": (
        50,
        "Houston's passing-game core is stable, while second-round tight end "
        "Marlin Klein adds modest route competition.",
    ),
    "Tucker Kraft": (
        51,
        "Dontayvion Wicks' departure can add targets, but Kraft's injury status "
        "and unsustainably high 2025 yards per catch temper the projection.",
    ),
    "Dalton Kincaid": (
        43,
        "Buffalo added D.J. Moore and changed to coordinator Pete Carmichael "
        "Jr.; Kincaid should be more efficient but still shares work with "
        "Dawson Knox.",
    ),
    "Cade Otton": (
        44,
        "Mike Evans' departure helps, but Emeka Egbuka and Chris Godwin remain "
        "the primary Tampa Bay targets in Zac Robinson's new offense.",
    ),
    "Jake Ferguson": (
        58,
        "Dallas' core offense is stable; the estimate assumes his yards per "
        "catch rebounds from an unusually low 2025 rather than simply dividing "
        "the line by that one season.",
    ),
    "Kyle Pitts": (
        68,
        "Kevin Stefanski and Tommy Rees take over Atlanta, but Drake London "
        "remains the lead target and Pitts' 2025 catch rate is not fully carried "
        "forward.",
    ),
    "Juwan Johnson": (
        50,
        "New Orleans added Jordyn Tyson and rookie tight end Oscar Delp, "
        "limiting Johnson's repeat-volume upside.",
    ),
    "Pat Freiermuth": (
        39,
        "Pittsburgh added Michael Pittman Jr. and Germie Bernard under Mike "
        "McCarthy, leaving Freiermuth as a secondary middle-of-field option.",
    ),
    "Tyler Warren": (
        74,
        "Michael Pittman Jr.'s departure opens short-area targets, partly "
        "offsetting Indianapolis' quarterback uncertainty.",
    ),
    "Harold Fannin Jr.": (
        66,
        "Todd Monken's arrival is encouraging, but Cleveland also added K.C. "
        "Concepcion and Denzel Boston to a target tree that includes Jerry "
        "Jeudy.",
    ),
    "Colston Loveland": (
        65,
        "D.J. Moore's departure opens underneath targets, while Chicago's heavy "
        "multi-tight-end usage and rookie blocker Sam Roush keep Loveland on "
        "the field.",
    ),
    "Chig Okonkwo": (
        44,
        "His move to Washington creates a new role in David Blough's offense, "
        "with Terry McLaurin and rookie Antonio Williams ahead in the target "
        "order.",
    ),
    "Brenton Strange": (
        45,
        "Jacksonville added Jakobi Meyers to a deep receiving group, so Strange "
        "projects as a moderate-volume outlet rather than a featured target.",
    ),
    "Gunnar Helm": (
        43,
        "Tennessee added Carnell Tate and Wan'Dale Robinson in Brian Daboll's "
        "new offense, reducing Helm's target-share ceiling.",
    ),
    "Greg Dulcich": (
        38,
        "His move to Miami gives him a path to routes after Jaylen Waddle's "
        "departure, but his injury history makes a full breakout unsafe.",
    ),
}


ROOKIE_PROJECTIONS: dict[str, tuple[int, str]] = {
    "Carnell Tate": (
        54,
        "He finished at Ohio State with 51 catches for 875 yards in 2025. "
        "Tennessee drafted him fourth overall to become Cam Ward's lead outside "
        "target; 785 yards at a conservative rookie 14.5 YPR is about 54 catches.",
    ),
    "Denzel Boston": (
        38,
        "He posted 62 catches for 881 yards in his final Washington season. "
        "Cleveland drafted him 39th, but K.C. Concepcion, Jerry Jeudy, and Harold "
        "Fannin Jr. limit volume; 492.5 yards at roughly 13 YPR is 38 catches.",
    ),
    "Germie Bernard": (
        34,
        "He led Alabama with 64 catches for 862 yards in 2025. As Pittsburgh's "
        "47th pick he begins behind DK Metcalf and Michael Pittman Jr.; 395.5 "
        "yards at a reduced NFL YPR is about 34 catches.",
    ),
    "Jordyn Tyson": (
        58,
        "He had 61 catches for 711 yards in nine games in 2025 after a 75-catch, "
        "1,101-yard 2024. New Orleans drafted him eighth to start beside Chris "
        "Olave; the 761.5-yard line supports about 58 catches.",
    ),
    "KC Concepcion": (
        48,
        "He produced 61 catches for 919 yards at Texas A&M in 2025. Cleveland "
        "drafted him 24th for a versatile role, but its crowded target tree "
        "keeps 619.5 yards near 48 catches.",
    ),
    "Makai Lemon": (
        51,
        "He won the Biletnikoff after 79 catches for 1,156 yards at USC. "
        "Philadelphia drafted him 20th, but DeVonta Smith and several veteran "
        "additions cap rookie volume; 645.5 yards supports about 51 catches.",
    ),
    "Omar Cooper Jr.": (
        43,
        "He recorded 69 catches for 937 yards for Indiana in 2025. The Jets "
        "traded up to pick 30, but Garrett Wilson remains the clear lead target; "
        "530.5 yards at a shorter NFL YPR is about 43 catches.",
    ),
    "Kenyon Sadiq": (
        40,
        "He broke out for 51 catches and 560 yards at Oregon in 2025. The Jets "
        "drafted him 16th for Frank Reich's offense, but rookie tight ends "
        "usually ramp gradually and Mason Taylor still shares the position.",
    ),
}


def number(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    return float(text)


def count_text(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def build_reason(row: dict[str, str], note: str) -> str:
    seasons: list[str] = []
    total_receptions = 0.0
    total_yards = 0.0

    for year in ("2025", "2024"):
        receptions = number(row.get(f"Rec_{year}"))
        yards = number(row.get(f"Yds_{year}"))
        games = number(row.get(f"G_{year}"))
        if receptions is None or yards is None:
            continue
        total_receptions += receptions
        total_yards += yards
        if games is not None:
            seasons.append(
                f"{count_text(receptions)} catches in {count_text(games)} "
                f"games in {year}"
            )
        else:
            seasons.append(f"{count_text(receptions)} catches in {year}")

    line = number(row.get("Bet_Line_Rec_Yds"))
    if not seasons or line is None or total_receptions <= 0 or total_yards <= 0:
        raise ValueError(f"Cannot build veteran reason for {row.get('Player')!r}")

    implied = line / (total_yards / total_receptions)
    history = " and ".join(seasons)
    return (
        f"{history}. The {count_text(line)}-yard line implies about "
        f"{implied:.0f} catches at his recent weighted yards per reception. "
        f"{note}"
    )


def update() -> tuple[int, int]:
    with INPUT.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    for column in ("Predicted_Recs", "Reasoning_Why"):
        if column not in fieldnames:
            fieldnames.append(column)

    projected = 0
    for row in rows:
        yard_line = number(row.get("Bet_Line_Rec_Yds"))
        reception_line = number(row.get("Bet_Line_Rec"))
        if yard_line is None or reception_line is not None:
            continue
        if row.get("Predicted_Recs") and row.get("Reasoning_Why"):
            continue

        player = row["Player"]
        if player in PROJECTIONS:
            prediction, note = PROJECTIONS[player]
            reason = build_reason(row, note)
        elif player in ROOKIE_PROJECTIONS:
            prediction, reason = ROOKIE_PROJECTIONS[player]
        else:
            raise ValueError(f"Missing 2026 reception projection for {player!r}")

        row["Predicted_Recs"] = str(prediction)
        row["Reasoning_Why"] = reason
        projected += 1

    rows.sort(
        key=lambda row: (
            number(row.get("Bet_Line_Rec_Yds")) is None,
            -(number(row.get("Bet_Line_Rec_Yds")) or 0),
        )
    )

    incomplete = [
        row["Player"]
        for row in rows
        if number(row.get("Bet_Line_Rec_Yds")) is not None
        and number(row.get("Bet_Line_Rec")) is None
        and (not row.get("Predicted_Recs") or not row.get("Reasoning_Why"))
    ]
    if incomplete:
        raise ValueError(f"Incomplete reception predictions: {incomplete}")

    temp_path = INPUT.with_suffix(INPUT.suffix + ".tmp")
    with temp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()
        writer.writerows(rows)
    temp_path.replace(INPUT)

    priced_rows = sum(number(row.get("Bet_Line_Rec_Yds")) is not None for row in rows)
    return projected, priced_rows


if __name__ == "__main__":
    projection_count, receiving_yard_line_count = update()
    print(
        f"Added {projection_count} reception predictions; "
        f"sorted {receiving_yard_line_count} rows with receiving-yard lines."
    )
