#!/usr/bin/env python3
"""Build a cross-site 2026 full-PPR overall ranking consensus.

The script parses the Firecrawl snapshots collected on 2026-07-26, reconciles
player-name variants, caps every deep source at its published top 300, and
writes one row per player ranked by at least one source.
"""

from __future__ import annotations

import csv
import difflib
import html
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote_plus


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / ".firecrawl"
OUTPUT = ROOT / "rankings" / "ppr_consensus_2026-07-26.csv"

SOURCE_ORDER = [
    "espn",
    "cbs",
    "yahoo",
    "footballguys",
    "rotoballer",
    "fantasypros",
    "draftsharks",
]

DISPLAY_PRIORITY = [
    "fantasypros",
    "yahoo",
    "rotoballer",
    "footballguys",
    "espn",
    "cbs",
    "draftsharks",
]

SOURCE_CAPS = {
    "espn": 300,
    "cbs": 200,
    "yahoo": 300,
    "footballguys": 300,
    "rotoballer": 300,
    # These two pages expose 25 free/public rows.
    "fantasypros": 25,
    "draftsharks": 25,
}

TEAM_DEFENSES = {
    "ARI": ("Arizona Cardinals", "Cardinals"),
    "ATL": ("Atlanta Falcons", "Falcons"),
    "BAL": ("Baltimore Ravens", "Ravens"),
    "BUF": ("Buffalo Bills", "Bills"),
    "CAR": ("Carolina Panthers", "Panthers"),
    "CHI": ("Chicago Bears", "Bears"),
    "CIN": ("Cincinnati Bengals", "Bengals"),
    "CLE": ("Cleveland Browns", "Browns"),
    "DAL": ("Dallas Cowboys", "Cowboys"),
    "DEN": ("Denver Broncos", "Broncos"),
    "DET": ("Detroit Lions", "Lions"),
    "GB": ("Green Bay Packers", "Packers"),
    "HOU": ("Houston Texans", "Texans"),
    "IND": ("Indianapolis Colts", "Colts"),
    "JAC": ("Jacksonville Jaguars", "Jaguars"),
    "KC": ("Kansas City Chiefs", "Chiefs"),
    "LAC": ("Los Angeles Chargers", "Chargers"),
    "LAR": ("Los Angeles Rams", "Rams"),
    "LV": ("Las Vegas Raiders", "Raiders"),
    "MIA": ("Miami Dolphins", "Dolphins"),
    "MIN": ("Minnesota Vikings", "Vikings"),
    "NE": ("New England Patriots", "Patriots"),
    "NO": ("New Orleans Saints", "Saints"),
    "NYG": ("New York Giants", "Giants"),
    "NYJ": ("New York Jets", "Jets"),
    "PHI": ("Philadelphia Eagles", "Eagles"),
    "PIT": ("Pittsburgh Steelers", "Steelers"),
    "SEA": ("Seattle Seahawks", "Seahawks"),
    "SF": ("San Francisco 49ers", "49ers"),
    "TB": ("Tampa Bay Buccaneers", "Buccaneers"),
    "TEN": ("Tennessee Titans", "Titans"),
    "WAS": ("Washington Commanders", "Commanders"),
}


@dataclass(frozen=True)
class Entry:
    source: str
    rank: int
    name: str
    position: str = ""
    team: str = ""


def read_snapshot(filename: str) -> str:
    path = SNAPSHOT_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing input snapshot: {path}")
    return path.read_text(encoding="utf-8")


def clean_text(value: str) -> str:
    return " ".join(html.unescape(value).replace("\u2019", "'").split())


def ascii_alnum(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", value)


def normalize_position(value: str) -> str:
    value = re.sub(r"\d", "", value.upper())
    return {
        "PK": "K",
        "TD": "DST",
        "DEF": "DST",
        "D/ST": "DST",
    }.get(value, value if value in {"QB", "RB", "WR", "TE", "K", "DST"} else "")


def defense_abbr(name: str, position: str = "", team: str = "") -> str:
    normalized = ascii_alnum(name)
    looks_like_defense = (
        normalize_position(position) == "DST"
        or "d/st" in name.lower()
        or normalized.endswith("dst")
    )
    for abbr, (full_name, nickname) in TEAM_DEFENSES.items():
        variants = {
            ascii_alnum(full_name),
            ascii_alnum(nickname),
            ascii_alnum(f"{nickname} D/ST"),
            ascii_alnum(f"{full_name} D/ST"),
        }
        if normalized in variants and (
            looks_like_defense or normalized == ascii_alnum(full_name)
        ):
            return abbr
    if looks_like_defense:
        team = {"JAX": "JAC", "WSH": "WAS", "LVR": "LV"}.get(team, team)
        if team in TEAM_DEFENSES:
            return team
    return ""


NAME_ALIASES = {
    "kenwalker": "kennethwalker",
    "kennygainwell": "kennethgainwell",
    "hollywoodbrown": "marquisebrown",
    "gabedavis": "gabrieldavis",
    "joshpalmer": "joshuapalmer",
    "chigokonkwo": "chigoziemokonkwo",
}


def identity_key(name: str, position: str = "", team: str = "") -> str:
    defense = defense_abbr(name, position, team)
    if defense:
        return f"dst_{defense.lower()}"

    value = clean_text(name)
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"\([^)]*\)", "", value)
    value = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", value)
    value = re.sub(r"[^a-z0-9]+", "", value)
    return NAME_ALIASES.get(value, value)


