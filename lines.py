"""DraftKings and FanDuel prop lines via BettingPros.

Undocumented public web API -- the key below is the one bettingpros.com ships
in its own frontend. No account, no monthly quota. If it ever stops working
this is the only module that needs replacing; notes/DATA_SOURCES.md records a
Rotowire fallback that covers four of the seven markets.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request

API = "https://api.bettingpros.com/v3/"
API_KEY = "CHi8Hy5CEE4khd46XNYL23dCFX96oUdw6qOt1Dnh"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")

BOOKS = {"DraftKings": 12, "FanDuel": 10, "Consensus": 0}

# our market key -> BettingPros market_id
MARKETS = {
    "pass_yds": 103,
    "rush_yds": 107,
    "rec_yds": 105,
    "rush_rec_yds": 406,
    "pass_tds": 102,
    "interceptions": 101,
    "anytime_td": 78,
}
# markets priced as a single "yes" rather than an over/under pair
ONE_SIDED = {"anytime_td"}

MARKET_LABELS = {
    "pass_yds": "Passing yards",
    "rush_yds": "Rushing yards",
    "rec_yds": "Receiving yards",
    "rush_rec_yds": "Rush + rec yards",
    "pass_tds": "Passing TDs",
    "interceptions": "Interceptions",
    "anytime_td": "Anytime TD",
}

_SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$", re.I)


def norm_name(name: str) -> str:
    """Join key between BettingPros and nflverse spellings: strip accents,
    punctuation and generational suffixes."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("'", "").replace(".", "").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = _SUFFIX.sub("", s)
    return s.lower()


def _get(path: str) -> dict:
    req = urllib.request.Request(API + path,
                                 headers={"x-api-key": API_KEY, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.load(r)


def events(season: int, week: int) -> list[dict]:
    q = urllib.parse.urlencode({"sport": "NFL", "season": season, "week": week})
    return _get(f"events?{q}").get("events", [])


def _offers(market_id: int, event_ids: str) -> list[dict]:
    """`limit` is capped at 10 by the API, so every market has to be paged."""
    out, page = [], 1
    while True:
        q = urllib.parse.urlencode({
            "sport": "NFL", "market_id": market_id,
            "event_id": event_ids, "limit": 10, "page": page,
        })
        data = _get(f"offers?{q}")
        out += data.get("offers", [])
        pages = data.get("_pagination", {}).get("total_pages", 1)
        if page >= pages or page > 60:
            return out
        page += 1
        time.sleep(0.1)


def _price(books: list[dict], book_id: int) -> tuple[float | None, float | None]:
    """(line, american odds) for one book, or (None, None) if it isn't posted."""
    for b in books or []:
        if b.get("id") != book_id:
            continue
        for ln in b.get("lines") or []:
            if ln.get("active") is False:
                continue
            return ln.get("line"), ln.get("cost")
    return None, None


def fetch(season: int, week: int, book_id: int,
          markets: list[str] | None = None) -> list[dict]:
    """Every posted prop for one week at one book, normalised to:
    {market, player, player_key, team, opponent, line, over, under}
    where `over`/`under` are American odds. One-sided markets carry the price
    in `over` and leave `under` as None.
    """
    evs = events(season, week)
    if not evs:
        return []
    ids = ":".join(str(e["id"]) for e in evs)
    # event id -> (away, home); both arrive as plain team abbreviations
    teams_by_event = {e["id"]: (str(e.get("visitor") or "").upper(),
                                str(e.get("home") or "").upper()) for e in evs}

    out: list[dict] = []
    for key in (markets or list(MARKETS)):
        mid = MARKETS[key]
        for offer in _offers(mid, ids):
            parts = {str(p.get("id")): p for p in offer.get("participants", [])}
            sels = offer.get("selections", [])

            if key in ONE_SIDED:
                for s in sels:
                    p = parts.get(str(s.get("participant")))
                    if not p:
                        continue
                    line, odds = _price(s.get("books"), book_id)
                    if odds is None:
                        continue
                    out.append(_row(key, p, offer, line, odds, None, teams_by_event))
                continue

            # two-sided: one participant, an Over selection and an Under
            p = next(iter(parts.values()), None)
            if not p:
                continue
            over = under = None
            line = None
            for s in sels:
                lab = (s.get("label") or "").lower()
                ln, odds = _price(s.get("books"), book_id)
                if odds is None:
                    continue
                if lab.startswith("over"):
                    over, line = odds, ln if ln is not None else line
                elif lab.startswith("under"):
                    under = odds
                    line = ln if line is None else line
            if over is None or line is None:
                continue
            out.append(_row(key, p, offer, line, over, under, teams_by_event))
    return out


def _row(market: str, participant: dict, offer: dict,
         line, over, under, teams_by_event: dict) -> dict:
    meta = participant.get("player") or {}
    name = participant.get("name") or ""
    team = (meta.get("team") or "").upper()
    away, home = teams_by_event.get(offer.get("event_id"), ("", ""))
    return {
        "market": market,
        "player": name,
        "player_key": norm_name(name),
        "position": (meta.get("position") or "").upper(),
        "team": team,
        "opponent": home if team == away else away,
        "away": away,
        "home": home,
        "event_id": offer.get("event_id"),
        "line": float(line) if line is not None else None,
        "over": float(over) if over is not None else None,
        "under": float(under) if under is not None else None,
    }


def implied(american: float) -> float:
    """American odds -> raw implied probability (still carrying the vig)."""
    return -american / (-american + 100) if american < 0 else 100 / (american + 100)


def no_vig(over: float, under: float | None, one_sided_hold: float = 0.06) -> float:
    """Market probability of the OVER with the book's margin removed.

    Two-sided prices normalise against each other. A one-sided price (anytime
    TD) has nothing to normalise against, so it gets a flat haircut for the
    typical hold on that market -- an estimate, and the board says so.
    """
    po = implied(over)
    if under is None:
        return po * (1 - one_sided_hold)
    pu = implied(under)
    return po / (po + pu) if (po + pu) else po
