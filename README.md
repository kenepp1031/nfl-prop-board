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
| **By game** | the full matchup board, in kickoff order -- Thursday, the 1 o'clock block, the 4 o'clocks, Sunday night, Monday |

Games on the **By game** board start closed, each header showing its headline
read; click the matchup bar to drop its props down. "Open every game" in the
sidebar opens them all at once.

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
| Entry years, reserve lists | nflverse `roster_{year}.csv` |
| Depth chart | nflverse `depth_charts_{year}.csv.gz`, ESPN's chart snapshotted twice a day |
| DK / FD lines | BettingPros v3 |
| Weather | Open-Meteo forecast, one request a week covering every outdoor venue |
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

**Weather** — the other half of the environment, from the forecast over the
game window (kickoff to three hours after) at outdoor venues. Wind is the one
that matters: over 10 mph every extra mile an hour takes throws away, makes
each one worth less, and pushes carries up, so at 20 mph passing efficiency
is 10% down, attempts 6% down and carries 8% up — a windy day reads like
being a five-point favourite on top of the spread. Rain does the same in a
small dose and snow in a large one; a kickoff below freezing costs the throw
a little more. It is the sustained wind that is priced; gusts are shown on
the matchup bar but not modelled. Scoring is deliberately left alone,
because the market total already has the forecast in it and docking it
again would count the wind twice.

Domes and closed roofs are neutral. A retractable roof nobody has reported
on is assumed closed, since that is what the operators do whenever the
weather would matter. A game more than a week out shows its forecast, marked
*early*, but is not priced on it.

Yardage probabilities use a normal spread that includes how little we may
know about a player; touchdowns and interceptions use Poisson.

**Confidence** is the pip meter on the right, and it is about the read, not
the bet: how much weighted history we have on the player against what a
full-time player carries, whether he has actually played this season, and how
many games we have on the defense. They multiply, so any one missing pulls the
whole thing down. Rows sort affirmative reads first -- what a player is
projected to do, ahead of what he is projected not to.

**Rookies are measured from their first game, not from the calendar.** The
same idea as the injury rule below, for a different reason: weeks before a
player was in the league are not weeks he failed to show us a role. Held to
the full two-season window a rookie scored about half what the identical
veteran scored purely for being new, which put every one of them under the
board's default threshold no matter how plainly he was starting. Those weeks
now come off the bottom of the fraction in full. The floor is what stops that
becoming a free pass: however short his career, he is measured against at
least three recent full games, so a Week 1 debut still reads as someone we
barely know and only a rookie who has played a quarter of a season reads as
fully seen. Rookies carry a `rookie` tag on the row, because a read built on
four games is worth knowing about even when it is a confident one.

**Time missed hurt is not held against a player.** Weeks he was listed out
come off the *bottom* of that first fraction, so the question is how much of
the time he was available we have seen him, not how much of the calendar. A
back who missed half of last season with a foot injury and has started every
game since is not a player we are unsure about. An injury history can forgive
at most half the reference -- someone who was out all year and has played once
is still someone we barely know. This changes the pip meter only: the
projection is still made from the games he actually played, and the shrinkage
still counts them honestly.

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

A thin sample makes that test stricter; it does not decide it. A player with
few games gets a narrower band to disagree in before we conclude we are the
ones missing something, but a rookie with three starts and a line sitting on
our number is not a missing depth chart — he is a player we have seen three
times, which is what the pip meter is for. Career length alone sets aside only
a player with a single game, where there is no usage to check a line against
at all.

## Injuries

This week's report, and only this week's. A report is about one game, so a
back ruled out in week 1 and never listed since is not out in week 3. The
first version folded the whole season into one name-to-status map and had
eleven players greyed on the week 3 board for exactly that reason, Brock
Bowers and Zay Flowers among them.

Out and doubtful set every one of the player's props aside. Questionable is a
tag on the row with the body part beside it, and so is a missed practice
before the Friday designations are posted (`DNP · hamstring`); what to make
of either is a judgement for whoever is reading. Limited and full
participation are not injuries and are not shown. The join is on the
nflverse player id, the same one the game logs carry, with the name as a
fallback.