def slug_to_name(slug: str) -> str:
    """Turn a URL slug into a readable fallback name."""
    words = unquote_plus(slug).replace("-", " ").split()
    special = {
        "aj": "A.J.",
        "cj": "C.J.",
        "dj": "DJ",
        "dk": "DK",
        "jk": "J.K.",
        "kj": "K.J.",
        "rj": "RJ",
        "tj": "T.J.",
    }
    return " ".join(special.get(word.lower(), word.capitalize()) for word in words)


def parse_fantasypros() -> list[Entry]:
    text = read_snapshot("fantasypros-2026-ppr.md")
    pattern = re.compile(
        r"(?m)^\| (\d+) \|.*?\[([^\]]+)\]\("
        r"https://www\.fantasypros\.com/nfl/players/[^)]+"
        r"\).*?\(([A-Z]{2,3})\) \| ([A-Z]+)\d+ \|"
    )
    return [
        Entry("fantasypros", int(rank), clean_text(name), normalize_position(pos), team)
        for rank, name, team, pos in pattern.findall(text)
        if int(rank) <= SOURCE_CAPS["fantasypros"]
    ]


def parse_draftsharks() -> list[Entry]:
    text = read_snapshot("draftsharks-2026-ppr.md")
    pattern = re.compile(
        r"(?m)^\| (\d+) \|.*?\]\("
        r"https://www\.draftsharks\.com/fantasy/points-outlook/([^/]+)/\d+"
        r"\)<br>([A-Z]{2,3})<br>([A-Z]+)\d+ \|"
    )
    return [
        Entry(
            "draftsharks",
            int(rank),
            slug_to_name(slug),
            normalize_position(pos),
            {"LVR": "LV", "JAX": "JAC", "WSH": "WAS"}.get(team, team),
        )
        for rank, slug, team, pos in pattern.findall(text)
        if int(rank) <= SOURCE_CAPS["draftsharks"]
    ]


def parse_footballguys(max_rank: int | None = SOURCE_CAPS["footballguys"]) -> list[Entry]:
    text = read_snapshot("footballguys-2026-ppr.md")
    pattern = re.compile(
        r"(?m)^\| (\d+) \|.*?\[\*\*(.+?)\*\*\]\([^)]+\) "
        r"([A-Z]{2,3}|FA).*?\| ([A-Z/]+)\d+ \|"
    )
    return [
        Entry(
            "footballguys",
            int(rank),
            clean_text(name),
            normalize_position(pos),
            {"JAX": "JAC", "WSH": "WAS", "LVR": "LV"}.get(team, team),
        )
        for rank, name, team, pos in pattern.findall(text)
        if max_rank is None or int(rank) <= max_rank
    ]


def parse_rotoballer() -> list[Entry]:
    text = read_snapshot("rotoballer-2026-ppr.md")
    entries: list[Entry] = []

    player_pattern = re.compile(
        r"\[(\d+)(QB|RB|WR|TE|K).*?\]\("
        r"https://www\.rotoballer\.com/nfl/player/\d+/([^)]+)\)"
    )
    for rank, pos, encoded_name in player_pattern.findall(text):
        if int(rank) <= SOURCE_CAPS["rotoballer"]:
            entries.append(
                Entry(
                    "rotoballer",
                    int(rank),
                    clean_text(unquote_plus(encoded_name)),
                    normalize_position(pos),
                )
            )

    defense_pattern = re.compile(
        r"(?m)^(\d+)DST(.+?)DST[A-Z]{2,3}DST!\[[A-Z]{2,3}\]"
    )
    for rank, name in defense_pattern.findall(text):
        if int(rank) <= SOURCE_CAPS["rotoballer"]:
            entries.append(
                Entry("rotoballer", int(rank), clean_text(name), "DST")
            )

    return sorted(entries, key=lambda entry: entry.rank)


