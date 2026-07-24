#!/usr/bin/env python3
"""Merge FantasyPros' 2025 full-PPR totals and WR ranks into the local CSVs."""

import csv
import os
import re
import tempfile
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen


SOURCE_URL = "https://www.fantasypros.com/nfl/stats/{position}.php?scoring=PPR&year=2025"
POINTS_COLUMN = "PPR_Points_2025"
RANK_COLUMN = "PPR_Rank_2025"
ROOT = Path(__file__).resolve().parent


class FantasyProsTableParser(HTMLParser):
    """Extract cells from the table whose HTML id is ``data``."""

    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_body = False
        self.in_row = False
        self.in_cell = False
        self.rows = []
        self.row = []
        self.cell_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and attrs.get("id") == "data":
            self.in_table = True
        elif self.in_table and tag == "tbody":
            self.in_body = True
        elif self.in_body and tag == "tr":
            self.in_row = True
            self.row = []
        elif self.in_row and tag == "td":
            self.in_cell = True
            self.cell_text = []

    def handle_data(self, data):
        if self.in_cell:
            self.cell_text.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.in_cell:
            self.row.append(" ".join("".join(self.cell_text).split()))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            self.rows.append(self.row)
            self.in_row = False
        elif tag == "tbody" and self.in_body:
            self.in_body = False
        elif tag == "table" and self.in_table:
            self.in_table = False


def normalize_name(name):
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"\([^)]*\)", "", name.lower())
    name = name.replace("&", "and")
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", name)
    return re.sub(r"[^a-z0-9]", "", name)


def fetch_position(position):
    url = SOURCE_URL.format(position=position)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8")

    parser = FantasyProsTableParser()
    parser.feed(html)
    result = {}
    for row in parser.rows:
        # Rank, Player, position-specific stats ..., FPTS, FPTS/G, ROST
        if len(row) < 5:
            continue
        display_name = row[1].rsplit(" (", 1)[0]
        result[normalize_name(display_name)] = {
            "rank": int(row[0]),
            "player": display_name,
            "points": float(row[-3].replace(",", "")),
        }

    minimum_rows = {"rb": 100, "wr": 200, "te": 100}[position]
    if len(result) < minimum_rows:
        raise RuntimeError(f"Only parsed {len(result)} {position.upper()} rows from {url}")
    return result


STATS_ALIASES = {
    normalize_name("kenneth gainwell"): normalize_name("Kenny Gainwell"),
    normalize_name("gabriel davis"): normalize_name("Gabe Davis"),
    normalize_name("dwayne eskridge"): normalize_name("Dee Eskridge"),
    normalize_name("josh palmer"): normalize_name("Joshua Palmer"),
    normalize_name("marquise brown"): normalize_name("Hollywood Brown"),
    normalize_name("scott miller"): normalize_name("Scotty Miller"),
}


RANK_ALIASES = {
    normalize_name(alias): normalize_name(source_name)
    for alias, source_name in {
        "Jamaar": "Ja'Marr Chase",
        "JJettas": "Justin Jefferson",
        "Amon Ra": "Amon-Ra St. Brown",
        "ceedee": "CeeDee Lamb",
        "Puka": "Puka Nacua",
        "AJ": "A.J. Brown",
        "BTJ": "Brian Thomas Jr.",
        "Malik": "Malik Nabers",
        "JSN": "Jaxon Smith-Njigba",
        "Garret Wilson-": "Garrett Wilson",
        "Ladd Monkey": "Ladd McConkey",
        "Terry": "Terry McLaurin",
        "Davante": "Davante Adams",
        "Tyreek": "Tyreek Hill",
        "Tee": "Tee Higgins",
        "Marv": "Marvin Harrison Jr.",
        "Devonta": "DeVonta Smith",
        "DK": "DK Metcalf",
        "Zay": "Zay Flowers",
        "Darnell Money": "Darnell Mooney",
        "Jerry Juedy": "Jerry Jeudy",
        "Ricky Pearsell": "Ricky Pearsall",
        "tetoria Millen": "Tetairoa McMillan",
        "Jaydeen Reed": "Jayden Reed",
        "Rome": "Rome Odunze",
        "demario": "DeMario Douglas",
        "Keenan": "Keenan Allen",
        "Kupp": "Cooper Kupp",
        "Jauan Jennigs": "Jauan Jennings",
        "Deebo": "Deebo Samuel Sr.",
        "Keon": "Keon Coleman",
        "Pittman": "Michael Pittman Jr.",
        "shaheed": "Rashid Shaheed",
        "Cedric Tilllman": "Cedric Tillman",
        "Hollywood": "Hollywood Brown",
        "Josh Palmer": "Joshua Palmer",
    }.items()
}