The designations land Friday afternoon for a Sunday game and nflverse
republishes its file through the day, which is why the refresh below runs
in the evening as well as the morning.

## Next man up

An injury used to set aside the player who had it and stop there. His
touches did not go anywhere, so the back behind him was still projected off
a backup's carries, and the line the book had posted for a starter's workload
tripped the role check: *bigger role than we can see*. Now we can see it.

The depth chart says who is behind whom. When a player is out, doubtful, or
on a reserve list, the touches he would have had are handed out:

- the next man at his position — the teammate whose volume sits just below
  his — takes a fixed share: three quarters of a back's carries, half a tight
  end's targets, a third of a receiver's;
- the rest is spread over everyone else in the group in proportion to what
  each already gets, so a lost receiver is mostly everyone else's targets;
- the next man is never handed more than the absentee had, and nobody in the
  pool gains more than a third of his own volume.

"Just below" is by volume, not by ESPN's order, because ESPN drops a back on
reserve to the bottom of its chart, and read literally that would send a
second back's carries to the lead back. The chart's order decides two other
things: who has been promoted into the lineup, and who the quarterback is.

Quarterback is not a redistribution. One man takes every snap, so the
healthy passer the chart puts first is projected on a starter's attempts:
his offense's own passes a game, less the few that go elsewhere, or the
attempts of the biggest passer the team has lost — out, on reserve, or
exempt — whichever is more, when either beats his own history. His carries
scale with his throws, because a passer whose logs are half a game here and
a start there is not a three-carry runner once he plays whole games. Kyler
Murray in Minnesota is the case: one partial game since the trade left him
reading as an 11-attempt passer against a line the book had posted for a
starter, and the role check set every one of his props aside.

Only the part of a teammate's read that was built with the absentee on the
field is corrected: his current-season share times the absentee's share of
this season's games, plus his last-season share times the absentee's of last
season's, and that second part only if both were on this team last season. A
receiver on reserve since August has been missing from every current-season
log his teammates have, so only the last-season part of their read needs it.
This is what keeps a long-term absence from inflating the same teammates
every week.

A promoted player carries a *next man up* tag and a lighter pip meter,
because his role is inferred from a chart rather than watched. Every row
whose volume changed says so, with who is out. Questionable players are not
redistributed; they are expected to play. A player promoted who has never
taken a snap has no baseline to adjust and still cannot be priced.

## Files

| | |
|---|---|
| `app.py` | Streamlit board |
| `refresh.py` | the daily pull; warms every cache file and proves the board builds |
| `board.py` | joins lines to projections, groups by game |
| `model.py` | baselines, defense profiles, projections, probabilities |
| `lines.py` | DK / FD lines |
| `nflverse.py` | game logs, schedule, injuries, reserve lists |
| `depth.py` | the depth chart, reduced to the latest snapshot |
| `weather.py` | the forecast per game, the venue coordinates, and the words for the matchup bar |
| `render.py` | the game panel markup |
| `common.py` | disk-cached fetch and disk memo |
| `.streamlit/config.toml` | the theme |
| `requirements.txt`, `.python-version` | what a host needs to build it |

## Staying current

While the board is open it refreshes itself — game logs on a six hour clock,
lines on a ten minute one, both behind whoever is looking rather than in front
of them. What it cannot do is refresh while it is shut, which is its normal
state, so opening it after a few days away meant a cold pull of two seasons of
game logs and sixty pages of lines with a spinner in front of it.

A scheduled task now does that pull twice a day whether or not anyone opens
the board:

| | |
|---|---|
| Task | **NFL Props Daily Refresh**, 08:00 and 18:00 daily |
| Runs | `pythonw refresh.py --quiet` in `C:\NFL props`, no console window |
| Catch-up | `StartWhenAvailable`, so a machine that was off at the time runs it at the next boot |
| Log | `cache/refresh.log`, trimmed from the front so it cannot grow forever |

