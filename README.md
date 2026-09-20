# NFL prop board

Who we think scores, who runs for how much, who catches how much -- and the
reason for each. Seven prop markets. Built around one question: **what does
this defense give up, and does it give up runs or passes?**

**The book does not get a vote.** Rows are ranked on our own number. The line
and the price sit beside it, small and grey, so you can see the two together;
they never pick a side and never change the order.

Double-click `Start NFL Props.cmd`, or:

```
python -m streamlit run app.py --server.port 8502
```

## Three views

| | |
|---|---|
| **Who scores** | everyone on the slate ranked by our probability he reaches the end zone |
| **Top projections** | one market, ranked by our projection, biggest first |
| **By game** | the full matchup board, grouped by game |

Every row carries the two or three things that actually moved the number --
his volume, what the defense gives up in the units it was measured in, and
the game script -- with an arrow for which way each one pushed.

## Markets

Passing yards · rushing yards · receiving yards · rush + receiving yards ·
passing touchdowns · interceptions · anytime touchdown.

DraftKings and FanDuel, switchable in the sidebar. FanDuel does not post
rush+rec or interceptions; DraftKings carries all seven.

## Where the numbers come from

Everything is free, needs no account and has no monthly quota.
`notes/DATA_SOURCES.md` has the exact URLs and what was tested.

| | |
|---|---|
| Player game logs | nflverse `stats_player_week_{year}.csv` |
| Schedule, spreads, totals | nflverse `games.csv` |
| Injuries | nflverse `injuries_{year}.csv` |
| DK / FD lines | BettingPros v3 |
| Logos, headshots | ESPN CDN, and the headshot URL inside the stats file |

DraftKings' and FanDuel's own endpoints are blocked from this machine at an
Akamai edge, so do not build on them. `notes/probe_sources.py` re-verifies
every source; `notes/verify_vs_nflcom.py` checks our game logs against
nfl.com's official season totals.

## How a projection is built

    projection = player baseline  x  opponent defense  x  game environment

**Player baseline** — per-game volume and efficiency from the last two
seasons, weighted toward recent games and toward the current season, because
a prop is a bet on this week's role. Efficiency and scoring rates are pulled
toward the position-group average until a player has enough games to have
earned his own. Scoring is modelled per *touch*, not per game, so a backup
does not inherit a starter's touchdown rate.

**Opponent defense** — yards allowed **per play**, not per game, so a defense
is not punished for its own offense leaving it on the field. Computed
separately for the run and the pass, and again for the receiving yards
allowed to RBs, WRs and TEs. The gap between the pass and run numbers is the
funnel read on each game header:

- *pass funnel* — stiff against the run, soft against the pass. Push passing
  and receiving props up, rushing props down.
- *run funnel* — the reverse.

**Game environment** — the implied team total from the spread and the total.
Favourites run more and throw less; the scoring environment scales touchdown
and interception rates.

Yardage probabilities use a normal spread that includes how little we may
know about a player; touchdowns and interceptions use Poisson.

**Confidence** is the pip meter on the right, and it is about the read, not
the bet: how much weighted history we have on the player against what a
full-time player carries, whether he has actually played this season, and how
many games we have on the defense. They multiply, so any one missing pulls the
whole thing down. Rows sort affirmative reads first -- what a player is
projected to do, ahead of what he is projected not to.

Every coefficient sits at the top of `model.py` with a comment saying what it
means. Nothing is fitted to past results.

## Set-aside props

A prop is set aside, greyed and never ranked, when the market's line implies a
role our game logs cannot see — a promotion, an injury ahead of him on the
depth chart — or the player is listed out. A backup quarterback projected for
77 yards against a 204.5 line is not a 34% edge; it means the book knows he is
starting and we do not. The flag covers every prop that player has in that
game, not just the one that tripped it. Toggle them on in the sidebar to see
what was dropped and why.

## Files

| | |
|---|---|
| `app.py` | Streamlit board |
| `board.py` | joins lines to projections, groups by game |
| `model.py` | baselines, defense profiles, projections, probabilities |
| `lines.py` | DK / FD lines |
| `nflverse.py` | game logs, schedule, injuries |
| `render.py` | the game panel markup |
| `common.py` | disk-cached fetch |
| `.streamlit/config.toml` | the theme |

## Known limits

- **It has not been backtested and will not be.** Judge it live.
- Two weeks into a season a defense read is mostly last year. The share of
  each read that comes from the current season is on every row that leans on
  it, and the weighting is in `model.py`.
- No depth chart. The set-aside rule is the guard against that, not a fix.
- BettingPros is an undocumented endpoint. If it breaks, `lines.py` is the
  only file to replace, and `notes/DATA_SOURCES.md` records a Rotowire
  fallback covering four of the seven markets.
