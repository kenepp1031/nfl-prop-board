"""Defense-adjusted prop projections.

The shape of every projection is the same:

    projection = player baseline  x  opponent defense  x  game environment

Player baseline  - recency-weighted per-game volume and efficiency.
Opponent defense - what that defense allows per play relative to league
                   average, separately for the run and the pass, and split by
                   the position being covered. This is the run-funnel /
                   pass-funnel read.
Game environment - the implied team total and the game script the spread
                   implies: favourites run more and throw less.

Nothing here is fitted to past results. Every coefficient is a round number
chosen for what it means, and they are all collected at the top of the file.
"""
from __future__ import annotations

import collections
import math

# --- weighting -------------------------------------------------------------
# Props are a bet on this week's role, so the current season has to lead. At
# 0.45 and 0.88 a week-3 read is roughly 40% this season / 60% last, and by
# midseason last year barely registers. Weighting last season the way a
# season-long model would leaves the board pricing last year's depth chart.
SEASON_WEIGHT = {0: 1.00, 1: 0.45, 2: 0.15}   # 0 = current season, 1 = last, ...
GAME_DECAY = 0.88                              # per game further back
MIN_EFF_GAMES = 3.0                            # below this a player is "thin"

# Weeks a player was ruled OUT are taken off the bottom of the confidence
# fraction rather than counted against him -- see player_baselines. An
# injury history can excuse time, but not the whole scale: a player who was
# out all year and has played once is still someone we barely know.
MAX_EXCUSED = 0.5                              # most of the reference injuries can forgive

# Weeks before a player's first NFL game come off that same bottom, and
# unlike injuries they come off in full: a rookie did not fail to show us
# last season, he was not eligible to play in it. Measuring him against a
# two-season calendar halved his meter for the crime of being new, which is
# the single reason no rookie ever cleared the board's default threshold.
#
# The floor is what stops that becoming a free pass. However short his
# career, a player is measured against at least this much recent full-weight
# playing time, so a Week 1 debut still reads as someone we barely know and
# only a rookie who has actually played a quarter of a season reads as fully
# seen. Three games, in the weights the decay gives the three most recent.
DEBUT_MIN_GAMES = 3

# --- player rate shrinkage -------------------------------------------------
# A player's own efficiency and scoring rates are pulled toward his position
# group's average until he has enough games to have earned them. Without this
# a rookie who scored once in two games reads as a 0.5 TD/game threat.
K_PLAYER_GAMES = 6.0

# --- how sure are we of our own number -------------------------------------
# Game-to-game spread is not the only uncertainty; the projection itself is an
# estimate off a finite sample, and the model is imperfect even with a full
# one. Both get added to the spread a line is priced against.
MODEL_ERROR_CV = 0.12

# --- role disagreement -----------------------------------------------------
# When the market's line sits far outside what a player's usage history can
# support, the book is pricing a role we cannot see -- a promotion, an injury
# ahead of him on the depth chart, a package change. That is missing
# information, not an edge, so those props are flagged and set aside.
ROLE_LOW, ROLE_HIGH = 0.55, 1.85
# Anytime touchdown is checked against the book's price instead of a line.
ATD_LONGSHOT = 0.15      # only police prices the book has already written off
ATD_MAX_RATIO = 3.0      # how far above that price our read may sit

# A thin sample used to set a player aside outright, whatever the line said.
# That is the wrong test: it answers "how long is his career" when the
# question is "does the book think he has a role we cannot see". It set
# aside every prop of every rookie on the board, including the ones the
# market agreed with to the yard. A thin player now faces the same test as
# anyone else, just a stricter one -- less room to disagree before we admit
# we are the ones missing something.
THIN_ROLE_LOW, THIN_ROLE_HIGH = 0.70, 1.45
THIN_ATD_MAX_RATIO = 2.0
# Below this there is no usage to check a line against at all. One game is
# not a role, so it is still set aside -- but it is one game, not three.
MIN_ROLE_GAMES = 1.5

# --- defense shrinkage -----------------------------------------------------
# A rate measured off n plays is pulled toward league average by n/(n+K).
# K is "how many plays before we half-believe it", in plays faced.
K_PASS_PLAYS = 250
K_RUSH_PLAYS = 130
K_TD_PLAYS = 300
DEF_MULT_CLAMP = (0.80, 1.25)                  # one odd game can't run away with it

# --- game script -----------------------------------------------------------
# Per point of pricing margin. A 7-point favourite throws ~8% less and runs
# ~10% more than the same team in a coin-flip game.
PASS_VOLUME_PER_POINT = 0.012
RUSH_VOLUME_PER_POINT = 0.015
SCRIPT_CLAMP = (0.82, 1.22)

# --- weather ---------------------------------------------------------------
# Wind is the one that matters. Under about ten miles an hour nobody plays
# differently; over it every extra mile an hour makes the throw harder and
# the run more attractive. At 20 mph this puts yards per throw 10% down,
# throws 6% down and carries 8% up -- a windy day reads like being a
# five-point favourite, on top of whatever the spread already says. It is
# the sustained wind over the game, not the gust, that these are per.
WIND_CALM_MPH = 10.0
WIND_PASS_EFF_PER_MPH = 0.010
WIND_PASS_VOL_PER_MPH = 0.006
WIND_RUSH_VOL_PER_MPH = 0.008
WIND_CAP_MPH = 30.0                            # past this the number is a guess anyway
# Rain and snow: fewer throws, worse throws. Rain is mild -- a wet ball
# costs a few percent -- and snow is a different sport, about three times it.
RAIN_PASS_EFF, RAIN_PASS_VOL, RAIN_RUSH_VOL = 0.97, 0.97, 1.04
SNOW_PASS_EFF, SNOW_PASS_VOL, SNOW_RUSH_VOL = 0.92, 0.90, 1.10
RAIN_MIN_PROB = 50.0                           # percent, at its worst over the game
RAIN_MIN_INCHES = 0.05                         # over the game
SNOW_MIN_INCHES = 0.1
# Below freezing the ball is harder to grip and catch. Small, and it is the
# only thing temperature does here -- heat changes pace, not props.
FREEZING_F = 32.0
COLD_PASS_EFF = 0.97
WEATHER_CLAMP = (0.75, 1.25)
# Scoring is deliberately NOT touched by any of this. The scoring multiplier
# comes from the implied team total, and the market's total already has the
# forecast in it; docking it again would count the wind twice.

# --- next man up -----------------------------------------------------------
# When a player is out, the touches he would have had do not vanish; the
# depth chart says where they go. The man directly below him on the chart
# takes NEXT_MAN_SHARE of them and the rest is spread over the group in
# proportion to what each player already gets -- a lost lead back is mostly
# the second back's carries, a lost receiver is mostly everyone else's
# targets. The next man is never handed more than the absentee had, and
# nobody in the pool gains more than POOL_GAIN_CAP of his own volume.
#
# "Directly below him" is by volume, not by ESPN's order: a back on reserve
# gets moved to the bottom of the chart, and read literally that would send
# a second back's carries to the lead back. The chart's order decides who
# has been promoted into the lineup, and who the quarterback is.
#
# Quarterback is not a redistribution at all. One man takes every snap, so
# the healthy man the chart puts first is projected on a starter's
# attempts: the team's own passes a game, less the few that go elsewhere,
# or the biggest passer the team has lost this season, whichever is more --
# if either beats his own history. A traded starter with one partial game
# here and a backup pressed into the job both read as backups off their
# logs, and both are exactly who the book has just posted a starter's line
# for. Only a passer who is out, on reserve or exempt has lost a role; a
# cut or retired one's attempts belong to the past.
STARTER_ATT_SHARE = 0.95    # of the team's pass attempts that the starter throws
#
# Each recipient is only corrected for the part of his read that was built
# with the absentee on the field: his current-season share times the
# absentee's share of this season's games, plus his last-season share times
# the absentee's of last season's, and that second part only if both of
# them were on this team last season. A receiver on reserve since August
# has been missing from every current-season log his teammates have.
STARTERS = {"QB": 1, "RB": 1, "WR": 3, "TE": 1}
NEXT_MAN_SHARE = {"RB": 0.75, "WR": 0.35, "TE": 0.55}
VACATED_KEYS = {"RB": ("car", "tgt"), "WR": ("tgt",), "TE": ("tgt",)}
QB_VACATES = {"out", "doubtful", "RES", "EXE", "PUP", "SUS"}
POOL_GAIN_CAP = 0.35        # of the recipient's own volume
MIN_VACATED = 1.0           # touches a game; below this nobody notices he is gone
MIN_ROLE_NOTE = 0.5         # touches a game before the row bothers to say so
PROMOTED_CONF = 0.80        # a role read off a depth chart is not a role we have watched

