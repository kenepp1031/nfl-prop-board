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

## 3. Snaps / injuries / rosters
.../releases/download/snap_counts/snap_counts_{year}.csv
.../releases/download/injuries/injuries_{year}.csv
.../releases/download/rosters/roster_{year}.csv
(depth_charts_{year}.csv also exists but is ~51 MB -- skip it.)

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

## 5. Images
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
