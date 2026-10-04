# NFL Props - data sources
Verified working 2026-09-20. Every source below is free, needs no account,
and has no monthly quota. Re-verify with `python notes/probe_sources.py`.

## 1. Player game stats  (the projection base)
https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{year}.csv

150 columns, one row per player per game. Carries every stat the board needs:
passing_yards, passing_tds, passing_interceptions, rushing_yards, rushing_tds,
receiving_yards, receiving_tds, carries, targets, receptions, target_share,
air_yards_share, wopr, plus headshot_url for the player pictures.

NOTE: the release tag is `stats_player`, NOT `player_stats`. The old
`player_stats_{year}.csv` files stop at 2024 and are no longer updated -- this is
why C:\NFL 2.0 has no yardage or TD data for 2025/2026 and silently fell back to
a thin play-by-play slice. Do not copy that URL.

2026 file was last updated 2026-09-20 09:04 UTC. Regular season weeks 1-2 present.

## 2. Schedule, spreads and totals
https://github.com/nflverse/nfldata/raw/master/data/games.csv
game_id, week, gameday, gametime, away_team, home_team, spread_line, total_line,
roof, surface, div_game, scores. Full 2026 season, all 18 weeks.

## 3. Snaps / injuries / rosters / depth charts
.../releases/download/snap_counts/snap_counts_{year}.csv
.../releases/download/injuries/injuries_{year}.csv
.../releases/download/rosters/roster_{year}.csv
.../releases/download/depth_charts/depth_charts_{year}.csv.gz

Depth charts (verified 2026-09-25): ESPN's chart, snapshotted twice a day
since March into one file per season with every snapshot kept -- 53 MB as
.csv, 11 MB as .csv.gz, three weeks in. Columns: dt, team, player_name,
espn_id, gsis_id, pos_grp, pos_name, pos_abb, pos_slot, pos_rank. The newest
`dt` is the chart; pos_rank is the order within the position (RB1, RB2...);
gsis_id is on 581 of 582 skill-position rows so the join to the game logs is
exact. depth.py keeps the latest snapshot as cache/depth_{year}.json.

Rosters carry `status` per player (ACT, DEV, RES, CUT, RET, EXE, INA) --
RES is the reserve lists, which the weekly injury report never mentions.

NFL 2.0 (C:\NFL 2.0) has no depth chart file either; it infers starters from
snap_counts and scrapes ESPN's injuries page (www.espn.com/nfl/injuries,
which does work from here -- only ESPN's site.api is blocked). That page
lists Injured Reserve, but its Out/Questionable are pre-designation guesses,
so the official nflverse report stays the source here.

## 4. DraftKings + FanDuel prop lines
BettingPros v3. Undocumented public web API, key is the one their own site ships.
  base    https://api.bettingpros.com/v3/
  header  x-api-key: CHi8Hy5CEE4khd46XNYL23dCFX96oUdw6qOt1Dnh
  books   book id 12 = DraftKings, 10 = FanDuel, 0 = consensus (18 books total)
  limit   `limit` maxes out at 10 -> must paginate via _pagination.total_pages

  GET events?sport=NFL&season=2026&week=N          -> event ids
  GET books?sport=NFL                              -> book id map
  GET offers?sport=NFL&market_id=M&event_id=a:b:c&limit=10&page=P

  market ids for our seven props:
    103  passing yards            107  rushing yards
    105  receiving yards          406  rushing + receiving yards
    102  passing touchdowns       101  interceptions
     78  anytime touchdown  (one offer per game, ~32 selections in it)

  Coverage measured on the 2026 week 2 slate:
    market            offers   DK   FD
    passing yards         32   32   32
    rushing yards        109   89   91
    receiving yards      225  182  182
    rush+rec yards        61   41    0
    passing TDs           32   32   30
    interceptions         32   32    0
    anytime TD            16   16   16   (16 offers = 16 games)
  FanDuel does not post rush+rec or interceptions; DraftKings covers all seven.

## 5. Weather  (verified 2026-09-25)
Open-Meteo forecast API. No key, no account, free for non-commercial use,
10,000 requests a day -- the board makes one a week.
  https://api.open-meteo.com/v1/forecast
    ?latitude=42.7738,-22.9122&longitude=-78.7870,-43.2302   (a list: one result per venue)
    &hourly=temperature_2m,apparent_temperature,precipitation_probability,
            precipitation,snowfall,weather_code,wind_speed_10m,wind_gusts_10m
    &wind_speed_unit=mph&temperature_unit=fahrenheit&precipitation_unit=inch
    &timezone=America/New_York&forecast_days=16
Asking for the hours in Eastern means a game's index in the list is just its
nfldata kickoff hour. Two or more venues come back as a JSON list, one as a
dict. Venue coordinates are a table in weather.py keyed on games.csv's
`stadium_id` -- nfldata has no stadiums file this machine can reach.

Also working from here, kept as a fallback: api.weather.gov (US venues only,
needs a User-Agent, two calls per point).

## 6. Images
  NFL shield  https://a.espncdn.com/i/teamlogos/leagues/500/nfl.png
  team logo   https://a.espncdn.com/i/teamlogos/nfl/500/{abbr_lowercase}.png
  headshot    comes in the stats file as headshot_url (static.www.nfl.com)

## Blocked from this machine -- do not build on these
DraftKings sportsbook JSON, FanDuel, and even ESPN's public site.api all return
403 from an Akamai edge ("Access Denied" / errors.edgesuite.net). Confirmed both
inside and outside the sandbox, so it is the network/IP, not tooling. BettingPros
and nflverse are unaffected.

## Backup line source if BettingPros breaks
Rotowire, no key, clean JSON, carries DK + FanDuel + 6 more books:
  https://www.rotowire.com/betting/nfl/tables/all-bets-props.php?prop=KEY
  keys: passYds, rushYds, recYds, receptions, completions, passAtt
  no `prop` parameter at all -> anytime TD ("Score TD")
Covers 4 of our 7 -- no pass TDs, no interceptions, no rush+rec.
Send a Referer of https://www.rotowire.com/betting/nfl/player-props.php
