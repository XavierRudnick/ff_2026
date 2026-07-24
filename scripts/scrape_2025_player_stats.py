#!/usr/bin/env python3
"""Build 2025 regular-season RB and pass-catcher player-feature CSVs.

The existing 2024 player ordering is preserved, then active 2025 players who
were not in those files (most notably rookies) are appended in descending PPR
order. The pass-catcher output combines WRs with the locally ranked TE
universe and all other active 2025 TEs. Duplicate multi-team rows in the 2024
source tables are collapsed to one player row. ``normalized_line`` is
intentionally left blank.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import tempfile
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd
import requests


SEASON = 2025
PROJECT_ROOT = Path(__file__).resolve().parent.parent

NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"
FFOPPORTUNITY = "https://github.com/ffverse/ffopportunity/releases/download/latest-data"

SOURCES = {
    "stats": f"{NFLVERSE}/stats_player/stats_player_reg_{SEASON}.csv.gz",
    "adv_rush": f"{NFLVERSE}/pfr_advstats/advstats_week_rush_{SEASON}.csv.gz",
    "adv_rec": f"{NFLVERSE}/pfr_advstats/advstats_week_rec_{SEASON}.csv.gz",
    "roster": f"{NFLVERSE}/rosters/roster_{SEASON}.csv.gz",
    "pbp": f"{NFLVERSE}/pbp/play_by_play_{SEASON}.csv.gz",
    "expected": f"{FFOPPORTUNITY}/ep_weekly_{SEASON}.csv",
    "sumer_wr": "https://sumersports.com/players/wide-receiver/?season=2025",
    "sumer_te": "https://sumersports.com/players/tight-end/?season=2025",
}

RB_COLUMNS = [
    "Player", "Age", "Team", "G", "Att", "Team Att", "Att_Share", "Yds",
    "YBC", "YBC/Att", "YAC", "YAC/Att", "REC", "TGT", "Team TGT",
    "TGT_share", "Rec YDS", "Rush TD", "Rec TD", "RZ TD", "RZ PCT",
    "RZ REC", "RZ REC TD", "FPTS", "FPTS/G", "XFP", "TD/G", "XTD",
    "fpts_diff", "tds_diff", "VOR", "ALY", "normalized_line",
]

WR_COLUMNS = [
    "Player", "Position", "Age", "Team", "G", "Tgt", "Rec", "Yds",
    "Target_Share", "CATCHABLE", "AIR", "team_air", "air_pct", "RZ TGT",
    "RZ_REC", "RZ_REC_PCT", "RZ_P_TD", "RZ_TGT_PCT", "Routes Run",
    "FPTS", "FPTS/G", "XFP", "fpts_diff", "RTD", "TD/G", "XTD",
    "td_diff", "WOPR", "VOR", "YPRR", "normalized_line", "TGT/G",
]

# Canonical display names for shorthand and misspellings in te/te_rank2025.csv.
TE_DISPLAY_ALIASES = {
    "broccolibowers": "Brock Bowers",
    "treymcbride": "Trey McBride",
    "georgerkittle": "George Kittle",
    "jonnu": "Jonnu Smith",
    "thock": "T.J. Hockenson",
    "laporta": "Sam LaPorta",
    "travis": "Travis Kelce",
    "isaihalikely": "Isaiah Likely",
    "dallasgogurt": "Dallas Goedert",
    "willdiselly": "Will Dissly",
    "njoku": "David Njoku",
    "jakefergusun": "Jake Ferguson",
    "mikegesiki": "Mike Gesicki",
    "conklin": "Tyler Conklin",
    "juwan": "Juwan Johnson",
    "patfriermoth": "Pat Freiermuth",
}

# Source naming differences that do not disappear when suffixes/punctuation are
# normalized.
ALIASES = {
    "cameronskattebo": "camskattebo",
    "joshpalmer": "joshuapalmer",
    "gabrieldavis": "gabedavis",
    "dwayneeskridge": "deeeskridge",
    "scottmiller": "scottymiller",
    "kennethgainwell": "kennygainwell",
    "patricktaylor": "patricktaylorjr",
    **{
        alias: re.sub(r"[^a-z0-9]", "", canonical.lower())
        for alias, canonical in TE_DISPLAY_ALIASES.items()
    },
}

PFR_TEAM = {
    "GB": "GNB", "KC": "KAN", "LV": "LVR", "LA": "LAR", "NE": "NWE",
    "NO": "NOR", "SF": "SFO", "TB": "TAM",
}


def normalize_name(value: object) -> str:
    value = "" if value is None else str(value)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.lower().replace("&", "and")
    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", value)
    key = re.sub(r"[^a-z0-9]", "", value)
    return ALIASES.get(key, key)


def canonical_team(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    team = str(value).upper()
    return PFR_TEAM.get(team, team)


def is_number(value: object) -> bool:
    try:
        return value is not None and not pd.isna(value) and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def number(value: object, default: float = 0.0) -> float:
    return float(value) if is_number(value) else default


def integer(value: object) -> int:
    return int(round(number(value)))


def safe_div(numerator: float, denominator: float, scale: float = 1.0) -> float | None:
    if not denominator:
        return None
    return numerator / denominator * scale


def rounded(value: float | None, digits: int) -> float | str:
    if value is None or not is_number(value):
        return ""
    result = round(float(value), digits)
    return 0.0 if result == -0.0 else result


def pct_string(value: float | None) -> str:
    if value is None or not is_number(value):
        return ""
    return f"{float(value):.1f}%"


def download(session: requests.Session, url: str, destination: Path) -> Path:
    if destination.exists() and destination.stat().st_size:
        return destination
    response = session.get(url, timeout=120)
    response.raise_for_status()
    destination.write_bytes(response.content)
    return destination


def load_player_universe(
    path: Path, default_position: str | None = None
) -> list[dict[str, object]]:
    frame = pd.read_csv(path)
    if "Player" not in frame:
        raise ValueError(f"{path.name} has no Player column")
    players: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in frame.to_dict("records"):
        raw_name = str(row["Player"]).strip()
        raw_key = re.sub(r"[^a-z0-9]", "", raw_name.lower())
        name = TE_DISPLAY_ALIASES.get(raw_key, raw_name)
        key = normalize_name(name)
        if not key or key in seen:
            continue
        seen.add(key)
        players.append(
            {
                "key": key,
                "name": name,
                "position": default_position,
                "prior_age": integer(row.get("Age")) if is_number(row.get("Age")) else None,
                "prior_team": str(row.get("Team", "")).strip(),
            }
        )
    return players


def add_active_players(
    players: list[dict[str, object]],
    stats: pd.DataFrame,
    positions: set[str],
) -> list[dict[str, object]]:
    """Append active 2025 players absent from the prior-season universe."""
    result = list(players)
    seen = {str(player["key"]) for player in result}
    candidates = []
    for row in stats.to_dict("records"):
        if (
            str(row.get("position")) not in positions
            or integer(row.get("games")) <= 0
        ):
            continue
        name = row.get("player_display_name")
        if name is None or pd.isna(name):
            continue
        key = normalize_name(name)
        if not key or key in seen:
            continue
        candidates.append(row)
        seen.add(key)

    candidates.sort(
        key=lambda row: (
            -number(row.get("fantasy_points_ppr")),
            str(row.get("player_display_name", "")).lower(),
        )
    )
    for row in candidates:
        name = str(row["player_display_name"]).strip()
        result.append(
            {
                "key": normalize_name(name),
                "name": name,
                "position": str(row.get("position") or ""),
                "prior_age": None,
                "prior_team": canonical_team(row.get("recent_team")),
            }
        )
    return result


def keyed_records(
    frame: pd.DataFrame,
    name_column: str,
    preferred_positions: set[str] | None = None,
    activity_columns: tuple[str, ...] = (),
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    scores: dict[str, tuple[int, float]] = {}
    for row in frame.to_dict("records"):
        key = normalize_name(row.get(name_column))
        preferred = int(
            preferred_positions is not None
            and str(row.get("position")) in preferred_positions
        )
        activity = sum(abs(number(row.get(column))) for column in activity_columns)
        score = (preferred, activity)
        if key and (key not in result or score > scores[key]):
            result[key] = row
            scores[key] = score
    return result


def aggregate_advanced(frame: pd.DataFrame, kind: str) -> tuple[dict, dict]:
    frame = frame[frame["game_type"].eq("REG")].copy()
    if kind == "rush":
        columns = [
            "carries", "rushing_yards_before_contact", "rushing_yards_after_contact"
        ]
    else:
        columns = ["receiving_drop"]
    grouped_id: dict[str, dict[str, float]] = {}
    grouped_name: dict[str, dict[str, float]] = {}
    for group_key, group in frame.groupby("pfr_player_id", dropna=True):
        grouped_id[str(group_key)] = {c: number(group[c].sum(min_count=1)) for c in columns}
    for group_key, group in frame.groupby(frame["pfr_player_name"].map(normalize_name)):
        if group_key:
            grouped_name[group_key] = {c: number(group[c].sum(min_count=1)) for c in columns}
    return grouped_id, grouped_name


def parse_sumer_player_data(html: str) -> list[dict[str, object]]:
    payloads: list[str] = []
    pattern = r"<script>self\.__next_f\.push\((.*?)\)</script>"
    for raw in re.findall(pattern, html, flags=re.S):
        try:
            packet = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(packet, list) and len(packet) > 1 and isinstance(packet[1], str):
            payloads.append(packet[1])
    for payload in sorted(payloads, key=len, reverse=True):
        if '"playerData"' not in payload or ":" not in payload:
            continue
        try:
            tree = json.loads(payload.split(":", 1)[1])
        except json.JSONDecodeError:
            continue
        if isinstance(tree, list) and len(tree) >= 4 and isinstance(tree[3], dict):
            data = tree[3].get("playerData")
            if isinstance(data, list):
                return data
    raise RuntimeError("Could not locate SumerSports playerData in page payload")


def build_sumer_index(session: requests.Session) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for source in ("sumer_wr", "sumer_te"):
        response = session.get(SOURCES[source], timeout=120)
        response.raise_for_status()
        for row in parse_sumer_player_data(response.text):
            if integer(row.get("season")) != SEASON:
                continue
            key = normalize_name(row.get("displayName"))
            if key:
                result[key] = row
    return result


def add_pff_route_fallbacks(
    session: requests.Session,
    players: list[dict[str, object]],
    stats_name: dict[str, dict[str, object]],
    roster_id: dict[str, dict[str, object]],
    roster_name: dict[str, dict[str, object]],
    sumer: dict[str, dict[str, object]],
) -> None:
    """Fill the rare Sumer omissions (usually players reclassified by position)."""
    route_pattern = re.compile(
        r"Routes Run</div></div>.*?"
        r'data-testid="playerProfiles\.statsTableRow\.statValue">([0-9,]+)</div>',
        flags=re.S,
    )
    for player in players:
        key = str(player["key"])
        stat = stats_name.get(key, {})
        if integer(stat.get("targets")) == 0:
            continue
        if integer(sumer.get(key, {}).get("receivingPassRoutesRun")) > 0:
            continue
        player_id = str(stat["player_id"]) if stat.get("player_id") is not None else ""
        roster = roster_id.get(player_id) or roster_name.get(key) or {}
        pff_id = roster.get("pff_id")
        if pff_id is None or pd.isna(pff_id):
            continue
        url = f"https://www.pff.com/nfl/players/player/{int(float(pff_id))}?season=2025&seasonType=REG"
        response = session.get(url, timeout=60)
        response.raise_for_status()
        match = route_pattern.search(response.text)
        if match:
            sumer[key] = {
                **sumer.get(key, {}),
                "receivingPassRoutesRun": match.group(1).replace(",", ""),
            }


def roster_indexes(roster: pd.DataFrame) -> tuple[dict, dict, dict]:
    roster = roster.copy()
    roster["_week"] = pd.to_numeric(roster["week"], errors="coerce").fillna(-1)
    roster = roster.sort_values(["_week", "game_type"], na_position="first")
    by_id: dict[str, dict[str, object]] = {}
    by_name: dict[str, dict[str, object]] = {}
    position_by_id: dict[str, str] = {}
    for row in roster.to_dict("records"):
        gsis = row.get("gsis_id")
        if gsis is not None and not pd.isna(gsis):
            by_id[str(gsis)] = row
            if row.get("position") is not None and not pd.isna(row.get("position")):
                position_by_id[str(gsis)] = str(row["position"])
        key = normalize_name(row.get("full_name"))
        if key:
            current = by_name.get(key)
            offensive = {"RB", "FB", "WR", "TE"}
            if current is None or (
                str(row.get("position")) in offensive
                and str(current.get("position")) not in offensive
            ):
                by_name[key] = row
    return by_id, by_name, position_by_id


def age_for(row: dict[str, object] | None, prior_age: int | None) -> int | str:
    if row:
        raw = row.get("birth_date")
        if raw is not None and not pd.isna(raw):
            try:
                born = date.fromisoformat(str(raw)[:10])
                end = date(SEASON, 12, 31)
                return end.year - born.year - ((end.month, end.day) < (born.month, born.day))
            except ValueError:
                pass
    return prior_age + 1 if prior_age is not None else ""


def analyze_pbp(pbp: pd.DataFrame, position_by_id: dict[str, str]) -> dict[str, object]:
    pbp = pbp[
        pbp["season_type"].eq("REG")
        & pbp["play_type"].ne("no_play")
        & pbp["two_point_attempt"].fillna(0).ne(1)
    ].copy()
    pbp["team"] = pbp["posteam"].map(canonical_team)
    pbp["rusher_pos"] = pbp["rusher_player_id"].map(position_by_id)
    pbp["receiver_pos"] = pbp["receiver_player_id"].map(position_by_id)

    rushes = pbp[pbp["rush_attempt"].eq(1) & pbp["rusher_player_id"].notna()].copy()
    targets = pbp[pbp["pass_attempt"].eq(1) & pbp["receiver_player_id"].notna()].copy()

    rb_positions = {"RB", "FB"}
    rb_rushes = rushes[rushes["rusher_pos"].isin(rb_positions)].copy()
    rb_targets = targets[targets["receiver_pos"].isin(rb_positions)].copy()

    team_rb_att = rb_rushes.groupby("team").size().to_dict()
    team_rb_tgt = rb_targets.groupby("team").size().to_dict()
    team_targets = targets.groupby("team").size().to_dict()
    team_air = targets.groupby("team")["air_yards"].sum(min_count=1).fillna(0).to_dict()

    red_rush = rushes[rushes["yardline_100"].le(20)].copy()
    red_tgt = targets[targets["yardline_100"].le(20)].copy()
    red_rb_rush = red_rush[red_rush["rusher_pos"].isin(rb_positions)]

    team_rz_rush: dict[tuple[str, str], int] = {}
    team_rz_tgt: dict[tuple[str, str], int] = {}
    for (team, position), group in red_rush.groupby(["team", "rusher_pos"]):
        position_group = "RB" if position in rb_positions else str(position)
        team_rz_rush[(team, position_group)] = team_rz_rush.get((team, position_group), 0) + len(group)
    for (team, position), group in red_tgt.groupby(["team", "receiver_pos"]):
        position_group = "RB" if position in rb_positions else str(position)
        team_rz_tgt[(team, position_group)] = team_rz_tgt.get((team, position_group), 0) + len(group)

    rz_rush_player: dict[str, dict[str, float]] = {}
    for player_id, group in red_rush.groupby("rusher_player_id"):
        rz_rush_player[str(player_id)] = {
            "att": float(len(group)),
            "td": number(group["rush_touchdown"].sum(min_count=1)),
        }
    rz_rec_player: dict[str, dict[str, float]] = {}
    for player_id, group in red_tgt.groupby("receiver_player_id"):
        rz_rec_player[str(player_id)] = {
            "tgt": float(len(group)),
            "rec": number(group["complete_pass"].sum(min_count=1)),
            "td": number(group["pass_touchdown"].sum(min_count=1)),
        }

    player_teams: dict[str, set[str]] = defaultdict(set)
    for _, row in rushes[["rusher_player_id", "team"]].dropna().iterrows():
        player_teams[str(row["rusher_player_id"])].add(str(row["team"]))
    for _, row in targets[["receiver_player_id", "team"]].dropna().iterrows():
        player_teams[str(row["receiver_player_id"])].add(str(row["team"]))

    # Publicly reproducible line-yards weighting. Normalize it so the league
    # average equals league RB yards per carry, matching the ALY scale.
    gains = pd.to_numeric(rb_rushes["yards_gained"], errors="coerce").fillna(0)
    line_yards = gains.where(gains >= 0, gains * 1.2)
    line_yards = line_yards.where(gains <= 4, 4 + (gains - 4) * 0.5)
    line_yards = line_yards.where(gains <= 10, 7.0)
    rb_rushes["line_yards"] = line_yards
    raw_total = number(rb_rushes["line_yards"].sum())
    factor = number(rb_rushes["yards_gained"].sum()) / raw_total if raw_total else 1.0
    aly: dict[str, float] = {}
    aly_attempts: dict[str, int] = {}
    for team, group in rb_rushes.groupby("team"):
        aly[str(team)] = number(group["line_yards"].mean()) * factor
        aly_attempts[str(team)] = len(group)

    return {
        "team_rb_att": team_rb_att,
        "team_rb_tgt": team_rb_tgt,
        "team_targets": team_targets,
        "team_air": team_air,
        "team_rz_rush": team_rz_rush,
        "team_rz_tgt": team_rz_tgt,
        "rz_rush_player": rz_rush_player,
        "rz_rec_player": rz_rec_player,
        "player_teams": player_teams,
        "aly": aly,
        "aly_attempts": aly_attempts,
    }


def teams_for(player_id: str | None, recent_team: str, pbp_data: dict) -> set[str]:
    teams = set(pbp_data["player_teams"].get(player_id or "", set()))
    if recent_team:
        teams.add(recent_team)
    return {team for team in teams if team}


def team_label(teams: set[str], fallback: str) -> str:
    if len(teams) > 1:
        return f"{len(teams)}TM"
    if teams:
        return next(iter(teams))
    return fallback or "FA"


def sum_teams(mapping: dict, teams: set[str]) -> float:
    return sum(number(mapping.get(team)) for team in teams)


def weighted_aly(teams: set[str], pbp_data: dict) -> float | None:
    total_attempts = sum(integer(pbp_data["aly_attempts"].get(t)) for t in teams)
    if not total_attempts:
        return None
    total = sum(
        number(pbp_data["aly"].get(t)) * integer(pbp_data["aly_attempts"].get(t))
        for t in teams
    )
    return total / total_attempts


def expected_indexes(expected: pd.DataFrame) -> tuple[dict, dict]:
    expected = expected[pd.to_numeric(expected["week"], errors="coerce").le(18)]
    columns = ["total_fantasy_points_exp", "total_touchdown_exp"]
    by_id: dict[str, dict[str, float]] = {}
    by_name: dict[str, dict[str, float]] = {}
    for player_id, group in expected.groupby("player_id", dropna=True):
        by_id[str(player_id)] = {c: number(group[c].sum(min_count=1)) for c in columns}
    for key, group in expected.groupby(expected["full_name"].map(normalize_name)):
        if key:
            by_name[key] = {c: number(group[c].sum(min_count=1)) for c in columns}
    return by_id, by_name


def select_by_id_or_name(
    player_id: str | None, key: str, by_id: dict, by_name: dict
) -> dict[str, object]:
    if player_id and player_id in by_id:
        return by_id[player_id]
    return by_name.get(key, {})


def build_rb_rows(players: list[dict], context: dict) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for player in players:
        key = player["key"]
        stat = context["stats_rb_name"].get(key, {})
        player_id = str(stat["player_id"]) if stat.get("player_id") is not None else None
        roster = (
            context["roster_id"].get(player_id or "")
            or context["roster_name"].get(key)
        )
        recent_team = canonical_team(stat.get("recent_team") or (roster or {}).get("team"))
        teams = teams_for(player_id, recent_team, context["pbp"])
        team_att = sum_teams(context["pbp"]["team_rb_att"], teams)
        team_tgt = sum_teams(context["pbp"]["team_rb_tgt"], teams)

        adv = select_by_id_or_name(
            str((roster or {}).get("pfr_id")) if (roster or {}).get("pfr_id") is not None else None,
            key,
            context["rush_id"],
            context["rush_name"],
        )
        exp = select_by_id_or_name(
            player_id, key, context["expected_id"], context["expected_name"]
        )
        rz_rush = context["pbp"]["rz_rush_player"].get(player_id or "", {})
        rz_rec = context["pbp"]["rz_rec_player"].get(player_id or "", {})

        games = integer(stat.get("games"))
        carries = integer(stat.get("carries"))
        targets = integer(stat.get("targets"))
        receptions = integer(stat.get("receptions"))
        rush_td = integer(stat.get("rushing_tds"))
        rec_td = integer(stat.get("receiving_tds"))
        total_td = rush_td + rec_td
        fpts = number(stat.get("fantasy_points_ppr"))
        fptsg = safe_div(fpts, games)
        xfp = safe_div(number(exp.get("total_fantasy_points_exp")), games)
        tdpg = safe_div(total_td, games)
        xtd = safe_div(number(exp.get("total_touchdown_exp")), games)
        ybc = number(adv.get("rushing_yards_before_contact"))
        yac = number(adv.get("rushing_yards_after_contact"))

        rz_team_att = sum(
            integer(context["pbp"]["team_rz_rush"].get((team, "RB"))) for team in teams
        )
        rz_share = safe_div(number(rz_rush.get("att")), rz_team_att, 100)

        row = {
            "Player": player["name"],
            "Age": age_for(roster, player["prior_age"]),
            "Team": team_label(teams, recent_team),
            "G": games,
            "Att": carries,
            "Team Att": integer(team_att),
            "Att_Share": rounded(safe_div(carries, team_att, 100), 2),
            "Yds": integer(stat.get("rushing_yards")),
            "YBC": integer(ybc),
            "YBC/Att": rounded(safe_div(ybc, carries), 2),
            "YAC": integer(yac),
            "YAC/Att": rounded(safe_div(yac, carries), 2),
            "REC": receptions,
            "TGT": targets,
            "Team TGT": integer(team_tgt),
            "TGT_share": rounded(safe_div(targets, team_tgt, 100), 2),
            "Rec YDS": integer(stat.get("receiving_yards")),
            "Rush TD": rush_td,
            "Rec TD": rec_td,
            "RZ TD": integer(rz_rush.get("td")),
            "RZ PCT": pct_string(rz_share),
            "RZ REC": integer(rz_rec.get("rec")),
            "RZ REC TD": integer(rz_rec.get("td")),
            "FPTS": rounded(fpts, 1),
            "FPTS/G": rounded(fptsg or 0, 1),
            "XFP": rounded(xfp or 0, 1),
            "TD/G": rounded(tdpg or 0, 2),
            "XTD": rounded(xtd or 0, 2),
            "fpts_diff": rounded((fptsg or 0) - (xfp or 0), 1),
            "tds_diff": rounded((tdpg or 0) - (xtd or 0), 2),
            "VOR": rounded((fptsg or 0) - 11.5, 1),
            "ALY": rounded(weighted_aly(teams, context["pbp"]), 2),
            "normalized_line": "",
        }
        rows.append(row)
    return rows


def build_wr_rows(players: list[dict], context: dict) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for player in players:
        key = player["key"]
        stat = context["stats_wr_name"].get(key, {})
        player_id = str(stat["player_id"]) if stat.get("player_id") is not None else None
        roster = (
            context["roster_id"].get(player_id or "")
            or context["roster_name"].get(key)
        )
        recent_team = canonical_team(stat.get("recent_team") or (roster or {}).get("team"))
        teams = teams_for(player_id, recent_team, context["pbp"])
        position = str(
            stat.get("position")
            or (roster or {}).get("position")
            or player.get("position")
            or "WR"
        )
        position_group = "TE" if position == "TE" else "WR"

        adv = select_by_id_or_name(
            str((roster or {}).get("pfr_id")) if (roster or {}).get("pfr_id") is not None else None,
            key,
            context["rec_id"],
            context["rec_name"],
        )
        exp = select_by_id_or_name(
            player_id, key, context["expected_id"], context["expected_name"]
        )
        sumer = context["sumer"].get(key, {})
        rz_rec = context["pbp"]["rz_rec_player"].get(player_id or "", {})

        games = integer(stat.get("games"))
        targets = integer(stat.get("targets"))
        receptions = integer(stat.get("receptions"))
        yards = integer(stat.get("receiving_yards"))
        rec_td = integer(stat.get("receiving_tds"))
        rush_td = integer(stat.get("rushing_tds"))
        total_td = rec_td + rush_td
        fpts = number(stat.get("fantasy_points_ppr"))
        fptsg = safe_div(fpts, games)
        xfp = safe_div(number(exp.get("total_fantasy_points_exp")), games)
        tdpg = safe_div(total_td, games)
        xtd = safe_div(number(exp.get("total_touchdown_exp")), games)
        routes = integer(sumer.get("receivingPassRoutesRun"))
        air = number(stat.get("receiving_air_yards"))
        air_share = number(stat.get("air_yards_share"))
        calculated_team_air = safe_div(air, air_share) if air_share else None
        if calculated_team_air is None:
            calculated_team_air = sum_teams(context["pbp"]["team_air"], teams)
        target_share = number(stat.get("target_share"))
        wopr = number(stat.get("wopr"))
        catchable = receptions + integer(adv.get("receiving_drop"))

        rz_team_tgt = sum(
            integer(context["pbp"]["team_rz_tgt"].get((team, position_group)))
            for team in teams
        )
        rz_tgt = number(rz_rec.get("tgt"))
        rz_catches = number(rz_rec.get("rec"))
        rz_catch_pct = safe_div(rz_catches, rz_tgt, 100)
        rz_target_pct = safe_div(rz_tgt, rz_team_tgt, 100)

        row = {
            "Player": player["name"],
            "Position": position_group,
            "Age": age_for(roster, player["prior_age"]),
            "Team": team_label(teams, recent_team),
            "G": games,
            "Tgt": targets,
            "Rec": receptions,
            "Yds": yards,
            "Target_Share": rounded(target_share * 100, 2),
            "CATCHABLE": catchable,
            "AIR": integer(air),
            "team_air": integer(calculated_team_air),
            "air_pct": rounded(air_share * 100, 2),
            "RZ TGT": integer(rz_tgt),
            "RZ_REC": integer(rz_catches),
            "RZ_REC_PCT": pct_string(rz_catch_pct),
            "RZ_P_TD": integer(rz_rec.get("td")),
            "RZ_TGT_PCT": pct_string(rz_target_pct),
            "Routes Run": routes,
            "FPTS": rounded(fpts, 1),
            "FPTS/G": rounded(fptsg or 0, 1),
            "XFP": rounded(xfp or 0, 1),
            "fpts_diff": rounded((fptsg or 0) - (xfp or 0), 1),
            "RTD": rec_td,
            "TD/G": rounded(tdpg or 0, 2),
            "XTD": rounded(xtd or 0, 2),
            "td_diff": rounded((tdpg or 0) - (xtd or 0), 2),
            "WOPR": rounded(wopr, 2),
            "VOR": rounded((fptsg or 0) - (8.5 if position_group == "TE" else 13.0), 1),
            "YPRR": rounded(safe_div(yards, routes), 2),
            "normalized_line": "",
            "TGT/G": rounded(safe_div(targets, games) or 0, 2),
        }
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rb-input", type=Path, default=PROJECT_ROOT / "rbs" / "rb_stats.csv"
    )
    parser.add_argument(
        "--wr-input", type=Path, default=PROJECT_ROOT / "wr" / "wr_stats_2024.csv"
    )
    parser.add_argument(
        "--te-input", type=Path, default=PROJECT_ROOT / "te" / "te_rank2025.csv"
    )
    parser.add_argument(
        "--rb-output", type=Path, default=PROJECT_ROOT / "rbs" / "rb_stats_2025.csv"
    )
    parser.add_argument(
        "--wr-output",
        type=Path,
        default=PROJECT_ROOT / "wr" / "wr_stats_act_2025.csv",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="Optional persistent raw-download cache (a temporary directory is the default)",
    )
    args = parser.parse_args()

    rb_players = load_player_universe(args.rb_input)
    wr_players = load_player_universe(args.wr_input, default_position="WR")
    te_players = load_player_universe(args.te_input, default_position="TE")
    session = requests.Session()
    session.headers.update({"User-Agent": "ff-2026-player-stats/1.0"})

    temporary = None
    if args.cache_dir:
        cache = args.cache_dir
        cache.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="nfl-2025-stats-")
        cache = Path(temporary.name)

    try:
        local = {
            name: download(session, SOURCES[name], cache / Path(SOURCES[name]).name)
            for name in ("stats", "adv_rush", "adv_rec", "roster", "pbp", "expected")
        }
        stats = pd.read_csv(local["stats"])
        roster = pd.read_csv(local["roster"], low_memory=False)
        adv_rush = pd.read_csv(local["adv_rush"])
        adv_rec = pd.read_csv(local["adv_rec"])
        expected = pd.read_csv(local["expected"], low_memory=False)
        rb_players = add_active_players(rb_players, stats, {"RB", "FB"})
        wr_players = add_active_players(wr_players, stats, {"WR"})
        te_players = add_active_players(te_players, stats, {"TE"})
        wr_keys = {player["key"] for player in wr_players}
        pass_catchers = wr_players + [
            player
            for player in te_players
            if player["key"] not in wr_keys
        ]

        pbp_columns = [
            "season_type", "week", "game_id", "posteam", "play_type",
            "two_point_attempt", "rush_attempt", "pass_attempt", "rusher_player_id",
            "receiver_player_id", "rush_touchdown", "pass_touchdown", "complete_pass",
            "yardline_100", "yards_gained", "air_yards",
        ]
        pbp = pd.read_csv(local["pbp"], usecols=pbp_columns, low_memory=False)

        roster_id, roster_name, position_by_id = roster_indexes(roster)
        for row in stats.to_dict("records"):
            if row.get("player_id") is not None and not pd.isna(row.get("player_id")):
                position_by_id[str(row["player_id"])] = str(row.get("position", ""))

        rush_id, rush_name = aggregate_advanced(adv_rush, "rush")
        rec_id, rec_name = aggregate_advanced(adv_rec, "rec")
        expected_id, expected_name = expected_indexes(expected)
        stats_rb_name = keyed_records(
            stats,
            "player_display_name",
            preferred_positions={"RB", "FB"},
            activity_columns=("carries", "targets"),
        )
        stats_wr_name = keyed_records(
            stats,
            "player_display_name",
            preferred_positions={"WR", "TE"},
            activity_columns=("targets", "receptions", "receiving_yards"),
        )
        sumer = build_sumer_index(session)
        add_pff_route_fallbacks(
            session, pass_catchers, stats_wr_name, roster_id, roster_name, sumer
        )
        context = {
            "stats_rb_name": stats_rb_name,
            "stats_wr_name": stats_wr_name,
            "roster_id": roster_id,
            "roster_name": roster_name,
            "rush_id": rush_id,
            "rush_name": rush_name,
            "rec_id": rec_id,
            "rec_name": rec_name,
            "expected_id": expected_id,
            "expected_name": expected_name,
            "sumer": sumer,
            "pbp": analyze_pbp(pbp, position_by_id),
        }

        rb_rows = build_rb_rows(rb_players, context)
        wr_rows = build_wr_rows(pass_catchers, context)
        args.rb_output.parent.mkdir(parents=True, exist_ok=True)
        args.wr_output.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rb_rows, columns=RB_COLUMNS).to_csv(args.rb_output, index=False)
        pd.DataFrame(wr_rows, columns=WR_COLUMNS).to_csv(args.wr_output, index=False)

        rb_active = sum(row["G"] > 0 for row in rb_rows)
        wr_active = sum(
            row["G"] > 0 and row["Position"] == "WR" for row in wr_rows
        )
        te_active = sum(
            row["G"] > 0 and row["Position"] == "TE" for row in wr_rows
        )
        print(
            f"Wrote {len(rb_rows)} RBs ({rb_active} with 2025 games) to {args.rb_output}"
        )
        print(
            f"Wrote {len(wr_rows)} pass catchers "
            f"({wr_active} active WR, {te_active} active TE) to {args.wr_output}"
        )
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    main()