The evening run is for the injury report: Friday's designations are posted in
the afternoon, and a morning-only pull would not show them until Saturday.
It also re-pulls the forecast, which moves.

It ignores every cache clock and fetches for real — a scheduled run that
honoured the six hour TTL would usually decide there was nothing to do. It
warms the week about to be played and the one after it, lines and forecast
both; past weeks are never refetched because those games are played and
their numbers never change again.

Each step is independent, so a feed that refuses costs that feed and not the
run, and every reader falls back to its last good copy. The last step builds
the whole board from what was just pulled and logs the prop counts, because
warming the files is not the same as knowing they still work together — a feed
that renames a column downloads perfectly and breaks the board on open.

`Update NFL Props.cmd` is the same pull with the output left on screen, for
when you want today's numbers now rather than at the next scheduled time.

To check on it, or to move the time:

```powershell
Get-ScheduledTaskInfo -TaskName "NFL Props Daily Refresh"   # last result, next run
Get-Content "C:\NFL props\cache\refresh.log" -Tail 20
Unregister-ScheduledTask -TaskName "NFL Props Daily Refresh"  # to remove it
```

## Speed

The board itself is cheap -- the join and the whole page of markup together
are about twenty milliseconds, so clicking a filter is instant. Everything
slow is the market pull, and it is handled three ways:

- **One pull covers both books.** A BettingPros offer arrives with
  DraftKings' price and FanDuel's on the same object, so `raw_offers()` is
  keyed by week and nothing else. Switching book is `price()` over data
  already in hand.
- **The pages go out together.** The API caps a page at ten offers, so a
  week is about sixty requests. Done one after another that is most of a
  minute. They are independent, so they run eight at a time in two waves --
  page 1 of every market to learn the page counts, then all the rest.
- **It is memoised on disk as well as in the cache**, trimmed to the fields
  the board reads. A restart, or a second person opening the board, reads a
  half-megabyte file instead of hitting the network. When the ten-minute
  clock runs out the refresh happens *behind* whoever is looking, rather
  than making them wait for it.

Cold, with the nflverse logs already down: about **1.7 seconds** to a drawn
board. Switching book or moving a filter: **about twenty milliseconds**.

## Running it somewhere else

It is standard library plus Streamlit, so there is nothing to provision.

1. Push the repo to GitHub.
2. At [share.streamlit.io](https://share.streamlit.io), *Create app* -> from
   your repo, branch `main`, main file `app.py`.
3. Nothing goes in Secrets. There are no accounts and no keys of ours.

`cache/` is gitignored and rebuilds itself on first run; on a host it is
scratch space that disappears on redeploy, which costs one cold pull.

Two things to know before you point other people at it. The BettingPros
endpoint is undocumented and is being called from a shared cloud address
rather than your house -- if it ever starts refusing, that is the first
thing to suspect, and the disk memo is what keeps a refusal from blanking
the board. And the API key in `lines.py` is the one bettingpros.com ships in
its own frontend, not a credential of yours; it is already public, but a
public repo does put it somewhere a scraper will find it. A private repo
works on the free tier and avoids the question.

## Known limits

- **It has not been backtested and will not be.** Judge it live.
- Two weeks into a season a defense read is mostly last year. The share of
  each read that comes from the current season is on every row that leans on
  it, and the weighting is in `model.py`.
- The depth chart is ESPN's, and it lags. A trade or a benching can take a
  day to show, and the shares handed to the next man up are round numbers,
  not fitted ones. The set-aside rule is still the guard for a role neither
  the chart nor the logs can see.
- The injury report is the official one, not Sunday's inactives. A surprise
  scratch ninety minutes before kickoff is not in it.
- Weather is a public forecast model's sustained wind over the game window.
  Gusts are shown but not priced, and a retractable roof nobody has reported
  on is assumed closed.
- BettingPros is an undocumented endpoint. If it breaks, `lines.py` is the
  only file to replace, and `notes/DATA_SOURCES.md` records a Rotowire
  fallback covering four of the seven markets.
