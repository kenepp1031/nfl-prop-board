"""Cross-check the nflverse weekly stats against nfl.com's official season
totals. nflverse is what the board runs on; nfl.com is the league's own number,
so a mismatch here means our ingest is wrong, not theirs.

    python notes/verify_vs_nflcom.py 2025

Season totals only -- that is all nfl.com publishes. It is a correctness check,
not a data source: the board needs per-game rows and nfl.com has none.
"""
from __future__ import annotations

import csv
import collections
import html
import io
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
NFLVERSE = ("https://github.com/nflverse/nflverse-data/releases/download/"
            "stats_player/stats_player_week_{year}.csv")
NFLCOM = "https://www.nfl.com/stats/player-stats/category/{cat}/{year}/reg/all/{sort}/desc"

# nfl.com column header -> nflverse weekly field, per category. STRICT columns
# feed the projections and must match to the value; any drift is a real bug.
# LOOSE columns are ones the league and nflverse legitimately bucket differently
# and that no prop on the board reads, so they are reported but do not fail:
#
#   - first downs: on 2025 data nflverse filed one McCaffrey play as a rushing
#     first down where nfl.com filed it as receiving. Both sides agree he had
#     119; only the split moves. A lateral or a shovel behind the line does this.
#   - fumbles: nflverse logged McMillan's fumble in fumbles_total but attributed
#     it to neither the rushing nor the receiving bucket. The fumble is there,
#     the category is not.
CATEGORIES = {
    "passing": ("passingyards", {
        "Pass Yds": "passing_yards", "Att": "attempts", "Cmp": "completions",
        "TD": "passing_tds", "INT": "passing_interceptions",
        "Sck": "sacks_suffered", "20+": "passing_20", "40+": "passing_40",
    }, {"1st": "passing_first_downs"}),
    "rushing": ("rushingyards", {
        "Rush Yds": "rushing_yards", "Att": "carries", "TD": "rushing_tds",
        "20+": "rushing_20", "40+": "rushing_40",
    }, {"Rush 1st": "rushing_first_downs", "Rush FUM": "rushing_fumbles"}),
    "receiving": ("receivingyards", {
        "Rec": "receptions", "Yds": "receiving_yards", "TD": "receiving_tds",
        "20+": "receiving_20", "40+": "receiving_40", "Tgts": "targets",
    }, {"Rec 1st": "receiving_first_downs", "Rec FUM": "receiving_fumbles"}),
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def scrape_nflcom(year: int, cat: str, sort: str) -> tuple[list[str], dict[str, list[str]]]:
    """Returns (headers, {player_name: row_cells}). One page = the top 25."""
    page = fetch(NFLCOM.format(cat=cat, year=year, sort=sort))
    table = re.search(r"<table[^>]*>(.*?)</table>", page, re.S)
    if not table:
        raise RuntimeError(f"no stats table on the {cat} page -- markup changed?")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(1), re.S)
    headers = [strip_tags(c) for c in re.findall(r"<th[^>]*>(.*?)</th>", rows[0], re.S)]
    out = {}
    for row in rows[1:]:
        cells = [strip_tags(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if cells:
            out[cells[0]] = cells
    return headers, out


def load_nflverse(year: int) -> list[dict]:
    text = fetch(NFLVERSE.format(year=year))
    return [r for r in csv.DictReader(io.StringIO(text)) if r["season_type"] == "REG"]


def num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main(year: int) -> int:
    print(f"nflverse stats_player_week_{year}.csv  vs  nfl.com {year} REG season totals\n")
    weekly = load_nflverse(year)
    failures = 0
    notes = []

    for cat, (sort, strict, loose) in CATEGORIES.items():
        colmap = {**strict, **loose}
        totals = collections.defaultdict(lambda: collections.defaultdict(float))
        for r in weekly:
            who = totals[r["player_display_name"]]
            for field in colmap.values():
                who[field] += num(r.get(field))

        headers, official = scrape_nflcom(year, cat, sort)
        checked = mismatched = skipped = 0

        for player, cells in official.items():
            row = dict(zip(headers, cells))
            ours = totals.get(player)
            if ours is None:
                skipped += 1          # name spelled differently on the two sides
                continue
            for header, field in colmap.items():
                if header not in row:
                    continue
                # nfl.com prints sack yardage positive, nflverse signs it negative
                theirs, mine = num(row[header]), abs(ours[field])
                checked += 1
                if abs(theirs - mine) <= 0.5:
                    continue
                line = (f"{cat:10} {player:22} {header:9} "
                        f"nfl.com={theirs:g}  nflverse={mine:g}")
                if header in strict:
                    mismatched += 1
                    print(f"  MISMATCH {line}")
                else:
                    notes.append(line)

        note = f" ({skipped} unmatched names)" if skipped else ""
        status = "OK" if not mismatched else f"{mismatched} MISMATCHED"
        print(f"  {cat:10} {len(official):>3} players, {checked:>4} values -> {status}{note}")
        failures += mismatched

    if notes:
        print()
        print(f"  {len(notes)} known bucketing difference(s), not read by any prop:")
        for line in notes:
            print(f"    {line}")

    print()
    if failures:
        print(f"FAIL: {failures} projection input(s) disagree with the league's numbers.")
    else:
        print("PASS: every value the projections read matches nfl.com exactly.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2025))
