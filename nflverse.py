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
ROSTER_URL = ("https://github.com/nflverse/nflverse-data/releases/download/"
              "rosters/roster_{year}.csv")

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
            # where it is played, so the forecast has somewhere to point
            "stadium_id": r.get("stadium_id", ""),
            "stadium": r.get("stadium", ""),
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


def entry_years(season: int) -> dict[str, int]:
    """{player_id: the season he entered the league}.

    A rookie has no game logs from last season, and without this the model
    reads that absence the same way it reads a veteran who was benched: as
    time we failed to learn anything about him. He was not in the league to
    have a role. This is what lets `player_baselines` tell the two apart.

    Keyed on `gsis_id`, the same identifier the weekly stats call
    `player_id`, so the join is exact -- no name matching. The roster file
    carries one row per player per week; the entry year does not change
    inside a season, so the first row for a player wins.

    A missing file is not fatal. Without it nobody is known to be a rookie
    and the debut heuristic in `player_baselines` takes over.
    """
    try:
        text = cached_fetch(f"roster_{season}.csv",
                            ROSTER_URL.format(year=season), CURRENT_HOURS)
    except Exception:
        return {}
    out: dict[str, int] = {}
    for r in csv.DictReader(io.StringIO(text)):
        pid = (r.get("gsis_id") or "").strip()
        if not pid or pid in out:
            continue
        # rookie_year is the season he first appeared; entry_year is when he
        # was drafted or signed. They differ for a player who spent his draft
        # year on IR, and the one we want is when he first had a role to read.
        for field in ("rookie_year", "entry_year"):
            try:
                out[pid] = int(r[field])
                break
            except (KeyError, TypeError, ValueError):
                continue
    return out


# Roster status codes that mean a player is not available to play. ACT is the
# active roster and DEV the practice squad, whose players get elevated on
# Saturdays; everything else -- reserve (injured, PUP, suspended), cut,
# retired, exempt, inactive -- is off the field, and unlike an injury
# designation it never appears on the weekly report.
RESERVE = {"RES", "PUP", "SUS", "CUT", "RET", "EXE", "INA"}


def roster_status(season: int) -> dict[str, str]:
    """{player_id: roster status}, from each player's latest row.

    The weekly report only lists players who might play. A receiver placed on
    injured reserve in week 1 is on nobody's report in week 3, and without
    this the board would still see his targets as spoken for. A missing file
    is not fatal; nobody is known to be on reserve.
    """
    try:
        text = cached_fetch(f"roster_{season}.csv",
                            ROSTER_URL.format(year=season), CURRENT_HOURS)
    except Exception:
        return {}
    latest: dict[str, tuple[int, str]] = {}
    for r in csv.DictReader(io.StringIO(text)):
        pid = (r.get("gsis_id") or "").strip()
        if not pid:
            continue
        try:
            wk = int(r.get("week") or 0)
        except ValueError:
            wk = 0
        status = (r.get("status") or "").strip().upper()
        if pid not in latest or wk >= latest[pid][0]:
            latest[pid] = (wk, status)
    return {pid: status for pid, (_, status) in latest.items()}


def injuries(season: int) -> dict[tuple, dict]:
    """The season's injury reports, one entry per player per week.

    Keyed BY WEEK, because a report is about one game. The old version
    folded the whole season into one name -> status map, so a back ruled
    out in week 1 with no designation since was still "listed out" in week
    3, sitting greyed under the line the book had just posted for him. A
    week's report is the only thing that says anything about that week.

    Each entry is {status, injury, practice}:
      status    Out / Doubtful / Questionable, or "" before the Friday
                designations are posted
      injury    the body part, lowercased, for the row to say
      practice  "DNP" when he missed practice and has no designation yet --
                the one practice status worth a tag. Limited and Full are
                not injuries and just clutter every row they land on.

    Reachable two ways: (week, gsis_id) is the exact join -- it is the same
    identifier the weekly stats call player_id -- and (week, team, name) is
    the fallback. A missing file is not fatal; the board just loses its tags.
    """
    try:
        text = cached_fetch(f"injuries_{season}.csv",
                            INJURY_URL.format(year=season), CURRENT_HOURS)
    except Exception:
        return {}
    out: dict[tuple, dict] = {}
    for r in csv.DictReader(io.StringIO(text)):
        if r.get("season_type") != "REG":
            continue
        try:
            week = int(r.get("week") or 0)
        except ValueError:
            continue
        status = (r.get("report_status") or "").strip()
        practice = (r.get("practice_status") or "").strip().lower()
        practice = "DNP" if practice.startswith("did not") else ""
        if not status and not practice:
            continue                      # nothing a prop row needs to say
        hurt = (r.get("report_primary_injury") or r.get("practice_primary_injury") or "")
        entry = {"status": status, "injury": hurt.strip().lower(), "practice": practice,
                 "team": team(r.get("team"))}
        pid = (r.get("gsis_id") or "").strip()
        name = (r.get("full_name") or "").strip().lower()
        if pid:
            out[(week, pid)] = entry
        if name:
            out[(week, team(r.get("team")), name)] = entry
    return out
