"""Assembles the board: joins market lines to our projections, one entry per
posted prop, grouped by game."""
from __future__ import annotations

import collections
import datetime as dt

import depth
import lines
import model
import nflverse

LOOKBACK_SEASONS = 2

# BettingPros uses a few different abbreviations than nflverse.
BP_TEAM = {"JAC": "JAX", "WSH": "WAS", "LAR": "LA", "LVR": "LV",
           "TAM": "TB", "NOR": "NO", "SFO": "SF", "KAN": "KC",
           "GNB": "GB", "NWE": "NE"}


def bp_team(abbr: str) -> str:
    a = (abbr or "").strip().upper()
    return nflverse.team(BP_TEAM.get(a, a))


def load_stats(season: int) -> dict:
    """The slow half: nflverse pulls plus the derived baselines and defense
    profiles. Depends only on the season, so it caches independently of which
    week or book is on screen."""
    years = list(range(season - LOOKBACK_SEASONS + 1, season + 1))
    weeks = nflverse.player_weeks(years, season)
    # Weeks players were ruled out, so the confidence meter can hold a player
    # to the time he was available rather than to the whole calendar.
    absences = nflverse.out_weeks(years, season)
    # The season each player came into the league, so a rookie's missing
    # prior season reads as "not eligible" rather than "we never saw him".
    entry = nflverse.entry_years(season)
    baselines = model.player_baselines(weeks, season, absences, entry)
    # `weeks` itself is deliberately NOT returned. Nothing downstream reads
    # the raw game logs -- the baselines and the defense profiles are the
    # whole of what they produce -- and it is twenty thousand rows that the
    # cache would otherwise pickle and carry in memory for every session.
    # The depth chart is what turns "listed out" into "so his carries go to
    # the next back". A board without it still builds; it just cannot see
    # past the injury.
    try:
        chart = depth.chart(season)
    except Exception:
        chart = {}
    return {
        "baselines": baselines,
        "defense": model.defense_profiles(weeks, season),
        "priors": model.spread_priors(baselines),
        "team_att": model.team_pass_attempts(weeks, season),
        "schedule": nflverse.schedule(season),
        "injuries": nflverse.injuries(season),
        "roster_status": nflverse.roster_status(season),
        "depth": chart,
        "by_name": _name_index(baselines),
    }


def _unavailable(injuries: dict, roster_status: dict[str, str], week: int) -> dict[str, str]:
    """{player_id: why} for everyone off the field this week: out or
    doubtful on the week's report, or on a reserve list per the roster. The
    report wins when both say something."""
    gone = {pid: status for pid, status in roster_status.items()
            if status in nflverse.RESERVE}
    for key, entry in injuries.items():
        if (len(key) == 2 and key[0] == week
                and entry.get("status", "").lower() in ("out", "doubtful")):
            gone[key[1]] = entry["status"].lower()
    return gone


def current_week(schedule: list[dict]) -> int:
    """The week whose games have not all kicked off yet.

    Lives here rather than in app.py because the nightly refresh has to reach
    the same answer -- warming last week's lines every morning would leave
    the board pulling the new week's board from scratch on first open, which
    is the whole thing the refresh exists to avoid.
    """
    today = dt.date.today().isoformat()
    upcoming = [g["week"] for g in schedule if g["gameday"] >= today]
    return min(upcoming) if upcoming else max(g["week"] for g in schedule)


def _name_index(baselines: dict) -> dict:
    """(normalised name, team) and normalised name alone -> baseline. Players
    change teams, so the name-only key is the fallback."""
    idx: dict = {}
    for b in baselines.values():
        key = lines.norm_name(b["name"])
        idx[(key, b["team"])] = b
        # keep the player with more recent playing time on a bare-name clash
        prev = idx.get(key)
        if prev is None or b["weighted_games"] > prev["weighted_games"]:
            idx[key] = b
    return idx