MARKETS = ("pass_yds", "rush_yds", "rec_yds", "rush_rec_yds",
           "pass_tds", "interceptions", "anytime_td")
YARDAGE = ("pass_yds", "rush_yds", "rec_yds", "rush_rec_yds")
COUNT = ("pass_tds", "interceptions")


# --------------------------------------------------------------------------
# small maths helpers
# --------------------------------------------------------------------------
def phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def poisson_over(lam: float, line: float) -> float:
    """P(X > line) for X ~ Poisson(lam). Lines are half-points, so this is
    P(X >= ceil(line))."""
    if lam <= 0:
        return 0.0
    need = math.ceil(line)
    below, term = 0.0, math.exp(-lam)
    for k in range(need):
        if k:
            term *= lam / k
        below += term
    return max(0.0, min(1.0, 1 - below))


def _shrink(raw: float, n: float, k: float) -> float:
    """Pull a ratio toward 1.0 when it rests on few plays."""
    if n <= 0:
        return 1.0
    return 1.0 + (raw - 1.0) * (n / (n + k))


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _safe(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den else default


# --------------------------------------------------------------------------
# weighting
# --------------------------------------------------------------------------
def timeline(weeks: list[dict]) -> list[tuple]:
    """Every (season, week) the data covers, oldest first. This is the
    calendar the decay is measured against."""
    return sorted({(r["season"], r["week"]) for r in weeks})


def game_weights(rows: list[dict], current_season: int,
                 calendar: list[tuple] | None = None) -> list[float]:
    """A weight per row, from the season it belongs to and how many weeks
    back it is.

    Two things this has to get right, both of which were wrong once:

    The decay is per GAME, not per row. A defense contributes ~25 opposing
    player-rows per game, so decaying by row index would put 0.88^500 on last
    season and throw the whole sample away.

    The decay is measured against the CALENDAR, not against the player's own
    last appearance. Without `calendar` a player who has not taken a snap
    since last season has his final 2025 game treated as the most recent
    game there is, so his weights come out flat and his effective sample
    comes out LARGER than an active starter's -- which is backwards, and it
    fed straight into the confidence meter.
    """
    games = sorted({(r["season"], r["week"]) for r in rows})
    cal = calendar or games
    last = len(cal) - 1
    pos = {g: i for i, g in enumerate(cal)}
    by_game = {}
    for g in games:
        season_w = SEASON_WEIGHT.get(current_season - g[0], 0.0)
        back = last - pos.get(g, last)
        by_game[g] = season_w * (GAME_DECAY ** back)
    return [by_game[(r["season"], r["week"])] for r in rows]


# --------------------------------------------------------------------------
# defense profiles
# --------------------------------------------------------------------------
def defense_profiles(weeks: list[dict], current_season: int) -> dict[str, dict]:
    """For each defense, multipliers against league average. Above 1.0 means
    the defense gives up more than average -- good for the offense facing it.

    Efficiency (yards per play) leads rather than yards per game, because
    yards allowed per game is mostly a function of how often a defense is on
    the field, which is the opponent's doing, not theirs.
    """
    cal = timeline(weeks)
    by_def: dict[str, list[dict]] = collections.defaultdict(list)
    for r in weeks:
        if r["opponent"]:
            by_def[r["opponent"]].append(r)

    acc: dict[str, dict] = {}
    for d, rows in by_def.items():
        rows.sort(key=lambda r: (r["season"], r["week"]))
        weights = game_weights(rows, current_season, cal)
        a: dict[str, float] = collections.defaultdict(float)
        games: set[tuple] = set()
        for r, w in zip(rows, weights):
            if w <= 0:
                continue
            games.add((r["season"], r["week"]))
            a["att"] += w * r["attempts"]
            a["pass_yds"] += w * r["passing_yards"]
            a["pass_td"] += w * r["passing_tds"]
            a["int"] += w * r["passing_interceptions"]
            a["car"] += w * r["carries"]
            a["rush_yds"] += w * r["rushing_yards"]
            a["rush_td"] += w * r["rushing_tds"]
            pg = r["position_group"] if r["position_group"] in ("RB", "WR", "TE") else None
            if pg:
                a["rec_yds_" + pg] += w * r["receiving_yards"]
                a["tgt_" + pg] += w * r["targets"]
        a["games"] = float(len(games))
        acc[d] = a

    lg: dict[str, float] = collections.defaultdict(float)
    for a in acc.values():
        for k, v in a.items():
            if k != "games":
                lg[k] += v

    lg_ypa = _safe(lg["pass_yds"], lg["att"])
    lg_ypc = _safe(lg["rush_yds"], lg["car"])
    lg_ptd = _safe(lg["pass_td"], lg["att"])
    lg_rtd = _safe(lg["rush_td"], lg["car"])
    lg_int = _safe(lg["int"], lg["att"])
    lg_pos = {pg: _safe(lg["rec_yds_" + pg], lg["tgt_" + pg]) for pg in ("RB", "WR", "TE")}

    out: dict[str, dict] = {}
    for d, a in acc.items():
        ypa = _safe(a["pass_yds"], a["att"])
        ypc = _safe(a["rush_yds"], a["car"])
        games = max(a["games"], 1.0)
        prof = {
            "games": int(a["games"]),
            "ypa_allowed": ypa,
            "ypc_allowed": ypc,
            # league averages travel with the profile so a row can say "5.0 a
            # carry against a league 4.3" instead of a bare multiplier
            "lg_ypa": lg_ypa,
            "lg_ypc": lg_ypc,
            "pass_yds_pg": a["pass_yds"] / games,
            "rush_yds_pg": a["rush_yds"] / games,
            "pass": _clamp(_shrink(_safe(ypa, lg_ypa, 1.0), a["att"], K_PASS_PLAYS), *DEF_MULT_CLAMP),
            "rush": _clamp(_shrink(_safe(ypc, lg_ypc, 1.0), a["car"], K_RUSH_PLAYS), *DEF_MULT_CLAMP),
            "pass_td": _clamp(_shrink(_safe(_safe(a["pass_td"], a["att"]), lg_ptd, 1.0),
                                      a["att"], K_TD_PLAYS), *DEF_MULT_CLAMP),
            "rush_td": _clamp(_shrink(_safe(_safe(a["rush_td"], a["car"]), lg_rtd, 1.0),
                                      a["car"], K_TD_PLAYS), *DEF_MULT_CLAMP),
            "int": _clamp(_shrink(_safe(_safe(a["int"], a["att"]), lg_int, 1.0),
                                  a["att"], K_TD_PLAYS), *DEF_MULT_CLAMP),
        }
        for pg in ("RB", "WR", "TE"):
            ypt = _safe(a["rec_yds_" + pg], a["tgt_" + pg])
            prof["ypt_allowed_" + pg] = ypt
            prof["lg_ypt_" + pg] = lg_pos[pg]
            prof["vs_" + pg] = _clamp(
                _shrink(_safe(ypt, lg_pos[pg], 1.0), a["tgt_" + pg], K_PASS_PLAYS / 2),
                *DEF_MULT_CLAMP)
        prof["funnel"] = prof["pass"] - prof["rush"]
        out[d] = prof
    return out


def funnel_label(prof: dict) -> str:
    """Plain words for the run/pass split, on round thresholds."""
    f = prof.get("funnel", 0.0)
    if f >= 0.06:
        return "pass funnel"
    if f <= -0.06:
        return "run funnel"
    if prof.get("pass", 1.0) > 1.04 and prof.get("rush", 1.0) > 1.04:
        return "soft all over"
    if prof.get("pass", 1.0) < 0.96 and prof.get("rush", 1.0) < 0.96:
        return "stiff all over"
    return "balanced"


# --------------------------------------------------------------------------
# player baselines
# --------------------------------------------------------------------------
_STAT_KEYS = (
    ("attempts", "att"), ("carries", "car"), ("targets", "tgt"),
    ("passing_yards", "pass_yds"), ("rushing_yards", "rush_yds"),
    ("receiving_yards", "rec_yds"), ("passing_tds", "pass_tds"),
    ("rushing_tds", "rush_tds"), ("receiving_tds", "rec_tds"),
    ("passing_interceptions", "ints"), ("receptions", "rec"),
)


def full_time_reference(weeks: list[dict],
                        current_season: int) -> tuple[float, float, dict]:
    """(total weight, effective sample, weight per week) a player would carry
    if he had played every game in the window.

    The per-week breakdown is what lets a player be measured against only the
    part of the calendar he was eligible for -- see the debut handling in
    `player_baselines`.

    A raw weight sum means nothing on its own -- the decay caps it around 8
    however long a career is -- so "how much have we got on this guy" only
    reads as a fraction of this.

    A full-time player still misses his bye, so the reference skips one week
    per season. Otherwise the top of the scale is unreachable by
    construction and every starter piles into the same bucket.
    """
    cal = timeline(weeks)
    if not cal:
        return 1.0, 1.0, {}
    byes = {min(w for s, w in cal if s == season) for season in {s for s, _ in cal}}
    fake = [{"season": s, "week": w} for s, w in cal
            if not (w in byes and (s, w) != cal[-1])]
    raw = game_weights(fake, current_season, cal)
    by_week = {(r["season"], r["week"]): w for r, w in zip(fake, raw) if w > 0}
    ws = [w for w in raw if w > 0]
    if not ws:
        return 1.0, 1.0, {}
    total = sum(ws)
    return total, (total ** 2) / sum(w * w for w in ws), by_week


def player_baselines(weeks: list[dict], current_season: int,
                     out_weeks: dict[str, set] | None = None,
                     entry_years: dict[str, int] | None = None) -> dict[str, dict]:
    """Recency-weighted per-game volume, efficiency and game-to-game spread.

    `out_weeks` is nflverse.out_weeks(): the weeks each player was ruled off
    the field. `entry_years` is nflverse.entry_years(): the season each player
    came into the league. Neither changes anything about the projection --
    they only change how much of the calendar we hold him to when judging how
    well we know him.
    """
    absent = out_weeks or {}
    entered = entry_years or {}
    by_player: dict[str, list[dict]] = collections.defaultdict(list)
    for r in weeks:
        by_player[r["player_id"]].append(r)

    cal = timeline(weeks)
    cal_weeks = set(cal)
    ref_weight, ref_ess, ref_by_week = full_time_reference(weeks, current_season)
    # The smallest reference anyone is measured against, whatever his debut:
    # the weight the decay puts on the DEBUT_MIN_GAMES most recent games.
    min_ref = sum(GAME_DECAY ** i for i in range(DEBUT_MIN_GAMES))
    out: dict[str, dict] = {}
    for pid, rows in by_player.items():
        rows.sort(key=lambda r: (r["season"], r["week"]))
        weights = game_weights(rows, current_season, cal)
        pairs = [(r, w) for r, w in zip(rows, weights) if w > 0]
        if not pairs:
            continue
        gw = sum(w for _, w in pairs)
        if gw <= 0:
            continue
        last = pairs[-1][0]

        def mean(field: str) -> float:
            return sum(w * r[field] for r, w in pairs) / gw

        def sd(field: str, mu: float) -> float:
            if len(pairs) < 2:
                return 0.0
            var = sum(w * (r[field] - mu) ** 2 for r, w in pairs) / gw
            return math.sqrt(max(var, 0.0))

        # Effective sample size, not the raw weight sum. With a 0.88 decay the
        # weights sum to at most ~8 no matter how long a career is, so using
        # that sum as "how many games do we have" would over-shrink everyone.
        # Kish's ESS answers the question the shrinkage actually asks.
        w2 = sum(w * w for _, w in pairs)
        eff_games = (gw * gw / w2) if w2 else 0.0

        # Time he was hurt is not time he failed to show us anything. Weeks he
        # was ruled out -- and did not play anyway -- come off the REFERENCE,
        # so the question becomes "how much of the time he was available have
        # we seen him", not "how much of the calendar". Nothing here touches
        # the projection or the shrinkage: we really do have fewer games on
        # him, and the estimate is still made from the games we have. This is
        # only about not calling a healthy starter unknown because of last
        # October.
        played = {(r["season"], r["week"]) for r, _ in pairs}
        missed = [g for g in absent.get(pid, ())
                  if g not in played and g in cal_weeks]
        lost = sum(w for w in game_weights(
            [{"season": s, "week": w} for s, w in missed], current_season, cal)
            if w > 0)
        avail_weight = max(ref_weight - lost, ref_weight * (1.0 - MAX_EXCUSED))

        # Weeks before he had ever played come off the same bottom, and they
        # come off in full -- they are not time he was unavailable, they are
        # time he was not in the league. Held to the whole two-season
        # calendar a rookie scored about half of what the identical veteran
        # scored, which put every one of them under the board's default
        # threshold no matter how plainly he had a role.
        #
        # Scoped to a debut in the CURRENT season. A veteran whose earliest
        # log in the window is old news is exactly the player we should be
        # unsure about, and he keeps the full reference.
        debut = pairs[0][0]
        entry = entered.get(pid)
        rookie = entry == current_season if entry else (
            debut["season"] == current_season and
            not any(r["season"] < current_season for r, _ in pairs))
        if rookie:
            pre_debut = sum(w for g, w in ref_by_week.items()
                            if g < (debut["season"], debut["week"]))
            avail_weight = max(avail_weight - pre_debut, min_ref)

        base = {
            "player_id": pid,
            "name": last["name"],
            "position": last["position"],
            "position_group": last["position_group"],
            "team": last["team"],
            "headshot": next((r["headshot"] for r, _ in reversed(pairs) if r["headshot"]), ""),
            "weighted_games": gw,
            "eff_games": eff_games,
            "ref_ess": ref_ess,
            "ref_weight": ref_weight,
            "avail_weight": avail_weight,
            "rookie": rookie,
            "entry_year": entry,
            "games_missed_out": len(missed),
            "games_cur": sum(1 for r, _ in pairs if r["season"] == current_season),
            "games_prev": sum(1 for r, _ in pairs if r["season"] < current_season),
            # where he played last season, so a teammate's absence is only
            # read into the part of his history they actually shared
            "prev_team": collections.Counter(
                r["team"] for r, _ in pairs if r["season"] < current_season
            ).most_common(1)[0][0] if any(r["season"] < current_season for r, _ in pairs) else "",
            "cur_share": sum(w for r, w in pairs if r["season"] == current_season) / gw,
        }
        for field, key in _STAT_KEYS:
            mu = mean(field)
            base[key] = mu
            base[key + "_sd"] = sd(field, mu)

        base["rush_rec_yds"] = base["rush_yds"] + base["rec_yds"]
        # rushing and receiving yards in the same game are only loosely related,
        # so add the spreads in quadrature rather than straight.
        base["rush_rec_yds_sd"] = math.hypot(base["rush_yds_sd"], base["rec_yds_sd"])

        base["ypa"] = _safe(base["pass_yds"], base["att"])
        base["ypc"] = _safe(base["rush_yds"], base["car"])
        base["ypt"] = _safe(base["rec_yds"], base["tgt"])
        base["int_rate"] = _safe(base["ints"], base["att"])
        base["pass_td_rate"] = _safe(base["pass_tds"], base["att"])
        base["rush_td_rate"] = _safe(base["rush_tds"], base["car"])
        base["rec_td_rate"] = _safe(base["rec_tds"], base["tgt"])
        out[pid] = base

    _shrink_to_position(out)
    return out


# Efficiency rates: only players who actually did the thing belong in the
# prior. A running back's "yards per pass attempt" is not evidence about
# quarterbacks, so each rate names the volume that has to be non-zero.
_EFFICIENCY_RATES = {"ypa": "att", "ypc": "car", "ypt": "tgt", "int_rate": "att"}

# Scoring is modelled per TOUCH, not per game, and the prior includes every
# player in the group -- including the ones who never score.
#
# Per touch matters as much as including the zeros. A third-string back who
# gets two carries a game should not inherit the average RB's touchdowns per
# GAME just because we are unsure about him; shrinking his touchdowns per
# CARRY and then multiplying by his own two carries keeps his role intact.
# Per game, he prices as a 23% touchdown scorer against a book at 3%.
_TOUCH_RATES = {"pass_td_rate": "att", "rush_td_rate": "car", "rec_td_rate": "tgt"}

# Volume is never shrunk -- how often a player touches the ball is the thing
# we are trying to measure, and it is his, not his position's.


def _shrink_to_position(baselines: dict[str, dict]) -> None:
    """Pull thin players' efficiency and scoring rates toward their position
    group, in place."""
    eff: dict[str, dict[str, list]] = collections.defaultdict(lambda: collections.defaultdict(list))

    for b in baselines.values():
        if b["eff_games"] < 4:
            continue
        pg = b["position_group"] or b["position"] or "UNK"
        for rate, volume_field in {**_EFFICIENCY_RATES, **_TOUCH_RATES}.items():
            if b[volume_field] > 0.5:
                # a zero here is real evidence (he gets touches and does not
                # score), so unlike the efficiency rates it stays in the prior
                eff[pg][rate].append((b[rate], b[volume_field]))

    def weighted_mean(pairs: list[tuple[float, float]]) -> float:
        wsum = sum(w for _, w in pairs)
        return (sum(v * w for v, w in pairs) / wsum) if wsum else 0.0

    group_mean: dict[str, dict[str, float]] = collections.defaultdict(dict)
    for pg, rates in eff.items():
        for rate, pairs in rates.items():
            group_mean[pg][rate] = weighted_mean(pairs)

    # Volume is never shrunk, but the board still needs a yardstick for it:
    # "18 carries a game" only means something against what the position
    # typically gets. Only players who actually do the thing count, or the
    # third-string backs drag every average to nothing.
    vol_pool: dict[str, dict[str, list]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for b in baselines.values():
        if b["eff_games"] < 4:
            continue
        pg = b["position_group"] or b["position"] or "UNK"
        for field in ("att", "car", "tgt"):
            if b[field] > 0.5:
                vol_pool[pg][field].append(b[field])
    group_volume: dict[str, dict[str, float]] = collections.defaultdict(dict)
    for pg, fields in vol_pool.items():
        for field, vals in fields.items():
            group_volume[pg][field] = sum(vals) / len(vals)

    for b in baselines.values():
        pg = b["position_group"] or b["position"] or "UNK"
        means = group_mean.get(pg, {})
        n = b["eff_games"]
        w = n / (n + K_PLAYER_GAMES)
        b["rate_confidence"] = w
        # kept so a row can say "5.1 a carry, his group averages 4.3"
        b["pos_mean"] = dict(means)
        b["pos_vol"] = dict(group_volume.get(pg, {}))
        all_rates = {**_EFFICIENCY_RATES, **_TOUCH_RATES}
        for rate, volume_field in all_rates.items():
            if rate not in means:
                continue
            # a player who has never thrown a pass keeps his zero rather than
            # inheriting the position's passing efficiency
            if volume_field and b[volume_field] <= 0.5:
                continue
            b[rate] = w * b[rate] + (1 - w) * means[rate]


# which yardage market's game-to-game spread moves with which volume
_VOLUME_MARKETS = {"att": ("pass_yds",), "car": ("rush_yds",), "tgt": ("rec_yds",)}


def team_pass_attempts(weeks: list[dict], current_season: int) -> dict[str, float]:
    """{team: pass attempts a game}, weighted the way the baselines are, so
    the chart's starter can be read on what his offense actually throws."""
    cal = timeline(weeks)
    per_game: dict[str, dict[tuple, float]] = collections.defaultdict(
        lambda: collections.defaultdict(float))
    for r in weeks:
        if r["team"]:
            per_game[r["team"]][(r["season"], r["week"])] += r["attempts"]
    out: dict[str, float] = {}
    for team, games in per_game.items():
        rows = [{"season": s, "week": w} for s, w in sorted(games)]
        weights = game_weights(rows, current_season, cal)
        wsum = sum(weights)
        if wsum > 0:
            out[team] = sum(games[(r["season"], r["week"])] * w
                            for r, w in zip(rows, weights)) / wsum
    return out


def next_man_up(chart: dict[str, list[dict]], bases: dict[str, dict],
                gone: dict[str, str], team: str, charted: set[str],
                week: int, team_att: float = 0.0) -> dict[str, dict]:
    """Adjusted baselines for one team's week: {player_id: a copy of his
    baseline with the volume that fell to him}. Players whose volume does
    not change are not in it.

    `chart` is depth.chart()["teams"][team], {pos: [{id, name, rank}, ...]}
    in depth order, and `charted` is every id on any team's chart. `gone` is
    {player_id: why} for everyone ruled out, doubtful or on a reserve list
    this week -- the why is a report status or a roster status code.

    A long-term absentee drops off ESPN's chart entirely, so the absent are
    also looked for among this team's baselines: gone, on nobody's chart,
    last seen playing for this team. Restricting that to players on NO
    chart is what stops a back who was traded and then hurt from being
    vacated from his old team as well as his new one.
    """
    played = max(week - 1, 1)

    def vol(pid: str, key: str) -> float:
        b = bases.get(pid)
        return float(b.get(key, 0.0)) if b else 0.0

    def overlap(absent_id: str, pid: str) -> float:
        """How much of `pid`'s read was built with `absent_id` on the field."""
        a, b = bases.get(absent_id), bases.get(pid)
        if not a or not b:
            return 0.0
        cur = _clamp(a.get("games_cur", 0) / played, 0.0, 1.0)
        prev = _clamp(a.get("games_prev", 0) / 17.0, 0.0, 1.0)
        if not (a.get("prev_team") == team and b.get("prev_team") == team):
            prev = 0.0                    # last season they were not together here
        s = b.get("cur_share", 0.0)
        return s * cur + (1 - s) * prev

    delta: dict[str, dict[str, float]] = collections.defaultdict(
        lambda: collections.defaultdict(float))
    sources: dict[str, dict[str, dict[str, float]]] = collections.defaultdict(
        lambda: collections.defaultdict(lambda: collections.defaultdict(float)))
    next_cap: dict[tuple[str, str], float] = {}
    promoted_ids: set[str] = set()

    def give(pid: str, key: str, amount: float, name: str) -> None:
        if amount > 0:
            delta[pid][key] += amount
            sources[pid][key][name] += amount

    def fit(pos: str) -> list[dict]:
        return [p for p in chart.get(pos, []) if p["id"] not in gone and p["id"] in bases]

    def off_chart(pos: str) -> list[dict]:
        return [{"id": pid, "name": b["name"], "rank": 0} for pid, b in bases.items()
                if (pid in gone and pid not in charted and b.get("team") == team
                    and (b.get("position_group") or b.get("position")) == pos)]

    # --- quarterback: a starter's attempts, or nothing -----------------------
    qbs = chart.get("QB", [])
    room = fit("QB")
    starter_flag: dict[str, str] = {}
    if room:
        starter = room[0]
        lost = [q for q in qbs if q["id"] in gone and q["id"] in bases]
        lost += [q for q in off_chart("QB") if gone.get(q["id"]) in QB_VACATES]
        best = max(lost, key=lambda q: vol(q["id"], "att"), default=None)
        lost_att = vol(best["id"], "att") if best else 0.0
        want = max(lost_att, STARTER_ATT_SHARE * team_att)
        have = vol(starter["id"], "att")
        if want - have >= MIN_VACATED:
            by_loss = lost_att >= STARTER_ATT_SHARE * team_att and best is not None
            give(starter["id"], "att", want - have, best["name"] if by_loss else "the chart")
            next_cap[(starter["id"], "att")] = want
            starter_flag[starter["id"]] = "lost" if by_loss else "chart"
            # a promotion only if the chart still has a lost man ahead of
            # him; once ESPN has moved him up he is simply the starter
            if any(q["rank"] < starter["rank"] for q in lost if q.get("rank")):
                promoted_ids.add(starter["id"])

    # --- the touches ---------------------------------------------------------
    runners = fit("RB")
    catchers = [p for pos in ("WR", "TE", "RB") for p in fit(pos)]
    for pos, keys in VACATED_KEYS.items():
        n_start = STARTERS[pos]
        healthy = fit(pos)
        primary = keys[0]
        absent = [p for p in chart.get(pos, []) if p["id"] in gone and p["id"] in bases]
        absent += off_chart(pos)
        if not absent:
            continue
        # whoever the absences moved into the lineup
        for i, p in enumerate(healthy):
            if i < n_start and p["rank"] > n_start:
                promoted_ids.add(p["id"])
        by_volume = sorted(healthy, key=lambda p: -vol(p["id"], primary))

        for a in absent:
            mine = vol(a["id"], primary)
            nxt = next((h for h in by_volume if vol(h["id"], primary) <= mine), None)
            for key in keys:
                raw = vol(a["id"], key)
                if raw < MIN_VACATED:
                    continue
                share = NEXT_MAN_SHARE[pos] if nxt else 0.0
                if nxt:
                    give(nxt["id"], key, raw * share * overlap(a["id"], nxt["id"]), a["name"])
                    next_cap[(nxt["id"], key)] = max(next_cap.get((nxt["id"], key), 0.0), raw)
                pool = [p for p in (runners if key == "car" else catchers)
                        if p["id"] != a["id"] and (nxt is None or p["id"] != nxt["id"])]
                weights = {p["id"]: vol(p["id"], key) for p in pool}
                wsum = sum(weights.values())
                if wsum <= 0:
                    continue
                for pid, w in weights.items():
                    give(pid, key, raw * (1 - share) * (w / wsum) * overlap(a["id"], pid),
                         a["name"])

    out: dict[str, dict] = {}
    for pid, d in delta.items():
        b = dict(bases[pid])
        gain: dict[str, float] = {}
        for key, amt in d.items():
            was = b[key]
            cap = next_cap.get((pid, key))
            if cap is not None:
                new = min(was + amt, max(was, cap))     # never more than the man he replaced
            else:
                new = was + min(amt, POOL_GAIN_CAP * was)
            if new - was < 1e-9:
                continue
            b[key] = new
            gain[key] = new - was
            ratio = new / was if was > 0 else 1.0
            for market in _VOLUME_MARKETS[key]:
                b[market + "_sd"] = b.get(market + "_sd", 0.0) * ratio
            # a quarterback read on a starter's attempts is playing whole
            # games, so his carries scale with his throws -- a passer whose
            # history is half a game of each is not a 3-carry runner
            if key == "att" and pid in starter_flag and b.get("car", 0.0) > 0:
                b["car"] = b["car"] * ratio
                gain["car"] = b["car"] - bases[pid]["car"]
                b["rush_yds_sd"] = b.get("rush_yds_sd", 0.0) * ratio
        if not gain:
            continue
        b["rush_rec_yds_sd"] = math.hypot(b["rush_yds_sd"], b["rec_yds_sd"])
        b["role_change"] = {
            "promoted": pid in promoted_ids,
            "starter": starter_flag.get(pid, ""),
            "gain": gain,
            "from": {k: [n for n, _ in sorted(v.items(), key=lambda kv: -kv[1])]
                     for k, v in sources[pid].items()},
        }
        out[pid] = b
    return out


def spread_priors(baselines: dict[str, dict]) -> dict[str, float]:
    """Typical game-to-game coefficient of variation per market, measured from
    the data rather than assumed, so a thin player's spread can be shrunk
    toward what that market normally looks like."""
    buckets: dict[str, list[float]] = collections.defaultdict(list)
    for b in baselines.values():
        if b["eff_games"] < 4:
            continue
        for market in YARDAGE:
            mu, s = b[market], b[market + "_sd"]
            if mu > 15 and s > 0:
                buckets[market].append(s / mu)
    return {m: (sorted(v)[len(v) // 2] if v else 0.5) for m, v in buckets.items()}


# --------------------------------------------------------------------------
# projection
# --------------------------------------------------------------------------
def weather_factors(wx: dict | None) -> dict:
    """What the forecast does to volume and to the throw.

    Returns {pass_eff, pass_vol, rush_vol, wind, kind, cold}. Neutral for a
    dome, for a game with no forecast, and for one too far out to trust --
    weather.py marks those `priced: False` and the header still shows them.
    """
    f = {"pass_eff": 1.0, "pass_vol": 1.0, "rush_vol": 1.0,
         "wind": 0.0, "kind": "", "cold": False}
    if not wx or wx.get("indoor") or not wx.get("priced"):
        return f

    wind = min(float(wx.get("wind") or 0.0), WIND_CAP_MPH)
    over = max(wind - WIND_CALM_MPH, 0.0)
    f["wind"] = wind
    f["pass_eff"] *= 1.0 - WIND_PASS_EFF_PER_MPH * over
    f["pass_vol"] *= 1.0 - WIND_PASS_VOL_PER_MPH * over
    f["rush_vol"] *= 1.0 + WIND_RUSH_VOL_PER_MPH * over

    snow = float(wx.get("snow") or 0.0)
    if snow >= SNOW_MIN_INCHES or wx.get("snowing"):
        f["kind"] = "snow"
        f["pass_eff"] *= SNOW_PASS_EFF
        f["pass_vol"] *= SNOW_PASS_VOL
        f["rush_vol"] *= SNOW_RUSH_VOL
    elif (float(wx.get("precip_prob") or 0.0) >= RAIN_MIN_PROB
          and float(wx.get("precip") or 0.0) >= RAIN_MIN_INCHES):
        f["kind"] = "rain"
        f["pass_eff"] *= RAIN_PASS_EFF
        f["pass_vol"] *= RAIN_PASS_VOL
        f["rush_vol"] *= RAIN_RUSH_VOL

    if float(wx.get("temp", 60.0)) <= FREEZING_F:
        f["cold"] = True
        f["pass_eff"] *= COLD_PASS_EFF

    for k in ("pass_eff", "pass_vol", "rush_vol"):
        f[k] = _clamp(f[k], *WEATHER_CLAMP)
    return f


def game_script(implied_team: float, implied_opp: float,
                league_avg_team_total: float, weather: dict | None = None) -> dict:
    """Volume and scoring multipliers implied by how the game is priced,
    and by what it will be played in."""
    margin = implied_team - implied_opp
    wx = weather_factors(weather)
    return {
        "margin": margin,
        "implied": implied_team,
        # the spread's share is clamped on its own, then the weather's is
        # multiplied on, so a windy blowout is not capped at a calm one
        "pass_vol": _clamp(1.0 - PASS_VOLUME_PER_POINT * margin, *SCRIPT_CLAMP) * wx["pass_vol"],
        "rush_vol": _clamp(1.0 + RUSH_VOLUME_PER_POINT * margin, *SCRIPT_CLAMP) * wx["rush_vol"],
        "pass_eff": wx["pass_eff"],
        "scoring": _clamp(_safe(implied_team, league_avg_team_total, 1.0), 0.70, 1.35),
        "weather": wx,
    }


def project(base: dict, defense: dict, script: dict) -> dict:
    """Every market for one player in one matchup. Yardage entries are point
    projections; count entries are Poisson rates."""
    pos_mult = defense.get("vs_" + base["position_group"], defense.get("pass", 1.0))
    # the weather's tax on every throw -- wind and rain make the same
    # attempt worth less, to the passer and to whoever it was meant for
    throw = script.get("pass_eff", 1.0)

    att = base["att"] * script["pass_vol"]
    car = base["car"] * script["rush_vol"]
    tgt = base["tgt"] * script["pass_vol"]

    rush_yds = car * base["ypc"] * defense["rush"]
    rec_yds = tgt * base["ypt"] * pos_mult * throw

    return {
        "pass_yds": att * base["ypa"] * defense["pass"] * throw,
        "rush_yds": rush_yds,
        "rec_yds": rec_yds,
        "rush_rec_yds": rush_yds + rec_yds,
        "pass_tds": att * base["pass_td_rate"] * script["scoring"] * defense["pass_td"],
        "interceptions": att * base["int_rate"] * defense["int"],
        "anytime_td": (car * base["rush_td_rate"] * defense["rush_td"]
                       + tgt * base["rec_td_rate"] * defense["pass_td"]) * script["scoring"],
        "_volume": {"att": att, "car": car, "tgt": tgt},
        "_pos_mult": pos_mult,
    }


def spread_for(base: dict, market: str, projection: float,
               priors: dict[str, float]) -> float:
    """Standard deviation to price a yardage line against.

    Three things move a result away from our number, and all three belong in
    the spread:
      1. the player's own game-to-game swing, blended toward what the market
         normally looks like when we have few games on him;
      2. sampling error -- our mean rests on n games, not infinitely many;
      3. model error -- we would still miss with a full season of data.
    Leaving out 2 and 3 is what produces a confident 1% on a backup who just
    got named starter.
    """
    prior_cv = priors.get(market, 0.5)
    prior = prior_cv * max(projection, 1.0)
    own = base.get(market + "_sd", 0.0)
    n = max(base["eff_games"], 0.5)

    if own <= 0:
        game_sd = prior
    else:
        w = n / (n + 4.0)      # 4 games before the player's own spread leads
        game_sd = w * own + (1 - w) * prior

    sampling_sd = game_sd / math.sqrt(n)
    model_sd = MODEL_ERROR_CV * max(projection, 1.0)
    total = math.sqrt(game_sd ** 2 + sampling_sd ** 2 + model_sd ** 2)
    return max(total, 0.20 * max(projection, 1.0))


def role_check(base: dict, market: str, projection: float, line: float,
               our_prob: float = 0.0, market_prob: float = 0.0) -> tuple[bool, str]:
    """Does the market's line sit inside what this player's usage can support?

    Returns (ok, reason). A line far above our number means the book is
    pricing a bigger role than his history shows -- a promotion or an injury
    ahead of him. A line far below means the opposite. Either way the gap is
    information we do not have, and betting it is betting against the book's
    depth chart, not against its number.

    A thin sample makes that test stricter, it does not decide it. A rookie
    with three starts and a line sitting exactly on our number is not a
    player whose role we are missing -- he is a player we have seen three
    times, which is what the confidence meter is for. Setting him aside on
    career length alone hid every rookie on the board.
    """
    thin = base["eff_games"] < MIN_EFF_GAMES
    if base["eff_games"] < MIN_ROLE_GAMES:
        return False, f"only {base['eff_games']:.1f} effective games of usage"
    if projection <= 0:
        return True, ""
    if market == "anytime_td":
        # No line to check a role against here -- the line is always "1". The
        # book's price is itself the sharpest read on role we can see, so a
        # player we make several times likelier to score than a book that has
        # already written him off is a stale usage read, not a find. Only
        # longshots are checked; a disagreement on a 40% favourite is a real
        # opinion, not a missing depth chart.
        cap = THIN_ATD_MAX_RATIO if thin else ATD_MAX_RATIO
        if 0 < market_prob < ATD_LONGSHOT and our_prob > cap * market_prob:
            return False, (f"we read {our_prob / market_prob:.1f}x the book's "
                           f"scoring chance - bigger role than we can see")
        return True, ""
    if market in COUNT:
        return True, ""
    lo, hi = (THIN_ROLE_LOW, THIN_ROLE_HIGH) if thin else (ROLE_LOW, ROLE_HIGH)
    ratio = line / projection if projection else 0.0
    if ratio > hi:
        return False, f"line is {ratio:.1f}x our usage read - bigger role than we can see"
    if ratio < lo:
        return False, f"line is {ratio:.1f}x our usage read - smaller role than we can see"
    return True, ""


def cover_probability(market: str, projection: float, line: float,
                      sd: float) -> float:
    """Our probability that the OVER hits."""
    if market in COUNT:
        return poisson_over(projection, line)
    if market == "anytime_td":
        return 1.0 - math.exp(-max(projection, 0.0))
    if sd <= 0:
        return 0.5
    return 1.0 - phi((line - projection) / sd)


# --------------------------------------------------------------------------
# how strongly do we hold the call, and why
#
# Nothing below looks at the book. The board ranks on our own read; the
# price is printed beside it as a reference, not as the thing being ranked.
# --------------------------------------------------------------------------
CONF_SEEN_CURRENT = 2.0   # games this season before we stop docking him
CONF_DEF_GAMES = 8.0      # opponent games past which the defense read is fully fed

# Plain words for the 0-1 confidence scale, high to low. These describe the
# scale, not this week's board -- they are not tuned to make the buckets come
# out any particular size.
CONF_WORDS = [(0.80, "strong read"), (0.58, "fair read"),
              (0.33, "light read"), (0.0, "thin read")]


def confidence(base: dict, dprof: dict) -> float:
    """0-1: how much of this read is actually earned.

    Three things have to be true before we hold an opinion -- we have seen
    the player enough, we have seen him play THIS season (roles change in
    March), and we have seen the defense enough. Any one missing should pull
    the whole thing down, so they multiply rather than average.

    Each term is measured against what a FULLY fed read looks like, not
    against infinity. Two earlier versions of this both collapsed to a single
    label across the whole board: one scaled usage by n/(n+K), whose ceiling
    the decayed ESS can never reach, and one counted the share of the
    weighting coming from this season, which in September is small for
    everybody for the same calendar reason and so separated nobody.
    """
    # Total weight, NOT the effective sample size. ESS is scale-invariant,
    # so it cannot tell "two recent games and a faded history" from "eighteen
    # evenly faded games and nothing since" -- it actually scores the retired
    # player HIGHER, because his weights are flatter. Total weight carries the
    # season and recency discount that separates them, which is the whole
    # question a confidence meter is asking. ESS stays where it belongs, in
    # the shrinkage.
    #
    # Measured against the time he was AVAILABLE, not the whole calendar --
    # `avail_weight` has his ruled-out weeks already taken out of it. A back
    # who missed eight games with a foot injury and has started every game
    # since is not a player we are unsure about.
    gw = max(base.get("weighted_games", 0.0), 0.0)
    ref = base.get("avail_weight") or base.get("ref_weight", 1.0)
    usage = min(gw / max(ref, 0.5), 1.0)

    played = float(base.get("games_cur", 0))
    current = 0.55 + 0.45 * min(played / CONF_SEEN_CURRENT, 1.0)

    dg = float(dprof.get("games", 0))
    defense = min(dg / CONF_DEF_GAMES, 1.0)

    return _clamp(usage * current * defense, 0.0, 1.0)


def confidence_word(c: float) -> str:
    for floor, word in CONF_WORDS:
        if c >= floor:
            return word
    return CONF_WORDS[-1][1]


def conviction(market: str, our_prob: float, conf: float) -> float:
    """0-1 ranking score, from our number alone.

    Anytime touchdown asks a question with a natural answer -- how likely is
    he to score -- so that probability IS the ranking. Every other market is
    a line to clear, where 50/50 means we have nothing to say and both 90%
    and 10% are strong opinions. Either way it is scaled by how much of the
    read we have earned, so a loud number off two games does not outrank a
    quieter one off twenty.
    """
    strength = our_prob if market == "anytime_td" else abs(our_prob - 0.5) * 2
    return _clamp(strength, 0.0, 1.0) * conf


_VOLUME_PHRASE = {
    "pass_yds": ("att", "pass attempt", "pass attempts"),
    "pass_tds": ("att", "pass attempt", "pass attempts"),
    "interceptions": ("att", "pass attempt", "pass attempts"),
    "rush_yds": ("car", "carry", "carries"),
    "rec_yds": ("tgt", "target", "targets"),
}


def _count(n: float, singular: str, plural: str | None = None) -> str:
    """"1 target", "13 targets" -- a row that says "1 targets" reads like a
    bug even when the number behind it is right."""
    word = singular if round(n) == 1 else (plural or singular + "s")
    return f"{n:.0f} {word}"


_SCRIPT_YARDAGE = ("pass_yds", "rush_yds", "rec_yds", "rush_rec_yds", "interceptions")


def drivers(base: dict, dprof: dict, script: dict, market: str,
            proj_all: dict, opponent: str) -> list[dict]:
    """The reasons behind one projection, biggest first.

    Each entry is {kind, text, lean}, where lean is +1 if that factor pushes
    the number up, -1 down, 0 for context. This is the point of the board --
    a number is only worth as much as the sentence next to it.
    """
    out: list[dict] = []
    vol = proj_all["_volume"]
    pg = base.get("position_group") or base.get("position") or ""
    pos_vol = base.get("pos_vol") or {}

    def vol_lean(*fields: str) -> int:
        """Volume is usually the biggest term in the projection, so when it
        is what makes a player interesting the row has to say so.

        Judged on the touch a player actually gets. A receiver with no
        carries is not a low-volume runner, he is not a runner, and marking
        that as a negative reads like the model docked him for it.
        """
        best, lean = 0.0, 0
        for field in fields:
            amount, typical = vol[field], pos_vol.get(field)
            if amount < 0.5 or not typical or amount <= best:
                continue
            ratio = amount / typical
            best = amount
            lean = 0 if abs(ratio - 1) < 0.15 else (1 if ratio > 1 else -1)
        return lean

    # --- volume: the biggest term in every projection ----------------------
    if market == "rush_rec_yds":
        touches = vol["car"] + vol["tgt"]
        out.append({"kind": "volume", "lean": vol_lean("car", "tgt"),
                    "text": f"{_count(vol['car'], 'carry', 'carries')} and "
                            f"{_count(vol['tgt'], 'target')} a game"})
    elif market == "anytime_td":
        touches = vol["car"] + vol["tgt"]
        out.append({"kind": "volume", "lean": vol_lean("car", "tgt"),
                    "text": f"{touches:.0f} touches a game "
                            f"({_count(vol['car'], 'carry', 'carries')}, "
                            f"{_count(vol['tgt'], 'target')})"})
    else:
        key, singular, plural = _VOLUME_PHRASE[market]
        out.append({"kind": "volume", "lean": vol_lean(key),
                    "text": f"{_count(vol[key], singular, plural)} a game"})

    # --- touches that fell to him ------------------------------------------
    out.extend(_role_driver(base, market))

    # --- the matchup -------------------------------------------------------
    out.extend(_matchup_driver(dprof, market, pg, opponent))

    # --- the weather -------------------------------------------------------
    # Ahead of the script on purpose: a row only has room for three reasons,
    # and on the day it matters the wind is the reason.
    out.extend(_weather_driver(script.get("weather") or {}, market, base))

    # --- game script -------------------------------------------------------
    # The dropback/carry story only belongs on the yardage markets. A
    # touchdown prop does not care that a favourite throws less -- it cares
    # that his team is expected in the end zone more often -- so for the
    # scoring markets the environment is the implied total, full stop.
    margin = script["margin"]
    if market in _SCRIPT_YARDAGE:
        if margin >= 3:
            ground = market in ("rush_yds", "rush_rec_yds")
            out.append({"kind": "script", "lean": 1 if ground else -1,
                        "text": f"{margin:.0f}-point favourite, " + (
                            "running it out late" if ground
                            else "fewer dropbacks with a lead")})
        elif margin <= -3:
            ground = market == "rush_yds"
            out.append({"kind": "script", "lean": -1 if ground else 1,
                        "text": f"{abs(margin):.0f}-point dog, " + (
                            "the script takes carries away" if ground
                            else "throwing to catch up")})
    elif market in ("anytime_td", "pass_tds"):
        s = script["scoring"]
        if abs(s - 1) >= 0.05:
            word = "high" if s > 1 else "quiet"
            out.append({"kind": "script", "lean": 1 if s > 1 else -1,
                        "text": f"{script['implied']:.0f} implied points, "
                                f"a {word}-scoring spot"})
        else:
            out.append({"kind": "script", "lean": 0,
                        "text": f"{script['implied']:.0f} implied points, "
                                f"an average scoring spot"})

    # --- his own efficiency against his position ---------------------------
    out.extend(_efficiency_driver(base, market))

    # --- what we do not know ----------------------------------------------
    share = base.get("cur_share", 0.0)
    if share < 0.35:
        out.append({"kind": "sample", "lean": 0,
                    "text": f"only {share * 100:.0f}% of this read is from this season"})
    if base.get("eff_games", 0) < MIN_EFF_GAMES:
        out.append({"kind": "sample", "lean": 0,
                    "text": f"{base['eff_games']:.1f} effective games of usage"})
    hurt = base.get("games_missed_out", 0)
    if hurt >= 3:
        out.append({"kind": "sample", "lean": 0,
                    "text": f"missed {hurt} games hurt, not held against him"})

    # Rows only have room for the first two or three of these, so the ones
    # that actually moved the number have to come first. Volume leads because
    # it is the biggest term; caveats trail because they qualify the rest.
    order = {"volume": 0, "role": 0, "matchup": 1, "weather": 1, "script": 1,
             "efficiency": 1, "sample": 3}
    return sorted(out, key=lambda d: (order[d["kind"]], 0 if d["lean"] else 1))


_ROLE_KEYS = {
    "pass_yds": ("att",), "pass_tds": ("att",), "interceptions": ("att",),
    "rush_yds": ("car",), "rec_yds": ("tgt",),
    "rush_rec_yds": ("car", "tgt"), "anytime_td": ("car", "tgt"),
}
_ROLE_WORD = {"att": "attempts", "car": "carries", "tgt": "targets"}


def _role_driver(base: dict, market: str) -> list[dict]:
    """The volume a teammate's absence handed him, when it is enough to
    matter to this market. "next man up" names the promotion; the rest of
    the group just gets the arithmetic."""
    rc = base.get("role_change")
    if not rc:
        return []
    keys = [k for k in _ROLE_KEYS[market] if rc["gain"].get(k, 0.0) >= MIN_ROLE_NOTE]
    if not keys:
        return []
    what = " and ".join(f"{rc['gain'][k]:.0f} {_ROLE_WORD[k]}" for k in keys)
    if rc.get("starter") == "chart":
        own = base["att"] - rc["gain"].get("att", 0.0)
        return [{"kind": "role", "lean": 1,
                 "text": f"starts per the depth chart - read on his offense's "
                         f"{base['att']:.0f} attempts, not his own {own:.0f}"}]
    who: list[str] = []
    for k in keys:
        for n in rc["from"].get(k, []):
            if n not in who:
                who.append(n)
    names = ", ".join(who[:2]) + (f" and {len(who) - 2} more" if len(who) > 2 else "")
    lead = "next man up: " if rc["promoted"] else ""
    return [{"kind": "role", "lean": 1,
             "text": f"{lead}+{what} with {names} out"}]


def _weather_driver(wx: dict, market: str, base: dict) -> list[dict]:
    """The forecast, only when it moved the number. A dome and a calm day
    say nothing -- there is no row that gets better for being told it was
    68 and still."""
    if not wx:
        return []
    moved = max(abs(wx.get("pass_eff", 1.0) - 1), abs(wx.get("pass_vol", 1.0) - 1),
                abs(wx.get("rush_vol", 1.0) - 1))
    if moved < 0.03:
        return []

    bits = []
    wind = wx.get("wind", 0.0)
    if wind >= WIND_CALM_MPH + 3:
        bits.append(f"{wind:.0f} mph wind")
    if wx.get("kind"):
        bits.append(wx["kind"])
    if wx.get("cold"):
        bits.append("below freezing")
    what = ", ".join(bits) or "the forecast"

    if market in ("pass_yds", "rec_yds", "pass_tds"):
        return [{"kind": "weather", "lean": -1,
                 "text": f"{what} - fewer throws, and each one worth less"}]
    if market == "interceptions":
        return [{"kind": "weather", "lean": -1,
                 "text": f"{what} - fewer throws to pick off"}]
    if market == "rush_yds":
        return [{"kind": "weather", "lean": 1,
                 "text": f"{what} pushes the game to the ground"}]
    if market == "rush_rec_yds":
        # both halves move; the sign is whichever half he lives on
        ground = base.get("car", 0.0) >= base.get("tgt", 0.0)
        return [{"kind": "weather", "lean": 1 if ground else -1,
                 "text": f"{what} - more carries, fewer targets"}]
    # anytime touchdown: his scores come from somewhere, and the weather
    # moves the ball toward the run
    rush_share = base.get("car", 0.0) * base.get("rush_td_rate", 0.0)
    rec_share = base.get("tgt", 0.0) * base.get("rec_td_rate", 0.0)
    ground = rush_share >= rec_share
    return [{"kind": "weather", "lean": 1 if ground else -1,
             "text": f"{what} shifts scoring toward the run"}]


def _matchup_driver(dprof: dict, market: str, pg: str, opp: str) -> list[dict]:
    """The defense half of the projection, in the units it was measured in."""
    def pct(mult: float) -> str:
        return f"{abs(mult - 1) * 100:.0f}% {'above' if mult > 1 else 'below'} average"

    def lean(mult: float) -> int:
        return 0 if abs(mult - 1) < 0.03 else (1 if mult > 1 else -1)

    if market == "pass_yds":
        m = dprof.get("pass", 1.0)
        return [{"kind": "matchup", "lean": lean(m),
                 "text": f"{opp} allow {dprof.get('ypa_allowed', 0):.1f} yards a pass attempt "
                         f"(league {dprof.get('lg_ypa', 0):.1f}), {pct(m)}"}]
    if market == "rush_yds":
        m = dprof.get("rush", 1.0)
        return [{"kind": "matchup", "lean": lean(m),
                 "text": f"{opp} allow {dprof.get('ypc_allowed', 0):.1f} yards a carry "
                         f"(league {dprof.get('lg_ypc', 0):.1f}), {pct(m)}"}]
    if market == "rec_yds":
        m = dprof.get("vs_" + pg, dprof.get("pass", 1.0))
        got = dprof.get("ypt_allowed_" + pg)
        if got is None:
            return [{"kind": "matchup", "lean": lean(m),
                     "text": f"{opp} secondary {pct(m)}"}]
        return [{"kind": "matchup", "lean": lean(m),
                 "text": f"{opp} allow {got:.1f} yards a target to {pg}s "
                         f"(league {dprof.get('lg_ypt_' + pg, 0):.1f}), {pct(m)}"}]
    if market == "rush_rec_yds":
        r = dprof.get("rush", 1.0)
        p = dprof.get("vs_" + pg, dprof.get("pass", 1.0))
        return [{"kind": "matchup", "lean": lean((r + p) / 2),
                 "text": f"{opp} allow {dprof.get('ypc_allowed', 0):.1f} a carry and "
                         f"{dprof.get('ypt_allowed_' + pg, 0):.1f} a target to {pg}s"}]
    if market == "pass_tds":
        m = dprof.get("pass_td", 1.0)
        return [{"kind": "matchup", "lean": lean(m),
                 "text": f"{opp} concede passing touchdowns {pct(m)}"}]
    if market == "interceptions":
        m = dprof.get("int", 1.0)
        return [{"kind": "matchup", "lean": lean(m),
                 "text": f"{opp} pick passes off at a rate {pct(m)}"}]

    # anytime touchdown draws on both
    r, p = dprof.get("rush_td", 1.0), dprof.get("pass_td", 1.0)
    bits = []
    if abs(r - 1) >= 0.03:
        bits.append(f"rushing touchdowns {pct(r)}")
    if abs(p - 1) >= 0.03:
        bits.append(f"receiving touchdowns {pct(p)}")
    if not bits:
        return [{"kind": "matchup", "lean": 0,
                 "text": f"{opp} concede touchdowns at about the league rate"}]
    return [{"kind": "matchup", "lean": 1 if (r + p) / 2 > 1 else -1,
             "text": f"{opp} concede " + " and ".join(bits)}]


_EFFICIENCY_LABEL = {
    "pass_yds": ("ypa", "yards a pass attempt", ""),
    "rush_yds": ("ypc", "yards a carry", ""),
    "rush_rec_yds": ("ypc", "yards a carry", ""),
    "rec_yds": ("ypt", "yards a target", ""),
    "interceptions": ("int_rate", "interception rate", "%"),
    "pass_tds": ("pass_td_rate", "touchdown rate", "%"),
}


def _efficiency_driver(base: dict, market: str) -> list[dict]:
    """Only worth saying when he is actually different from his position."""
    rate, label, unit = _EFFICIENCY_LABEL.get(market, (None, "", ""))
    if not rate:
        return []
    mine = base.get(rate, 0.0)
    theirs = (base.get("pos_mean") or {}).get(rate)
    if not theirs or not mine:
        return []
    ratio = mine / theirs
    if abs(ratio - 1) < 0.08:
        return []
    if unit == "%":
        text = (f"his {label} is {mine * 100:.1f}% against a position "
                f"average {theirs * 100:.1f}%")
    else:
        text = f"he gets {mine:.1f} {label}, his position averages {theirs:.1f}"
    return [{"kind": "efficiency", "lean": 1 if ratio > 1 else -1, "text": text}]