RB_RANK_ALIASES = {
    normalize_name(alias): normalize_name(source_name)
    for alias, source_name in {
        "Bijan": "Bijan Robinson",
        "Saquon": "Saquon Barkley",
        "Jahmy Gibbs": "Jahmyr Gibbs",
        "Jeanty": "Ashton Jeanty",
        "CMC": "Christian McCaffrey",
        "Devon": "De'Von Achane",
        "JT": "Jonathan Taylor",
        "Bucky": "Bucky Irving",
        "Kamara": "Alvin Kamara",
        "Isaihah Pichacho": "Isiah Pacheco",
        "Dmont": "David Montgomery",
        "Chuba": "Chuba Hubbard",
        "Brian Robinson": "Brian Robinson Jr.",
        "Ken Walker": "Kenneth Walker III",
        "Javonte": "Javonte Williams",
        "Rhamodre Stevenson": "Rhamondre Stevenson",
        "Najee": "Najee Harris",
        "Dobbins": "J.K. Dobbins",
        "Teryvon Henderson": "TreVeyon Henderson",
        "Tank": "Tank Bigsby",
        "Swift": "D'Andre Swift",
        "Rico": "Rico Dowdle",
    }.items()
}


TE_RANK_ALIASES = {
    normalize_name(alias): normalize_name(source_name)
    for alias, source_name in {
        "Broccoli Bowers": "Brock Bowers",
        "Georger Kittle": "George Kittle",
        "Jonnu": "Jonnu Smith",
        "THock": "T.J. Hockenson",
        "Laporta": "Sam LaPorta",
        "Travis": "Travis Kelce",
        "isaiha Likely": "Isaiah Likely",
        "Dallas Gogurt": "Dallas Goedert",
        "Will Diselly": "Will Dissly",
        "Njoku": "David Njoku",
        "Jake Fergusun": "Jake Ferguson",
        "Conklin": "Tyler Conklin",
        "Juwan": "Juwan Johnson",
        "Pat Friermoth": "Pat Freiermuth",
        "Mike gesiki": "Mike Gesicki",
    }.items()
}


def write_csv_atomic(path, rows):
    original_mode = path.stat().st_mode & 0o777
    fd, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as output:
            csv.writer(output).writerows(rows)
        os.chmod(temporary_name, original_mode)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def merge_points(filename, source):
    path = ROOT / filename
    with path.open(newline="", encoding="utf-8") as input_file:
        rows = list(csv.reader(input_file))

    header = rows[0]
    player_index = header.index("Player")
    if POINTS_COLUMN in header:
        points_index = header.index(POINTS_COLUMN)
    else:
        points_index = len(header)
        header.append(POINTS_COLUMN)

    matched = 0
    zero_point_players = []
    for row in rows[1:]:
        key = normalize_name(row[player_index])
        key = STATS_ALIASES.get(key, key)
        points = source.get(key, {}).get("points", 0.0)
        if key in source:
            matched += 1
        else:
            zero_point_players.append(row[player_index])
        value = f"{points:.1f}"
        if points_index == len(row):
            row.append(value)
        else:
            row[points_index] = value

    write_csv_atomic(path, rows)
    return matched, zero_point_players


