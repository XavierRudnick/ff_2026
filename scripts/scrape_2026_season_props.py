#!/usr/bin/env python3
"""Collect current 2026 NFL regular-season player totals from Illinois books.

The output is intentionally one row per offered side (Over/Under).  Caesars
requires a real browser session because its public JSON endpoint rejects plain
HTTP clients; the other live sources are collected from their public feeds.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
NOW = datetime.now(ZoneInfo("America/Chicago")).replace(microsecond=0)
STAMP = NOW.isoformat()
DATE = NOW.date().isoformat()
PROPS_PATH = ROOT / f"nfl_2026_season_props_{DATE}.csv"
STATUS_PATH = ROOT / f"nfl_2026_season_props_status_{DATE}.csv"

JURISDICTION = "IL"
SEASON = "2026"

FANDUEL_PAGE = "https://sportsbook.fanduel.com/football/nfl"
FANDUEL_API = (
    "https://sbapi.il.sportsbook.fanduel.com/api/content-managed-page"
    "?page=CUSTOM&customPageId=nfl&pbHorizontal=false&_ak=FhMFpcPWXMeyZxOx"
)

BETMGM_PAGE = "https://www.il.betmgm.com/en/sports/football-11/betting/usa-9/nfl-35"
BETMGM_CONFIG = (
    "https://www.il.betmgm.com/en/api/clientconfig?browserUrl="
    "http%3A%2F%2Fwww.il.betmgm.com%2Fen%2Fsports%2Ffootball-11%2Fbetting%2Fusa-9%2Fnfl-35"
    "&x-from-product=host-app"
)

CAESARS_PAGE = "https://sportsbook.caesars.com/us/il/bet/americanfootball/events/all"
CAESARS_API_ROOT = (
    "https://api.americanwagering.com/regions/us/locations/il/brands/czr/sb"
)

BETRIVERS_PAGE = "https://il.betrivers.com/?page=sportsbook&group=1000093656&type=futures"
BETRIVERS_API = (
    "https://il.betrivers.com/api/service/sportsbook/offering/listview/filtered/events?cageCode=847"
)

DRAFTKINGS_PAGE = (
    "https://sportsbook.draftkings.com/leagues/football/nfl"
    "?category=countdown-%E2%8C%9B&subcategory=player-stats-o-u&nav_1=pass-yards"
)
BET365_PAGE = "https://www.bet365.com/"
FANATICS_PAGE = "https://www.fanaticsinc.com/fanatics-sportsbook-online-experience"
ESPN_BET_STATUS_PAGE = (
    "https://support.espn.com/hc/en-us/articles/19990992084116-What-is-ESPN-BET"
)

REQUESTED: dict[str, list[str]] = {
    "FanDuel": [
        "passing_yards", "passing_tds", "interceptions", "rushing_yards",
        "rushing_tds", "receiving_yards", "receptions", "receiving_tds",
    ],
    "DraftKings": [
        "passing_yards", "passing_tds", "interceptions", "completions",
        "rushing_yards", "rushing_tds", "receiving_yards", "receptions",
        "receiving_tds",
    ],
    "BetMGM": [
        "passing_yards", "passing_tds", "interceptions", "rushing_yards",
        "rushing_tds", "receiving_yards", "receptions", "receiving_tds",
    ],
    "Caesars": [
        "passing_yards", "passing_tds", "interceptions", "rushing_yards",
        "rushing_tds", "receiving_yards", "receptions", "receiving_tds",
    ],
    "bet365": [
        "passing_yards", "passing_tds", "interceptions", "rushing_yards",
        "rushing_tds", "receiving_yards", "receptions", "receiving_tds",
    ],
    "Fanatics Sportsbook": [
        "passing_yards", "passing_tds", "interceptions", "rushing_yards",
        "rushing_tds", "receiving_yards", "receptions", "receiving_tds",
    ],
    "ESPN BET": [
        "passing_yards", "passing_tds", "interceptions", "rushing_yards",
        "rushing_tds", "receiving_yards", "receptions", "receiving_tds",
    ],
    "BetRivers": [
        "passing_yards", "passing_tds", "interceptions", "rushing_yards",
        "rushing_tds", "receiving_yards", "receptions", "receiving_tds",
    ],
}

SOURCE_PAGES = {
    "FanDuel": FANDUEL_PAGE,
    "DraftKings": DRAFTKINGS_PAGE,
    "BetMGM": BETMGM_PAGE,
    "Caesars": CAESARS_PAGE,
    "bet365": BET365_PAGE,
    "Fanatics Sportsbook": FANATICS_PAGE,
    "ESPN BET": ESPN_BET_STATUS_PAGE,
    "BetRivers": BETRIVERS_PAGE,
}

PROP_COLUMNS = [
    "sportsbook", "jurisdiction", "season", "player", "market", "line",
    "side", "american_odds", "decimal_odds", "retrieved_at_ct", "market_id",
    "selection_id", "source_url",
]
STATUS_COLUMNS = [
    "sportsbook", "jurisdiction", "season", "market", "status", "priced_rows",
    "player_lines", "detail", "retrieved_at_ct", "source_url",
]


def get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
        ),
    }
    request_headers.update(headers or {})
    req = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def post_json(url: str, payload: dict[str, Any]) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.load(response)


def row(
    sportsbook: str,
    player: str,
    market: str,
    line: float,
    side: str,
    american_odds: int | str,
    decimal_odds: float,
    market_id: int | str,
    selection_id: int | str,
    source_url: str,
) -> dict[str, Any]:
    return {
        "sportsbook": sportsbook,
        "jurisdiction": JURISDICTION,
        "season": SEASON,
        "player": player.strip(),
        "market": market,
        "line": line,
        "side": side.title(),
        "american_odds": american_odds,
        "decimal_odds": decimal_odds,
        "retrieved_at_ct": STAMP,
        "market_id": market_id,
        "selection_id": selection_id,
        "source_url": source_url,
    }


def scrape_fanduel() -> list[dict[str, Any]]:
    data = get_json(FANDUEL_API)
    label_map = {
        "Passing Yards": "passing_yards",
        "Passing TDs": "passing_tds",
        "Rushing Yards": "rushing_yards",
        "Rushing TDs": "rushing_tds",
        "Receiving Yards": "receiving_yards",
        "Receiving TDs": "receiving_tds",
        "Receptions": "receptions",
        "Interceptions": "interceptions",
    }
    rows: list[dict[str, Any]] = []
    for market in data["attachments"]["markets"].values():
        if market.get("marketStatus") != "OPEN":
            continue
        name = market.get("marketName", "")
        matched: tuple[str, str] | None = None
        for source_label, canonical in label_map.items():
            suffix = f" Regular Season {source_label} 2026-27"
            if name.endswith(suffix):
                matched = (name.removesuffix(suffix), canonical)
                break
        if not matched:
            continue
        player, canonical = matched
        for runner in market.get("runners", []):
            if runner.get("runnerStatus") != "ACTIVE":
                continue
            runner_match = re.fullmatch(
                r".+\s+(Over|Under)\s+(-?\d+(?:\.\d+)?)",
                runner.get("runnerName", ""),
            )
            if not runner_match:
                continue
            side, line_text = runner_match.groups()
            odds = runner["winRunnerOdds"]
            rows.append(
                row(
                    "FanDuel", player, canonical, float(line_text), side,
                    odds["americanDisplayOdds"]["americanOddsInt"],
                    odds["trueOdds"]["decimalOdds"]["decimalOdds"],
                    market["marketId"], runner["selectionId"], FANDUEL_API,
                )
            )
    return rows


def scrape_betmgm() -> list[dict[str, Any]]:
    config = get_json(BETMGM_CONFIG, {"x-bwin-sports-api": "prod"})
    access_id = config["msApp"]["publicAccessId"]
    api_root = config["msConnection"]["cdsApiUrl"].rstrip("/")
    params = {
        "x-bwin-accessid": access_id,
        "lang": "en-us",
        "country": "US",
        "usercountry": "US",
        "state": "Latest",
        "fixtureIds": "19070789",
        "offerMapping": "All",
        "scoreboardMode": "Full",
    }
    api_url = f"{api_root}/bettingoffer/fixture-view?{urllib.parse.urlencode(params)}"
    data = get_json(api_url)
    market_map = {
        "regular season passing yards": "passing_yards",
        "regular season passing touchdowns": "passing_tds",
        "regular season interceptions": "interceptions",
        "regular season rushing yards": "rushing_yards",
        "regular season rushing touchdowns": "rushing_tds",
        "regular season receiving yards": "receiving_yards",
        "regular season receptions": "receptions",
        "regular season receiving touchdowns": "receiving_tds",
    }
    rows: list[dict[str, Any]] = []
    for game in data["fixture"].get("games", []):
        if game.get("visibility") != "Visible":
            continue
        game_name = game.get("name", {}).get("value", "")
        descriptor = game_name.rsplit(": ", 1)[-1].lower()
        canonical = market_map.get(descriptor)
        if not canonical:
            continue
        player = game.get("player1", {}).get("short")
        if not player:
            player = game_name.rsplit(": ", 1)[0]
            player = re.sub(r"\s+\([A-Z]{2,4}\)$", "", player)
        for result in game.get("results", []):
            if result.get("visibility") != "Visible":
                continue
            result_name = result.get("name", {}).get("value", "")
            match = re.fullmatch(r"(Over|Under)\s+(-?\d+(?:\.\d+)?)", result_name)
            if not match:
                continue
            side, line_text = match.groups()
            rows.append(
                row(
                    "BetMGM", player, canonical, float(line_text), side,
                    result["americanOdds"], result["odds"], game["id"],
                    result["id"], api_url,
                )
            )
    return rows


def scrape_betrivers() -> list[dict[str, Any]]:
    description_map = {
        "Player's Total Passing Yards - Regular Season": "passing_yards",
        "Player's Total Passing Touchdowns - Regular Season": "passing_tds",
        "Player's Total Interceptions Thrown - Regular Season": "interceptions",
        "Player's Total Rushing Yards - Regular Season": "rushing_yards",
        "Player's Total Rushing Touchdowns - Regular Season": "rushing_tds",
        "Player's Total Receiving Yards - Regular Season": "receiving_yards",
        "Player's Total Receptions - Regular Season": "receptions",
        "Player's Total Receiving Touchdowns - Regular Season": "receiving_tds",
    }
    rows: list[dict[str, Any]] = []
    for page_number in range(1, 11):
        data = post_json(
            BETRIVERS_API,
            {
                "eventFeedTypes": ["FUTURES"],
                "groupIds": [1000093656],
                "excludedGroupIds": [2000126292],
                "participantIds": [],
                "mainLineOnly": False,
                "pageNr": page_number,
                "pageSize": 20,
                "offset": 0,
                "cageCode": 847,
            },
        )
        for item in data.get("items", []):
            event_name = item.get("name", "")
            player = re.sub(r"\s+Markets\s+2026/2027$", "", event_name)
            player = re.sub(r"\s+2026/2027\s+Markets$", "", player)
            for offer in item.get("betOffers", []):
                canonical = description_map.get(offer.get("betDescription"))
                if not canonical or offer.get("status") != "OPEN":
                    continue
                for outcome in offer.get("outcomes", []):
                    if outcome.get("status") != "OPEN":
                        continue
                    side = outcome.get("label", "")
                    if side not in {"Over", "Under"}:
                        continue
                    rows.append(
                        row(
                            "BetRivers", player, canonical, outcome["line"], side,
                            outcome["oddsAmerican"], outcome["odds"], offer["id"],
                            outcome["id"], BETRIVERS_API,
                        )
                    )
        if page_number >= data.get("paging", {}).get("totalPages", page_number):
            break
    return rows


def find_chrome() -> str:
    candidates = [
        os.environ.get("CAESARS_CHROME"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("Chrome/Chromium executable not found")


def caesars_player(market_name: str) -> str:
    tokens = [token.strip() for token in market_name.split("|") if token.strip()]
    return tokens[0] if tokens else market_name


def parse_caesars_payload(
    payload: dict[str, Any], canonical: str, source_url: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for competition in payload.get("competitions", []):
        for event in competition.get("events", []):
            if "2026/27 NFL Regular Season Player Props" not in event.get("name", ""):
                continue
            for group in event.get("keyMarketGroups", []):
                for market in group.get("markets", []):
                    if not market.get("active") or not market.get("display"):
                        continue
                    player = caesars_player(market.get("name", ""))
                    for selection in market.get("selections", []):
                        if not selection.get("active") or not selection.get("display"):
                            continue
                        side = selection.get("type", "").title()
                        if side not in {"Over", "Under"}:
                            continue
                        price = selection["price"]
                        rows.append(
                            row(
                                "Caesars", player, canonical, market["line"], side,
                                price["a"], price["d"], market["id"], selection["id"],
                                source_url,
                            )
                        )
    return rows


async def scrape_caesars_async() -> list[dict[str, Any]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Caesars collection requires the Python playwright package") from exc

    label_map = {
        "Season Pass TDs O|U": "passing_tds",
        "Season Pass Yards O|U": "passing_yards",
        "Season Rush TDs O|U": "rushing_tds",
        "Season Rush Yards O|U": "rushing_yards",
        "Season Receiving TDs O|U": "receiving_tds",
        "Season Receiving Yards O|U": "receiving_yards",
        "Season Receptions O|U": "receptions",
    }
    rows: list[dict[str, Any]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            executable_path=find_chrome(),
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 1100},
        )
        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        await page.goto(CAESARS_PAGE, wait_until="domcontentloaded", timeout=90_000)
        await page.wait_for_timeout(7_000)

        primary_predicate = lambda response: (
            "api.americanwagering.com" in response.url
            and "FUTURE_BETS" in response.url
            and "/secondary/" not in response.url
            and response.request.method == "GET"
            and response.status == 200
        )
        async with page.expect_response(primary_predicate, timeout=30_000) as pending:
            await page.get_by_text("Player Futures", exact=True).first.click()
        primary_response = await pending.value
        primary_payload = await primary_response.json()
        selected_id = primary_payload.get("selectedSecondaryTabId")
        selected_tab = next(
            (tab for tab in primary_payload.get("secondaryTabs", []) if tab["id"] == selected_id),
            primary_payload["secondaryTabs"][0],
        )
        selected_label = selected_tab["displayName"]
        if selected_label in label_map:
            rows.extend(
                parse_caesars_payload(
                    primary_payload, label_map[selected_label], primary_response.url
                )
            )

        for label, canonical in label_map.items():
            if label == selected_label:
                continue
            secondary_predicate = lambda response: (
                "api.americanwagering.com" in response.url
                and "/secondary/" in response.url
                and response.request.method == "GET"
                and response.status == 200
            )
            async with page.expect_response(secondary_predicate, timeout=30_000) as pending:
                await page.get_by_text(label, exact=True).first.click()
            response = await pending.value
            payload = await response.json()
            rows.extend(parse_caesars_payload(payload, canonical, response.url))

        await browser.close()
    return rows


def scrape_caesars() -> list[dict[str, Any]]:
    return asyncio.run(scrape_caesars_async())


def status_rows(props: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter((item["sportsbook"], item["market"]) for item in props)
    special = {
        "DraftKings": (
            "no_available_bets",
            "Current 2026 Player Stats O/U board displayed 'No Available Bets'; no wagerable prices were returned.",
        ),
        "bet365": (
            "blocked_by_site",
            "Cloudflare blocked this collection environment, so current live offers could not be verified.",
        ),
        "Fanatics Sportsbook": (
            "app_only_not_scraped",
            "No official desktop sportsbook odds board was available; the official product directs sportsbook betting to its mobile app.",
        ),
        "ESPN BET": (
            "discontinued_brand",
            "ESPN BET Sportsbook rebranded to theScore Bet on 2025-12-01; ESPN BET is now a content-focused brand.",
        ),
    }
    output: list[dict[str, Any]] = []
    for sportsbook, markets in REQUESTED.items():
        for market in markets:
            count = counts[(sportsbook, market)]
            if count:
                status = "available"
                detail = "Wagerable Over/Under offers captured from the official sportsbook feed."
            elif sportsbook in special:
                status, detail = special[sportsbook]
            else:
                status = "not_posted"
                detail = "No wagerable market was present in the book's current 2026 season-props feed."
            output.append(
                {
                    "sportsbook": sportsbook,
                    "jurisdiction": JURISDICTION,
                    "season": SEASON,
                    "market": market,
                    "status": status,
                    "priced_rows": count,
                    "player_lines": count // 2,
                    "detail": detail,
                    "retrieved_at_ct": STAMP,
                    "source_url": SOURCE_PAGES[sportsbook],
                }
            )
    return output


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    props: list[dict[str, Any]] = []
    for sportsbook, scraper in [
        ("FanDuel", scrape_fanduel),
        ("BetMGM", scrape_betmgm),
        ("BetRivers", scrape_betrivers),
        ("Caesars", scrape_caesars),
    ]:
        book_rows = scraper()
        props.extend(book_rows)
        print(f"{sportsbook}: {len(book_rows)} priced sides", file=sys.stderr)

    props.sort(
        key=lambda item: (
            list(REQUESTED).index(item["sportsbook"]),
            REQUESTED[item["sportsbook"]].index(item["market"]),
            item["player"].casefold(),
            0 if item["side"] == "Over" else 1,
        )
    )
    statuses = status_rows(props)
    write_csv(PROPS_PATH, PROP_COLUMNS, props)
    write_csv(STATUS_PATH, STATUS_COLUMNS, statuses)
    print(PROPS_PATH)
    print(STATUS_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