def parse_yahoo() -> list[Entry]:
    text = read_snapshot("yahoo-2026-ppr-interact.txt")
    entries = []
    for rank, name in re.findall(r"(?m)^(\d+)\.\s+(.+?)\s*$", text):
        if int(rank) <= SOURCE_CAPS["yahoo"]:
            position = "DST" if defense_abbr(name, "DST") else ""
            entries.append(Entry("yahoo", int(rank), clean_text(name), position))
    return entries


def parse_espn() -> list[Entry]:
    text = read_snapshot("espn-2026-ppr-top300.md")
    entries = []
    row_pattern = re.compile(
        r"(?m)^\| ([^|]+) \| ([^|]+), ([A-Z]{2,3}|FA) \| \$"
    )
    for rank, (rank_cell, name, team) in enumerate(row_pattern.findall(text), start=1):
        pos_match = re.search(r"(QB|RB|WR|TE|K|DST)", rank_cell)
        position = normalize_position(pos_match.group(1)) if pos_match else ""
        entries.append(Entry("espn", rank, clean_text(name), position, team))
    return entries[: SOURCE_CAPS["espn"]]


def parse_cbs() -> list[Entry]:
    text = read_snapshot("cbs-2026-ppr.md")
    start = text.index("\nConsensus\n")
    end = text.index("\n[Jamey Eisenberg]", start)
    consensus = text[start:end]
    pattern = re.compile(
        r"(?ms)^(\d+)\n\n"
        r"(?:!\[player-headshot\]\([^)]+\)\n\n)?"
        r"\[[^\]]+\]\((https://www\.cbssports\.com/nfl/(?:players|teams)/[^)]+)\) "
        r"(QB|RB|WR|TE|K|DST)\b"
    )

    entries = []
    for rank_text, url, pos in pattern.findall(consensus):
        rank = int(rank_text)
        if rank > SOURCE_CAPS["cbs"]:
            continue
        if "/players/" in url:
            slug_match = re.search(r"/players/\d+/([^/]+)/fantasy/", url)
        else:
            slug_match = re.search(r"/teams/[A-Z]+/([^/]+)/fantasy/", url)
        if not slug_match:
            continue
        entries.append(
            Entry("cbs", rank, slug_to_name(slug_match.group(1)), pos)
        )
    return entries


def validate_sources(entries_by_source: dict[str, list[Entry]]) -> None:
    expected = {
        "espn": 300,
        "cbs": 200,
        "yahoo": 300,
        "footballguys": 300,
        "rotoballer": 300,
        "fantasypros": 25,
        "draftsharks": 25,
    }
    for source, expected_count in expected.items():
        entries = entries_by_source[source]
        ranks = [entry.rank for entry in entries]
        if len(entries) != expected_count:
            raise RuntimeError(
                f"{source}: parsed {len(entries)} entries; expected {expected_count}"
            )
        if len(ranks) != len(set(ranks)):
            raise RuntimeError(f"{source}: duplicate ranks detected")
        keys = [
            identity_key(entry.name, entry.position, entry.team) for entry in entries
        ]
        if len(keys) != len(set(keys)):
            duplicates = sorted(
                key for key, count in Counter(keys).items() if count > 1
            )
            raise RuntimeError(
                f"{source}: duplicate normalized players detected: {duplicates[:10]}"
            )
        if set(ranks) != set(range(1, expected_count + 1)):
            missing = sorted(set(range(1, expected_count + 1)) - set(ranks))
            raise RuntimeError(f"{source}: non-contiguous ranks; missing {missing[:10]}")


