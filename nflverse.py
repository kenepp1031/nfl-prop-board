"""nflverse feeds: weekly player stats, the schedule, and the injury report.

The weekly stats live on the `stats_player` release, NOT the older
`player_stats` one -- that release stopped being updated after 2024. See
notes/DATA_SOURCES.md.
"""
from __future__ import annotations

import collections
import csv
import io

from common import cached_fetch

WEEKLY_URL = ("https://github.com/nflverse/nflverse-data/releases/download/"
              "stats_player/stats_player_week_{year}.csv")
GAMES_URL = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
INJURY_URL = ("https://github.com/nflverse/nflverse-data/releases/download/"
              "injuries/injuries_{year}.csv")

# The current season's file is rewritten after every game; older seasons never
# change again, so they can sit in the cache for a week.
CURRENT_HOURS = 6
HISTORY_HOURS = 24 * 7

# Teams that relocated or rebranded inside our lookback, mapped to today's abbr.
ALIASES = {"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA", "OAK ": "LV"}


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def team(abbr: str) -> str:
    a = (abbr or "").strip().upper()
    return ALIASES.get(a, a)


def player_weeks(years: list[int], current_year: int) -> list[dict]:
    """One row per player per game, regular season only, numeric fields coerced."""
    keep_num = (
        "attempts", "completions", "passing_yards", "passing_tds",
        "passing_interceptions", "sacks_suffered", "passing_air_yards",
        "carries", "rushing_yards", "rushing_tds",
        "targets", "receptions", "receiving_yards", "receiving_tds",
        "receiving_air_yards", "target_share", "air_yards_share", "wopr",
        "fantasy_points_ppr",
    )
    rows: list[dict] = []
    for year in years:
        hours = CURRENT_HOURS if year >= current_year else HISTORY_HOURS
        text = cached_fetch(f"stats_player_week_{year}.csv",
                            WEEKLY_URL.format(year=year), hours)
        for r in csv.DictReader(io.StringIO(text)):
            if r.get("season_type") != "REG":
                continue
            row = {
                "season": int(r["season"]),
                "week": int(r["week"]),
                "game_id": r.get("game_id", ""),
                "player_id": r["player_id"],
                "name": r["player_display_name"],
                "position": (r.get("position") or "").upper(),
                "position_group": (r.get("position_group") or "").upper(),
                "team": team(r.get("team")),
                "opponent": team(r.get("opponent_team")),
                "headshot": r.get("headshot_url") or "",
            }
            for f in keep_num:
                row[f] = _num(r.get(f))
            rows.append(row)
    return rows


def schedule(season: int) -> list[dict]:
    """Every game of one season with the closing spread and total.

    `spread_line` is the HOME team's spread, positive meaning home is favoured,
    so the implied team totals are total/2 +/- spread/2.
    """
    text = cached_fetch("games.csv", GAMES_URL, CURRENT_HOURS)
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("season") != str(season) or r.get("game_type") not in (None, "", "REG"):
            continue
        spread = _num(r.get("spread_line"))
        total = _num(r.get("total_line"))
        out.append({
            "game_id": r["game_id"],
            "week": int(r["week"]),
            "gameday": r.get("gameday", ""),
            "gametime": r.get("gametime", ""),
            "away": team(r.get("away_team")),
            "home": team(r.get("home_team")),
            "away_score": r.get("away_score") or None,
            "home_score": r.get("home_score") or None,
            "spread": spread,
            "total": total,
            "roof": r.get("roof", ""),
            "divisional": r.get("div_game") == "1",
            # implied team totals, the scoring environment each side is priced into
            "implied_home": total / 2 + spread / 2 if total else 0.0,
            "implied_away": total / 2 - spread / 2 if total else 0.0,
        })
    return out


def out_weeks(years: list[int], current_year: int) -> dict[str, set[tuple]]:
    """{player_id: {(season, week), ...}} -- the weeks a player was ruled off
    the field.

    A week a player was OUT is not a week we failed to learn something about
    his role. He was not available to have one. The confidence meter takes
    these weeks off the bottom of its fraction so a starter who missed half a
    season hurt is not read as less known than the backup who replaced him.

    Keyed on `gsis_id`, which is the same identifier the weekly stats call
    `player_id`, so the join is exact -- no name matching anywhere in it.
    A missing file is not fatal; it just means nobody gets excused.
    """
    gone: dict[str, set[tuple]] = collections.defaultdict(set)
    for year in years:
        hours = CURRENT_HOURS if year >= current_year else HISTORY_HOURS
        try:
            text = cached_fetch(f"injuries_{year}.csv",
                                INJURY_URL.format(year=year), hours)
        except Exception:
            continue
        for r in csv.DictReader(io.StringIO(text)):
            if r.get("season_type") != "REG":
                continue
            # Doubtful counts with Out: a player listed doubtful who then has
            # no stat line did not play, and the caller only excuses weeks he
            # has no game log for anyway.
            if (r.get("report_status") or "").strip().lower() not in ("out", "doubtful"):
                continue
            pid = (r.get("gsis_id") or "").strip()
            if pid and r.get("week"):
                gone[pid].add((int(r["season"]), int(r["week"])))
    return dict(gone)


def injuries(season: int) -> dict[tuple[str, str], str]:
    """{(team, lowercased player name): status}. Missing file is not fatal --
    the board just loses its OUT/QUESTIONABLE tags."""
    try:
        text = cached_fetch(f"injuries_{season}.csv",
                            INJURY_URL.format(year=season), CURRENT_HOURS)
    except Exception:
        return {}
    # Only the game-status designations. practice_status carries strings like
    # "Full Participation In Practice", which is not an injury and just
    # clutters every row it lands on.
    real = {"out", "doubtful", "questionable"}
    out: dict[tuple[str, str], str] = {}
    for r in csv.DictReader(io.StringIO(text)):
        status = (r.get("report_status") or "").strip()
        name = (r.get("full_name") or "").strip().lower()
        if status.lower() in real and name:
            out[(team(r.get("team")), name)] = status
    return out
