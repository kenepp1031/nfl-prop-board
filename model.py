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
def game_weights(rows: list[dict], current_season: int) -> list[float]:
    """A weight per row, from the season it belongs to and how many GAMES back
    it is. The decay has to be per game, not per row: a defense contributes
    ~25 opposing player-rows per game, so decaying by row index would put
    0.94^500 on last season and throw the whole sample away."""
    games = sorted({(r["season"], r["week"]) for r in rows})
    n = len(games)
    by_game = {}
    for i, g in enumerate(games):
        season_w = SEASON_WEIGHT.get(current_season - g[0], 0.0)
        by_game[g] = season_w * (GAME_DECAY ** (n - 1 - i))
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
    by_def: dict[str, list[dict]] = collections.defaultdict(list)
    for r in weeks:
        if r["opponent"]:
            by_def[r["opponent"]].append(r)

    acc: dict[str, dict] = {}
    for d, rows in by_def.items():
        rows.sort(key=lambda r: (r["season"], r["week"]))
        weights = game_weights(rows, current_season)
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


def player_baselines(weeks: list[dict], current_season: int) -> dict[str, dict]:
    """Recency-weighted per-game volume, efficiency and game-to-game spread."""
    by_player: dict[str, list[dict]] = collections.defaultdict(list)
    for r in weeks:
        by_player[r["player_id"]].append(r)

    out: dict[str, dict] = {}
    for pid, rows in by_player.items():
        rows.sort(key=lambda r: (r["season"], r["week"]))
        weights = game_weights(rows, current_season)
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

        base = {
            "player_id": pid,
            "name": last["name"],
            "position": last["position"],
            "position_group": last["position_group"],
            "team": last["team"],
            "headshot": next((r["headshot"] for r, _ in reversed(pairs) if r["headshot"]), ""),
            "weighted_games": gw,
            "eff_games": eff_games,
            "games_cur": sum(1 for r, _ in pairs if r["season"] == current_season),
            "games_prev": sum(1 for r, _ in pairs if r["season"] < current_season),
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

    for b in baselines.values():
        pg = b["position_group"] or b["position"] or "UNK"
        means = group_mean.get(pg, {})
        n = b["eff_games"]
        w = n / (n + K_PLAYER_GAMES)
        b["rate_confidence"] = w
        all_rates = {**_EFFICIENCY_RATES, **_TOUCH_RATES}
        for rate, volume_field in all_rates.items():
            if rate not in means:
                continue
            # a player who has never thrown a pass keeps his zero rather than
            # inheriting the position's passing efficiency
            if volume_field and b[volume_field] <= 0.5:
                continue
            b[rate] = w * b[rate] + (1 - w) * means[rate]


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
def game_script(implied_team: float, implied_opp: float,
                league_avg_team_total: float) -> dict:
    """Volume and scoring multipliers implied by how the game is priced."""
    margin = implied_team - implied_opp
    return {
        "margin": margin,
        "implied": implied_team,
        "pass_vol": _clamp(1.0 - PASS_VOLUME_PER_POINT * margin, *SCRIPT_CLAMP),
        "rush_vol": _clamp(1.0 + RUSH_VOLUME_PER_POINT * margin, *SCRIPT_CLAMP),
        "scoring": _clamp(_safe(implied_team, league_avg_team_total, 1.0), 0.70, 1.35),
    }


def project(base: dict, defense: dict, script: dict) -> dict:
    """Every market for one player in one matchup. Yardage entries are point
    projections; count entries are Poisson rates."""
    pos_mult = defense.get("vs_" + base["position_group"], defense.get("pass", 1.0))

    att = base["att"] * script["pass_vol"]
    car = base["car"] * script["rush_vol"]
    tgt = base["tgt"] * script["pass_vol"]

    rush_yds = car * base["ypc"] * defense["rush"]
    rec_yds = tgt * base["ypt"] * pos_mult

    return {
        "pass_yds": att * base["ypa"] * defense["pass"],
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
    """
    if base["eff_games"] < MIN_EFF_GAMES:
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
        if 0 < market_prob < ATD_LONGSHOT and our_prob > ATD_MAX_RATIO * market_prob:
            return False, (f"we read {our_prob / market_prob:.1f}x the book's "
                           f"scoring chance - bigger role than we can see")
        return True, ""
    if market in COUNT:
        return True, ""
    ratio = line / projection if projection else 0.0
    if ratio > ROLE_HIGH:
        return False, f"line is {ratio:.1f}x our usage read - bigger role than we can see"
    if ratio < ROLE_LOW:
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