def merge_wr_ranks(source):
    path = ROOT / "ranks_2025.csv"
    with path.open(newline="", encoding="utf-8") as input_file:
        rows = list(csv.reader(input_file))

    if not rows or rows[0][0] != "Player":
        rows.insert(
            0,
            [
                "Player",
                "Rank_2024",
                "Outlook_2025",
                "Notes",
                "Tier_1",
                "Tier_2",
                "Tier_3",
                "Tier_4",
                "Tier_5",
                "Tier_6",
            ],
        )

    header = rows[0]
    if RANK_COLUMN in header:
        rank_index = header.index(RANK_COLUMN)
    else:
        rank_index = len(header)
        header.append(RANK_COLUMN)

    missing = []
    for row in rows[1:]:
        key = normalize_name(row[0])
        key = RANK_ALIASES.get(key, key)
        rank = source.get(key, {}).get("rank")
        if rank is None:
            missing.append(row[0])
            value = ""
        else:
            value = str(rank)
        if rank_index == len(row):
            row.append(value)
        else:
            row[rank_index] = value

    if missing:
        raise RuntimeError(f"Unmatched players in ranks_2025.csv: {', '.join(missing)}")
    write_csv_atomic(path, rows)
    return len(rows) - 1


def merge_position_rankings(filename, source, original_header, aliases):
    path = ROOT / filename
    with path.open(newline="", encoding="utf-8") as input_file:
        rows = list(csv.reader(input_file))

    if not rows or rows[0][0] != "Player":
        rows.insert(0, original_header)

    header = rows[0]
    for column in (POINTS_COLUMN, RANK_COLUMN):
        if column not in header:
            header.append(column)
    points_index = header.index(POINTS_COLUMN)
    rank_index = header.index(RANK_COLUMN)

    missing = []
    for row in rows[1:]:
        key = normalize_name(row[0])
        key = aliases.get(key, key)
        source_row = source.get(key)
        if source_row is None:
            missing.append(row[0])
            points_value = "0.0"
            rank_value = ""
        else:
            points_value = f"{source_row['points']:.1f}"
            rank_value = str(source_row["rank"])

        while len(row) < len(header):
            row.append("")
        row[points_index] = points_value
        row[rank_index] = rank_value

    write_csv_atomic(path, rows)
    return len(rows) - 1, missing


def main():
    rb_source = fetch_position("rb")
    wr_source = fetch_position("wr")
    te_source = fetch_position("te")
    rb_matches, rb_zeroes = merge_points("rb_stats.csv", rb_source)
    wr_matches, wr_zeroes = merge_points("wr_stats.csv", wr_source)
    rank_matches = merge_wr_ranks(wr_source)
    rb_rank_matches, rb_rank_missing = merge_position_rankings(
        "rbs_rank_2025.csv",
        rb_source,
        [
            "Player",
            "Rank_2024",
            "Outlook_2025",
            "Notes",
            "Tier_1",
            "Tier_2",
            "Tier_3",
            "Tier_4",
            "Tier_5",
            "Tier_6",
            "Handcuff",
        ],
        RB_RANK_ALIASES,
    )
    te_rank_matches, te_rank_missing = merge_position_rankings(
        "te_rank2025.csv",
        te_source,
        ["Player", "Rank_2024", "Outlook_2025", "Notes"],
        TE_RANK_ALIASES,
    )
    print(
        f"FantasyPros source rows: {len(rb_source)} RB, {len(wr_source)} WR, "
        f"{len(te_source)} TE"
    )
    print(f"rb_stats.csv: {rb_matches} matched; {len(rb_zeroes)} assigned 0.0")
    print(f"wr_stats.csv: {wr_matches} matched; {len(wr_zeroes)} assigned 0.0")
    print(f"ranks_2025.csv: {rank_matches} WR ranks matched")
    print(
        f"rbs_rank_2025.csv: {rb_rank_matches - len(rb_rank_missing)} matched; "
        f"missing={rb_rank_missing}"
    )
    print(
        f"te_rank2025.csv: {te_rank_matches - len(te_rank_missing)} matched; "
        f"missing={te_rank_missing}"
    )


if __name__ == "__main__":
    main()
