"""HTML for the board. Streamlit has no native element that puts a team
logo, a player headshot, our number, the book's number and a written reason
on one dense row, so the panels are hand-built markup; everything else in
the app is a native widget.

The layout is deliberately ordered: who, what we think he does, why we think
it, and only then what the book has posted. The price is a reference column,
never the headline.
"""
from __future__ import annotations

import html

import model

# nflverse abbreviation -> the slug ESPN's logo CDN uses
ESPN_SLUG = {"WAS": "wsh", "LA": "lar"}

SHIELD = "https://a.espncdn.com/i/teamlogos/leagues/500/nfl.png"

# how many reasons fit on a row before it stops being readable
MAX_DRIVERS = 3


def logo(abbr: str) -> str:
    return f"https://a.espncdn.com/i/teamlogos/nfl/500/{ESPN_SLUG.get(abbr, (abbr or '').lower())}.png"


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def american(odds) -> str:
    if odds is None:
        return "--"
    return f"+{odds:.0f}" if odds > 0 else f"{odds:.0f}"


# the scale itself lives in model.py, next to what produces it
confidence_word = model.confidence_word


STYLE = """
<style>
:root {
  --ink:      #08080A;
  --panel:    #101014;
  --panel-2:  #16161C;
  --rule:     #2A2A33;
  --text:     #EDEDED;
  --dim:      #7A7A88;
  --dimmer:   #55555F;
  --acid:     #C6FF00;
  --hot:      #FF2D7E;
  --cyan:     #00E5FF;
}

/* ---- slate header -------------------------------------------------- */
.np-head { display:flex; align-items:center; gap:18px; border-bottom:3px solid var(--acid);
           padding:4px 0 14px; margin-bottom:22px; }
.np-head img { height:54px; filter:drop-shadow(0 0 10px rgba(198,255,0,.25)); }
.np-head .t { font-family:Anton,Impact,sans-serif; font-size:40px; line-height:.95;
              letter-spacing:.5px; text-transform:uppercase; }
.np-head .t em { font-style:normal; color:var(--acid); }
.np-head .s { color:var(--dim); font-size:13px; letter-spacing:2.5px;
              text-transform:uppercase; margin-top:4px; }

/* ---- section rule -------------------------------------------------- */
.np-sect { display:flex; align-items:baseline; gap:14px; margin:6px 0 14px; }
.np-sect .h { font-family:Anton,Impact,sans-serif; font-size:24px; letter-spacing:.8px;
              text-transform:uppercase; color:var(--hot); }
.np-sect .d { font-size:11.5px; color:var(--dim); letter-spacing:.4px; }

/* ---- one game ------------------------------------------------------ */
.np-game { border:1px solid var(--rule); background:var(--panel); margin-bottom:26px; }
.np-bar  { display:flex; align-items:stretch; background:var(--panel-2);
           border-bottom:1px solid var(--rule); flex-wrap:wrap; }
.np-side { display:flex; align-items:center; gap:11px; padding:13px 17px; min-width:250px; flex:1; }
.np-side img { height:40px; width:40px; object-fit:contain; }
.np-abbr { font-family:Anton,Impact,sans-serif; font-size:25px; letter-spacing:1px; }
.np-where{ font-family:'Space Mono',monospace; font-size:10px; color:var(--dim);
           letter-spacing:1.5px; vertical-align:middle; }
.np-imp  { font-family:'Space Mono',monospace; font-size:11px; color:var(--dim); }
.np-imp b { color:var(--text); font-weight:700; }
.np-mid  { display:flex; flex-direction:column; justify-content:center; align-items:center;
           padding:10px 22px; border-left:1px solid var(--rule); border-right:1px solid var(--rule);
           min-width:150px; }
.np-mid .k { font-family:'Space Mono',monospace; font-size:16px; color:var(--acid); font-weight:700; }
.np-mid .v { font-size:10px; color:var(--dim); letter-spacing:1.6px; text-transform:uppercase; }

/* defense read chip */
.np-read { display:inline-block; font-size:10px; letter-spacing:1.3px; text-transform:uppercase;
           padding:3px 8px; border:1px solid currentColor; transform:skewX(-11deg);
           font-weight:700; margin-top:4px; }
.np-read span { display:inline-block; transform:skewX(11deg); }
.read-pass { color:var(--cyan); }
.read-run  { color:var(--acid); }
.read-soft { color:var(--hot); }
.read-stiff{ color:var(--dim); }
.read-bal  { color:var(--dim); }

/* ---- prop rows ----------------------------------------------------- */
.np-row { display:grid;
          grid-template-columns:44px minmax(132px,1.1fr) 104px 96px 88px minmax(200px,1.9fr) 76px;
          align-items:center; gap:12px; padding:10px 16px;
          border-bottom:1px solid rgba(42,42,51,.55); }
.np-row:last-child { border-bottom:none; }
.np-row:hover { background:rgba(198,255,0,.035); }
.np-row.flagged { opacity:.42; }

.np-face { width:40px; height:40px; object-fit:cover; background:var(--panel-2);
           border:1px solid var(--rule); }
.np-who  { min-width:0; }
.np-name { font-weight:700; font-size:14px; white-space:nowrap; overflow:hidden;
           text-overflow:ellipsis; }
.np-meta { font-size:10.5px; color:var(--dim); letter-spacing:.7px; text-transform:uppercase; }
.np-mkt  { font-size:10px; letter-spacing:1.1px; text-transform:uppercase; color:var(--dim);
           border-left:2px solid var(--rule); padding-left:9px; }

/* our number leads; the book's sits beside it, smaller and grey */
.np-ours { font-family:'Space Mono',monospace; text-align:right; }
.np-ours .big { font-size:21px; font-weight:700; color:var(--cyan); display:block;
                line-height:1.1; }
.np-ours .cap { font-size:9px; color:var(--cyan); opacity:.75; letter-spacing:1.5px;
                text-transform:uppercase; }
.np-book { font-family:'Space Mono',monospace; text-align:right; color:var(--dimmer); }
.np-book .big { font-size:13px; font-weight:700; display:block; line-height:1.15; }
.np-book .cap { font-size:9px; letter-spacing:1.3px; text-transform:uppercase; }
.np-gap { font-size:10px; font-weight:700; }
.gap-over  { color:var(--acid); }
.gap-under { color:var(--hot); }

/* the reasons */
.np-why  { min-width:0; }
.np-drv  { font-size:11px; color:#B6B6C2; line-height:1.45; white-space:nowrap;
           overflow:hidden; text-overflow:ellipsis; }
.np-drv i { font-style:normal; font-weight:700; margin-right:5px; }
.up   { color:var(--acid); }
.down { color:var(--hot); }
.flat { color:var(--dimmer); }

/* confidence meter */
.np-conf { text-align:right; }
.np-pips { display:flex; gap:2px; justify-content:flex-end; margin-bottom:3px; }
.np-pip  { width:9px; height:6px; background:#23232C; }
.np-pip.on { background:var(--acid); }
.np-conf .w { font-size:9px; color:var(--dim); letter-spacing:.9px; text-transform:uppercase; }

.np-flagnote { grid-column:4 / -1; font-size:10.5px; color:var(--hot); letter-spacing:.5px; }
.np-empty { padding:16px; color:var(--dim); font-size:13px; }

/* ---- scorers leaderboard ------------------------------------------- */
.np-board { border:1px solid var(--rule); background:var(--panel); margin-bottom:30px; }
.np-sc { display:grid;
         grid-template-columns:40px 42px minmax(140px,1.1fr) 132px 92px 84px minmax(180px,1.7fr);
         align-items:center; gap:12px; padding:10px 16px;
         border-bottom:1px solid rgba(42,42,51,.55); }
.np-sc:last-child { border-bottom:none; }
.np-sc:hover { background:rgba(255,45,126,.05); }
.np-rank { font-family:Anton,Impact,sans-serif; font-size:23px; color:var(--hot);
           text-align:center; line-height:1; }
.np-rank.cool { color:var(--dimmer); }
.np-game-of { font-size:10.5px; color:var(--dim); letter-spacing:.9px; text-transform:uppercase; }
.np-game-of b { color:var(--text); font-weight:700; }

@media (max-width: 1000px) {
  .np-row { grid-template-columns:38px 1fr 92px 84px; }
  .np-mkt, .np-why, .np-conf { display:none; }
  .np-sc  { grid-template-columns:34px 38px 1fr 88px 80px; }
  .np-game-of, .np-sc .np-why { display:none; }
}
</style>
"""

