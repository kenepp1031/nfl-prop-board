"""The depth chart: who is behind whom, per team, per position.

nflverse snapshots ESPN's depth charts twice a day into one file per season,
every snapshot kept, which is why the file is 50 MB three weeks into a
season. Only the newest snapshot means anything here, and it is about two
thousand rows, so the parse keeps that and throws the history away.

    depth.chart(2026)  ->  {"stamp": "2026-09-25T12:44:44Z",
                            "teams": {"BUF": {"RB": [{id, name, rank}, ...], ...}, ...}}

Ranks are ESPN's order within the position -- RB1, RB2 -- and every row
carries the nflverse player id, so the join to the game logs is exact. Only
QB, RB, WR and TE are kept; nobody is projecting a fullback's line.

What the board does with it lives in model.next_man_up.
"""
from __future__ import annotations

import collections
import csv
import gzip
import io
import urllib.request

import common
import nflverse
from common import cached_json

# The .gz is a fifth the size of the .csv. It is unpacked in memory and not
# kept: the only thing worth having on disk is the two-thousand-row snapshot.
DEPTH_URL = ("https://github.com/nflverse/nflverse-data/releases/download/"
             "depth_charts/depth_charts_{year}.csv.gz")
POSITIONS = ("QB", "RB", "WR", "TE")
# ESPN's abbreviations where they differ from nflverse's
TEAM_ALIAS = {"WSH": "WAS", "JAC": "JAX", "LAR": "LA", "LVR": "LV"}


def _team(code: str) -> str:
    c = (code or "").strip().upper()
    return nflverse.team(TEAM_ALIAS.get(c, c))


def _latest(text: str) -> dict:
    """The newest snapshot in the file, reduced to what the board reads."""
    stamp, keep = "", []
    for r in csv.DictReader(io.StringIO(text)):
        dt = r.get("dt") or ""
        if dt > stamp:
            stamp, keep = dt, []
        if dt == stamp and r.get("pos_abb") in POSITIONS:
            keep.append(r)

    teams: dict[str, dict[str, list[dict]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for r in keep:
        pid = (r.get("gsis_id") or "").strip()
        try:
            rank = int(r.get("pos_rank") or 0)
        except ValueError:
            continue
        if not pid or rank <= 0:
            continue
        teams[_team(r.get("team"))][r["pos_abb"]].append(
            {"id": pid, "name": (r.get("player_name") or "").strip(), "rank": rank})
    for chart in teams.values():
        for rows in chart.values():
            rows.sort(key=lambda p: p["rank"])
    return {"stamp": stamp, "teams": {t: dict(c) for t, c in teams.items()}}


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": common.UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read()
    return gzip.decompress(raw).decode("utf-8", "replace")


def chart(season: int, max_age_hours: float = nflverse.CURRENT_HOURS) -> dict:
    """The latest depth chart, memoised on disk so the board never re-reads
    fifty megabytes to learn two thousand rows. A failed pull serves the
    last good copy; with none at all it raises, and the caller decides
    whether a board without a depth chart is still a board (it is)."""
    return cached_json(f"depth_{season}.json", max_age_hours,
                       lambda: _latest(_fetch(DEPTH_URL.format(year=season))))