def build(season: int, week: int, book: str, stats: dict,
          market_lines: list[dict], weather: dict | None = None) -> dict:
    """Returns {'games': [...], 'unmatched': n, 'league_avg_total': x}.

    `weather` is weather.forecasts() for the week, {game_id: forecast}. It is
    optional on purpose: a board without a forecast is still a board, and
    the refresh log is where a failed weather pull gets reported.
    """
    weather = weather or {}
    sched = {}
    for g in stats["schedule"]:
        if g["week"] == week:
            sched[(g["away"], g["home"])] = g

    games_by_pair = {}
    for g in sched.values():
        games_by_pair[frozenset((g["away"], g["home"]))] = g

    totals = [g["total"] for g in sched.values() if g["total"]]
    league_avg_team_total = (sum(totals) / len(totals) / 2) if totals else 22.5

    defense = stats["defense"]
    priors = stats["priors"]
    by_name = stats["by_name"]
    injuries = stats["injuries"]

    # Who is off the field this week, and where their touches go. Worked out
    # once per team from the week's report, the reserve list and the depth
    # chart; a player whose volume changes projects off the adjusted copy.
    gone = _unavailable(injuries, stats.get("roster_status") or {}, week)
    teams = (stats.get("depth") or {}).get("teams") or {}
    charted = {p["id"] for chart in teams.values() for rows in chart.values() for p in rows}
    adjusted: dict[str, dict] = {}
    for t, chart in teams.items():
        adjusted.update(model.next_man_up(chart, stats["baselines"], gone, t, charted, week,
                                          (stats.get("team_att") or {}).get(t, 0.0)))

    buckets: dict[str, list[dict]] = collections.defaultdict(list)
    unmatched: set[str] = set()

    for ln in market_lines:
        team = bp_team(ln["team"])
        opp = bp_team(ln["opponent"])
        game = games_by_pair.get(frozenset((team, opp)))
        if game is None or ln["line"] is None:
            continue

        base = by_name.get((ln["player_key"], team)) or by_name.get(ln["player_key"])
        if base is None:
            unmatched.add(ln["player"])
            continue
        base = adjusted.get(base["player_id"], base)
        promoted = bool((base.get("role_change") or {}).get("promoted"))

        dprof = defense.get(opp)
        if dprof is None:
            continue

        implied = game["implied_home"] if team == game["home"] else game["implied_away"]
        implied_opp = game["implied_away"] if team == game["home"] else game["implied_home"]
        script = model.game_script(implied, implied_opp, league_avg_team_total,
                                   weather.get(game["game_id"]))

        proj_all = model.project(base, dprof, script)
        market = ln["market"]
        projection = proj_all[market]

        sd = (model.spread_for(base, market, projection, priors)
              if market in model.YARDAGE else 0.0)
        our = model.cover_probability(market, projection, ln["line"], sd)
        mkt = lines.no_vig(ln["over"], ln["under"])

        # The call comes from our number against the line, NOT from our number
        # against the book's. The price is a reference printed beside the
        # read; it is not allowed to pick the side or set the ranking.
        one_sided = market in lines.ONE_SIDED
        if one_sided or our >= 0.5:
            side, edge = "OVER", our - mkt
        else:
            side, edge = "UNDER", mkt - our

        conf = model.confidence(base, dprof)
        if promoted:
            conf *= model.PROMOTED_CONF     # a role we inferred, not one we watched
        conv = model.conviction(market, our, conf)
        why = model.drivers(base, dprof, script, market, proj_all, opp)

        playable, reason = model.role_check(base, market, projection, ln["line"],
                                            our_prob=our, market_prob=mkt)
        # THIS week's report, by player id first and name second. Out and
        # doubtful set the prop aside; questionable, or a missed practice
        # before the designations are out, is a tag on the row and nothing
        # more -- that is a judgement for whoever is reading it.
        hurt = (injuries.get((week, base["player_id"]))
                or injuries.get((week, team, base["name"].lower())) or {})
        status = hurt.get("status", "") or hurt.get("practice", "")
        if hurt.get("injury"):
            status = f"{status} · {hurt['injury']}" if status else ""
        if hurt.get("status", "").lower() in ("out", "doubtful"):
            playable = False
            reason = f"listed {hurt['status'].lower()}" + (
                f" ({hurt['injury']})" if hurt.get("injury") else "")

        buckets[game["game_id"]].append({
            "market": market,
            "market_label": lines.MARKET_LABELS[market],
            "player": base["name"],
            "position": base["position"] or ln["position"],
            "headshot": base["headshot"],
            "team": team,
            "opponent": opp,
            "line": ln["line"],
            "over": ln["over"],
            "under": ln["under"],
            "one_sided": one_sided,
            "projection": projection,
            "sd": sd,
            "our_prob": our,
            "market_prob": mkt,
            "side": side,
            "edge": edge,
            "confidence": conf,
            "conviction": conv,
            "drivers": why,
            "delta": projection - ln["line"] if market in model.YARDAGE else None,
            "def_mult": _mult_for(market, dprof, base),
            "cur_share": base["cur_share"],
            "weighted_games": base["weighted_games"],
            "eff_games": base["eff_games"],
            "games_cur": base["games_cur"],
            "thin": base["eff_games"] < model.MIN_EFF_GAMES,
            "rookie": base.get("rookie", False),
            "promoted": promoted,
            "playable": playable,
            "reason": reason,
            "status": status,
            "script": script,
        })

    out_games = []
    for gid, props in buckets.items():
        game = next(g for g in sched.values() if g["game_id"] == gid)
        _propagate_role_flags(props)
        # Readable props first, then what we think a player DOES, then how
        # strongly we hold it.
        #
        # Not by edge -- a big number against the book usually means we are
        # missing something, and it is not what this board is for. And not by
        # conviction alone either: "confidently under a small line" scores as
        # high as "confidently productive", so a third-string back projected
        # for 3 rushing yards against a 5.5 line led the panel ahead of the
        # players the game is actually about. Affirmative reads come first;
        # the unders are still there, underneath.
        props.sort(key=lambda p: (not p["playable"],
                                  p["side"] != "OVER",
                                  -p["conviction"]))
        out_games.append({
            **game,
            "props": props,
            "weather": weather.get(gid),
            "def_away": defense.get(game["away"], {}),
            "def_home": defense.get(game["home"], {}),
            "best_conviction": max((p["conviction"] for p in props
                                    if p["playable"] and p["side"] == "OVER"),
                                   default=0.0),
        })
    out_games.sort(key=lambda g: (g["gameday"], g["gametime"]))

    return {
        "games": out_games,
        "unmatched": sorted(unmatched),
        "league_avg_team_total": league_avg_team_total,
        "book": book,
        "week": week,
        "season": season,
    }