_READ_CLASS = {
    "pass funnel": "read-pass",
    "run funnel": "read-run",
    "soft all over": "read-soft",
    "stiff all over": "read-stiff",
    "balanced": "read-bal",
}

_LEAN_MARK = {1: ('<i class="up">&#9650;</i>', ""),
              -1: ('<i class="down">&#9660;</i>', ""),
              0: ('<i class="flat">&#8226;</i>', "")}


def header(season: int, week: int, book: str, n_props: int) -> str:
    return (
        f'<div class="np-head"><img src="{SHIELD}" alt="NFL">'
        f'<div><div class="t">Prop <em>Board</em></div>'
        f'<div class="s">{season} &middot; week {week} &middot; our read '
        f'&middot; {n_props} players &middot; {esc(book)} shown for reference</div></div></div>'
    )


def section(title: str, note: str) -> str:
    return (f'<div class="np-sect"><div class="h">{esc(title)}</div>'
            f'<div class="d">{esc(note)}</div></div>')


def _pips(conf: float) -> str:
    on = max(1, min(5, round(conf * 5 + 0.0001)))
    cells = "".join(f'<div class="np-pip{" on" if i < on else ""}"></div>' for i in range(5))
    return (f'<div class="np-conf"><div class="np-pips">{cells}</div>'
            f'<div class="w">{esc(confidence_word(conf))}</div></div>')


