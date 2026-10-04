"""Pull every feed the board reads and leave it on disk, fresh.

The board already refreshes itself while it is open -- game logs on a six
hour clock, lines on a ten minute one. What it cannot do is refresh while it
is shut, and that is the normal state of it. Open it on a Sunday morning
after a week away and the first thing it does is a cold pull of two seasons
of game logs and sixty pages of lines, with a spinner in front of it.

So this runs once a day whether anyone opens the board or not. It ignores
every cache clock and fetches for real, which is the point: a scheduled run
that honoured the six hour TTL would usually decide there was nothing to do.
By the time the board is opened, every file it wants is already there and
current, and the open costs a file read.

    python refresh.py            # this season, the week about to be played
    python refresh.py --week 5   # a specific week
    python refresh.py --quiet    # only complain on failure

Run by "Update NFL Props.cmd", which the installed scheduled task calls each
morning. Safe to run by hand at any time, and safe to run while the board is
open -- every write goes to a temp file and is renamed into place.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
import traceback

import board
import common
import depth
import lines
import nflverse
import weather

SEASON = 2026
LOG = common.APP_DIR / "cache" / "refresh.log"
KEEP_LOG_BYTES = 200_000

# Weeks of lines to warm. The week about to be played is what the board
# opens on; the one after it is what you look at on a Monday, and the books
# have usually posted some of it by then. Past weeks are deliberately not
# refreshed -- those games are played and their numbers never change again.
WEEKS_AHEAD = 2


def log(msg: str, quiet: bool = False) -> None:
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp}  {msg}"
    if not quiet:
        print(line, flush=True)
    try:
        LOG.parent.mkdir(exist_ok=True)
        # Trim from the front rather than letting a daily job grow a log
        # forever on a machine nobody is watching.
        if LOG.exists() and LOG.stat().st_size > KEEP_LOG_BYTES:
            tail = LOG.read_text(encoding="utf-8", errors="replace")[-KEEP_LOG_BYTES // 2:]
            LOG.write_text(tail[tail.find("\n") + 1:], encoding="utf-8")
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass                      # a board that cannot log still refreshes


def step(name: str, fn, quiet: bool = False) -> tuple[bool, object]:
    """Run one pull, time it, and let the rest continue if it fails.

    A refusal from one feed should cost that feed, not the whole run. Every
    reader downstream already falls back to its cached copy, so a failed step
    leaves the board on yesterday's file rather than on nothing.
    """
    t0 = time.perf_counter()
    try:
        out = fn()
    except Exception as exc:
        log(f"  FAILED  {name}: {exc.__class__.__name__}: {exc}", quiet)
        traceback.print_exc(file=sys.stderr)
        return False, None
    log(f"  ok      {name} ({time.perf_counter() - t0:.1f}s)", quiet)
    return True, out


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh the NFL prop board's data.")
    ap.add_argument("--season", type=int, default=SEASON)
    ap.add_argument("--week", type=int, default=None,
                    help="default: the week about to be played, plus the next one")
    ap.add_argument("--quiet", action="store_true",
                    help="write to the log but not to the console")
    args = ap.parse_args()
    season, quiet = args.season, args.quiet

    log(f"refresh {season} starting", quiet)
    years = list(range(season - board.LOOKBACK_SEASONS + 1, season + 1))
    failures = 0

    # --- the feeds, forced past their clocks -------------------------------
    # max_age_hours=0 means "the cached copy is always too old", which is how
    # a scheduled pull differs from the board's own opportunistic one.
    def logs():
        for year in years:
            common.cached_fetch(f"stats_player_week_{year}.csv",
                                nflverse.WEEKLY_URL.format(year=year), 0)

    def injuries():
        for year in years:
            common.cached_fetch(f"injuries_{year}.csv",
                                nflverse.INJURY_URL.format(year=year), 0)

    ok, _ = step("game logs", logs, quiet); failures += not ok
    ok, _ = step("schedule, spreads and totals", lambda: common.cached_fetch(
        "games.csv", nflverse.GAMES_URL, 0), quiet); failures += not ok
    ok, _ = step("injury report", injuries, quiet); failures += not ok
    # Rosters carry each player's entry year, which is what tells a rookie
    # apart from a veteran who simply did not play last season.
    ok, _ = step("rosters (entry years, reserve lists)", lambda: common.cached_fetch(
        f"roster_{season}.csv", nflverse.ROSTER_URL.format(year=season), 0),
        quiet); failures += not ok
    # ESPN's depth chart by way of nflverse: the file is the whole season of
    # twice-daily snapshots, so this is the biggest download of the run.
    ok, chart = step("depth chart", lambda: depth.chart(season, max_age_hours=0),
                     quiet); failures += not ok
    if ok and chart:
        stamp = (chart.get("stamp") or "")[:16].replace("T", " ")
        log(f"          {len(chart.get('teams') or {})} teams, snapshot {stamp} UTC", quiet)

    # --- which weeks of lines to warm --------------------------------------
    try:
        sched = nflverse.schedule(season)
        weeks_all = sorted({g["week"] for g in sched})
        if args.week:
            weeks = [args.week]
        else:
            now = board.current_week(sched)
            weeks = [w for w in weeks_all if now <= w < now + WEEKS_AHEAD]
        log(f"  current week {board.current_week(sched)}, "
            f"warming lines for {weeks}", quiet)
    except Exception as exc:
        log(f"  FAILED  reading schedule for week numbers: {exc}", quiet)
        weeks, failures = [], failures + 1

    for w in weeks:
        ok, raw = step(f"lines, week {w}",
                       lambda w=w: lines.raw_offers(season, w, max_age_hours=0),
                       quiet)
        failures += not ok
        if ok and raw is not None:
            n = sum(len(v) for v in (raw.get("offers") or {}).values())
            log(f"          {n} offers across {len(raw.get('events') or [])} games",
                quiet)

    # --- the forecast for every outdoor game in those weeks ----------------
    # Forecasts move, so this is the pull most worth repeating. The morning
    # run has Sunday's 1 o'clock five hours out.
    for w in weeks:
        ok, wx = step(f"weather, week {w}",
                      lambda w=w: weather.forecasts(season, w, max_age_hours=0),
                      quiet)
        failures += not ok
        if ok and wx:
            outdoors = [v for v in wx.values() if v and not v.get("indoor")]
            windiest = max((v["wind"] for v in outdoors), default=0.0)
            log(f"          {len(outdoors)} outdoor games, windiest {windiest:.0f} mph",
                quiet)

    # --- prove the board can actually be built from what we just pulled ----
    # Warming the files is not the same as knowing they work together. A
    # feed that changes a column name downloads perfectly and breaks the
    # board on open; better to find that in the log than on a Sunday.
    def build():
        stats = board.load_stats(season)
        if not weeks:
            return 0
        ml = lines.price(lines.raw_offers(season, weeks[0]),
                         lines.BOOKS["DraftKings"])
        try:
            wx = weather.forecasts(season, weeks[0])
        except Exception:
            wx = {}                       # already logged as its own step
        data = board.build(season, weeks[0], "DraftKings", stats, ml, weather=wx)
        props = [p for g in data["games"] for p in g["props"]]
        rookies = [p for p in props if p.get("rookie")]
        log(f"          {len(props)} props, "
            f"{sum(1 for p in props if p['playable'])} playable, "
            f"{len(rookies)} rookie ({sum(1 for p in rookies if p['playable'])} playable)",
            quiet)
        return len(props)

    ok, _ = step("build the board", build, quiet); failures += not ok

    log("refresh finished clean" if not failures
        else f"refresh finished with {failures} failed step(s); "
             f"the board falls back to the last good copy of each",
        quiet)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