def _mult_for(market: str, dprof: dict, base: dict) -> float:
    """The single defense multiplier that moved this particular market, so the
    board can show what the matchup did to the number."""
    if market in ("pass_yds",):
        return dprof.get("pass", 1.0)
    if market in ("rush_yds",):
        return dprof.get("rush", 1.0)
    if market in ("rec_yds",):
        return dprof.get("vs_" + base["position_group"], dprof.get("pass", 1.0))
    if market == "rush_rec_yds":
        return (dprof.get("rush", 1.0)
                + dprof.get("vs_" + base["position_group"], dprof.get("pass", 1.0))) / 2
    if market == "pass_tds":
        return dprof.get("pass_td", 1.0)
    if market == "interceptions":
        return dprof.get("int", 1.0)
    return (dprof.get("rush_td", 1.0) + dprof.get("pass_td", 1.0)) / 2


def _propagate_role_flags(props: list[dict]) -> None:
    """If we cannot read a player's role, that applies to all of his props.

    The role check compares a line to our usage read, which only works on the
    yardage markets. But a quarterback whose passing-yards line says he is
    starting when our logs say he is a backup has an unreadable interception
    prop too -- same missing information, different market.
    """
    flagged: dict[str, str] = {}
    for p in props:
        if not p["playable"] and p["reason"]:
            flagged.setdefault(p["player"], p["reason"])
    for p in props:
        if p["playable"] and p["player"] in flagged:
            p["playable"] = False
            p["reason"] = flagged[p["player"]]


def scorers(data: dict, limit: int = 40) -> list[dict]:
    """Everyone on the slate, ranked by our own probability that they find
    the end zone. This is the plain question the board exists to answer, so
    it is ranked on our number and nothing else -- the book's price rides
    along as a reference column."""
    found = [p for g in data["games"] for p in g["props"]
             if p["market"] == "anytime_td" and p["playable"]]
    found.sort(key=lambda p: -p["our_prob"])
    return found[:limit]


def leaders(data: dict, market: str, limit: int = 25) -> list[dict]:
    """Ranked by our projection for one yardage or count market, biggest
    first -- who we think puts up the most, regardless of where the line
    sits."""
    rows = [p for g in data["games"] for p in g["props"]
            if p["market"] == market and p["playable"]]
    rows.sort(key=lambda p: -p["projection"])
    return rows[:limit]