def _drivers_html(p: dict, limit: int = MAX_DRIVERS) -> str:
    rows = []
    for d in p.get("drivers", [])[:limit]:
        mark = _LEAN_MARK.get(d.get("lean", 0), _LEAN_MARK[0])[0]
        rows.append(f'<div class="np-drv">{mark}{esc(d["text"])}</div>')
    return f'<div class="np-why">{"".join(rows)}</div>' if rows else '<div class="np-why"></div>'


def _side(abbr: str, implied: float, read: str, home: bool) -> str:
    cls = _READ_CLASS.get(read, "read-bal")
    where = "home" if home else "away"
    return (
        f'<div class="np-side"><img src="{logo(abbr)}" alt="{esc(abbr)}">'
        f'<div><div class="np-abbr">{esc(abbr)} '
        f'<span class="np-where">{where}</span></div>'
        f'<div class="np-imp">implied <b>{implied:.1f}</b></div>'
        f'<div class="np-read {cls}"><span>{esc(read)}</span></div></div></div>'
    )


def game_panel(game: dict, props: list[dict], away_read: str, home_read: str) -> str:
    spread = game["spread"]
    fav = f'{game["home"]} -{spread:g}' if spread > 0 else f'{game["away"]} -{abs(spread):g}'
    if spread == 0:
        fav = "pick 'em"

    rows = "".join(_prop_row(p) for p in props) or (
        '<div class="np-empty">No props clear the filters for this game.</div>')

    return (
        '<div class="np-game">'
        '<div class="np-bar">'
        + _side(game["away"], game["implied_away"], away_read, home=False)
        + f'<div class="np-mid"><div class="k">{game["total"]:g}</div>'
          f'<div class="v">total</div>'
          f'<div class="k" style="margin-top:6px">{esc(fav)}</div>'
          f'<div class="v">spread</div></div>'
        + _side(game["home"], game["implied_home"], home_read, home=True)
        + '</div>' + rows + '</div>'
    )


def _our_cell(p: dict) -> str:
    """What we think happens. Always the biggest thing on the row."""
    if p["market"] == "anytime_td":
        return (f'<div class="np-ours"><span class="big">{p["our_prob"] * 100:.0f}%</span>'
                f'<span class="cap">to score</span></div>')
    if p["market"] in ("pass_tds", "interceptions"):
        return (f'<div class="np-ours"><span class="big">{p["projection"]:.2f}</span>'
                f'<span class="cap">we project</span></div>')
    return (f'<div class="np-ours"><span class="big">{p["projection"]:.0f}</span>'
            f'<span class="cap">yards</span></div>')