def reconcile(
    entries_by_source: dict[str, list[Entry]],
    metadata_entries: list[Entry],
) -> tuple[dict[str, dict[str, int]], dict[str, str], dict[str, str], list[str]]:
    """Return source ranks, canonical names/positions, and audited fuzzy matches."""
    reliable_sources = [
        "fantasypros",
        "yahoo",
        "rotoballer",
        "footballguys",
        "cbs",
        "draftsharks",
    ]
    canonical_keys: set[str] = set()
    for source in reliable_sources:
        for entry in entries_by_source[source]:
            canonical_keys.add(identity_key(entry.name, entry.position, entry.team))

    ranks_by_key: dict[str, dict[str, int]] = defaultdict(dict)
    names_by_key: dict[str, dict[str, str]] = defaultdict(dict)
    positions_by_key: dict[str, Counter[str]] = defaultdict(Counter)
    fuzzy_audit: list[str] = []

    # Use the uncapped Footballguys board only to fill position metadata for
    # players who make another site's top 300. Its ranks beyond 300 do not
    # participate in the consensus.
    metadata_positions: dict[str, Counter[str]] = defaultdict(Counter)
    for entry in metadata_entries:
        if entry.position:
            metadata_positions[
                identity_key(entry.name, entry.position, entry.team)
            ][entry.position] += 1

    for source in SOURCE_ORDER:
        for entry in entries_by_source[source]:
            key = identity_key(entry.name, entry.position, entry.team)

            # ESPN's PDF text layer contains a handful of OCR spelling errors.
            # Match only unrecognized ESPN keys, constrain by position where
            # possible, and require both a high score and a clear best match.
            if source == "espn" and key not in canonical_keys and not key.startswith("dst_"):
                candidates = []
                for candidate in canonical_keys:
                    if candidate.startswith("dst_"):
                        continue
                    known_positions = positions_by_key.get(candidate)
                    if (
                        entry.position
                        and known_positions
                        and entry.position not in known_positions
                    ):
                        continue
                    ratio = difflib.SequenceMatcher(None, key, candidate).ratio()
                    candidates.append((ratio, candidate))
                candidates.sort(reverse=True)
                best_score, best_key = candidates[0] if candidates else (0.0, "")
                second_score = candidates[1][0] if len(candidates) > 1 else 0.0
                if best_score >= 0.84 and best_score - second_score >= 0.025:
                    fuzzy_audit.append(
                        f"ESPN rank {entry.rank}: {entry.name!r} -> "
                        f"{best_key!r} ({best_score:.3f})"
                    )
                    key = best_key

            ranks_by_key[key][source] = entry.rank
            names_by_key[key][source] = entry.name
            if entry.position:
                positions_by_key[key][entry.position] += 1

    canonical_names: dict[str, str] = {}
    canonical_positions: dict[str, str] = {}
    for key in ranks_by_key:
        if key.startswith("dst_"):
            abbr = key.removeprefix("dst_").upper()
            canonical_names[key] = f"{TEAM_DEFENSES[abbr][0]} D/ST"
            canonical_positions[key] = "DST"
            continue

        source_names = names_by_key[key]
        canonical_names[key] = next(
            source_names[source]
            for source in DISPLAY_PRIORITY
            if source in source_names
        )
        if positions_by_key[key]:
            canonical_positions[key] = positions_by_key[key].most_common(1)[0][0]
        elif metadata_positions[key]:
            canonical_positions[key] = metadata_positions[key].most_common(1)[0][0]
        else:
            canonical_positions[key] = ""

    return ranks_by_key, canonical_names, canonical_positions, fuzzy_audit


def write_consensus(
    ranks_by_key: dict[str, dict[str, int]],
    canonical_names: dict[str, str],
    canonical_positions: dict[str, str],
) -> list[dict[str, object]]:
    rows = []
    for key, source_ranks in ranks_by_key.items():
        ranks = list(source_ranks.values())
        rows.append(
            {
                "player": canonical_names[key],
                "position": canonical_positions[key],
                "average_rank": round(statistics.fmean(ranks), 2),
                "sources_ranked": len(ranks),
                **{f"{source}_rank": source_ranks.get(source, "") for source in SOURCE_ORDER},
            }
        )

    rows.sort(
        key=lambda row: (
            row["average_rank"],
            -row["sources_ranked"],
            str(row["player"]).lower(),
        )
    )
    for consensus_rank, row in enumerate(rows, start=1):
        row["consensus_rank"] = consensus_rank

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "consensus_rank",
        "player",
        "position",
        "average_rank",
        "sources_ranked",
        *[f"{source}_rank" for source in SOURCE_ORDER],
    ]
    with OUTPUT.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main() -> None:
    entries_by_source = {
        "espn": parse_espn(),
        "cbs": parse_cbs(),
        "yahoo": parse_yahoo(),
        "footballguys": parse_footballguys(),
        "rotoballer": parse_rotoballer(),
        "fantasypros": parse_fantasypros(),
        "draftsharks": parse_draftsharks(),
    }
    validate_sources(entries_by_source)
    ranks, names, positions, fuzzy_audit = reconcile(
        entries_by_source, parse_footballguys(max_rank=None)
    )
    rows = write_consensus(ranks, names, positions)

    print(f"Wrote {len(rows)} rows to {OUTPUT}")
    for source in SOURCE_ORDER:
        print(f"{source}: {len(entries_by_source[source])} ranks")
    print(f"ESPN fuzzy name corrections: {len(fuzzy_audit)}")
    for correction in fuzzy_audit:
        print(f"  {correction}")


if __name__ == "__main__":
    main()