def _book_cell(p: dict) -> str:
    """The market, kept small and grey on purpose."""
    if p["market"] == "anytime_td":
        body = (f'<span class="big">{p["market_prob"] * 100:.0f}%</span>'
                f'<span class="cap">book {american(p["over"])}</span>')
    else:
        gap = p["delta"]
        tail = ""
        if gap is not None and abs(gap) >= 0.5:
            cls = "gap-over" if gap > 0 else "gap-under"
            tail = f'<span class="np-gap {cls}">{gap:+.0f} vs line</span><br>'
        body = (f'<span class="big">{p["line"]:g}</span>{tail}'
                f'<span class="cap">book line</span>')
    return f'<div class="np-book">{body}</div>'


def _prop_row(p: dict) -> str:
    face = (f'<img class="np-face" src="{esc(p["headshot"])}" alt="">'
            if p["headshot"] else '<div class="np-face"></div>')
    status = (f' &middot; <span style="color:#FF8A00">{esc(p["status"])}</span>'
              if p["status"] else "")

    if not p["playable"]:
        detail = f'<div class="np-flagnote">set aside &mdash; {esc(p["reason"])}</div>'
    else:
        detail = _our_cell(p) + _book_cell(p) + _drivers_html(p) + _pips(p["confidence"])

    return (
        f'<div class="np-row{"" if p["playable"] else " flagged"}">'
        f'{face}'
        f'<div class="np-who"><div class="np-name">{esc(p["player"])}</div>'
        f'<div class="np-meta">{esc(p["position"])} &middot; {esc(p["team"])} '
        f'vs {esc(p["opponent"])}{status}</div></div>'
        f'<div class="np-mkt">{esc(p["market_label"])}</div>'
        f'{detail}</div>'
    )


def scorer_board(rows: list[dict]) -> str:
    """Everyone on the slate ranked by our probability that they score."""
    if not rows:
        return '<div class="np-board"><div class="np-empty">No scorers priced yet.</div></div>'
    return '<div class="np-board">' + "".join(
        _scorer_row(i + 1, p) for i, p in enumerate(rows)) + '</div>'


def _scorer_row(rank: int, p: dict) -> str:
    face = (f'<img class="np-face" src="{esc(p["headshot"])}" alt="">'
            if p["headshot"] else '<div class="np-face"></div>')
    cool = "" if rank <= 10 else " cool"
    return (
        f'<div class="np-sc">'
        f'<div class="np-rank{cool}">{rank}</div>{face}'
        f'<div class="np-who"><div class="np-name">{esc(p["player"])}</div>'
        f'<div class="np-meta">{esc(p["position"])} &middot; {esc(p["team"])}</div></div>'
        f'<div class="np-game-of"><b>{esc(p["team"])}</b> vs {esc(p["opponent"])}<br>'
        f'{p["script"]["implied"]:.1f} implied pts</div>'
        + _our_cell(p) + _book_cell(p) + _drivers_html(p, 2) +
        f'</div>'
    )


def yardage_board(rows: list[dict]) -> str:
    """One market ranked by our projection, biggest first."""
    if not rows:
        return '<div class="np-board"><div class="np-empty">Nothing priced for that market.</div></div>'
    return '<div class="np-board">' + "".join(
        _yardage_row(i + 1, p) for i, p in enumerate(rows)) + '</div>'


def _yardage_row(rank: int, p: dict) -> str:
    face = (f'<img class="np-face" src="{esc(p["headshot"])}" alt="">'
            if p["headshot"] else '<div class="np-face"></div>')
    cool = "" if rank <= 10 else " cool"
    return (
        f'<div class="np-sc">'
        f'<div class="np-rank{cool}">{rank}</div>{face}'
        f'<div class="np-who"><div class="np-name">{esc(p["player"])}</div>'
        f'<div class="np-meta">{esc(p["position"])} &middot; {esc(p["team"])}</div></div>'
        f'<div class="np-game-of"><b>{esc(p["team"])}</b> vs {esc(p["opponent"])}<br>'
        f'{esc(confidence_word(p["confidence"]))}</div>'
        + _our_cell(p) + _book_cell(p) + _drivers_html(p, 2) +
        f'</div>'
    )
